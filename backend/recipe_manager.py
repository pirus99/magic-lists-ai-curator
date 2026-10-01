import json
import math
import os
import re
from typing import Dict, Any, Optional, List
from pathlib import Path

# Math functions allowed inside recipe {{MATH:...}} expressions.
_SAFE_MATH_NAMES = {
    "abs": abs, "round": round, "min": min, "max": max,
    "ceil": math.ceil, "floor": math.floor,
    "pow": pow, "sqrt": math.sqrt,
}

class RecipeManager:
    """Manages playlist generation recipes and their application"""
    
    def __init__(self, recipes_dir: str = "recipes"):
        self.recipes_dir = Path(recipes_dir)
        self.registry_path = self.recipes_dir / "registry.json"
        self._registry_cache = None
        self._recipe_cache = {}
    
    def _load_registry(self) -> Dict[str, str]:
        """Load the recipe registry mapping playlist types to recipe files"""
        if self._registry_cache is None:
            try:
                with open(self.registry_path, 'r') as f:
                    self._registry_cache = json.load(f)
            except FileNotFoundError:
                raise Exception(f"Recipe registry not found at {self.registry_path}")
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in recipe registry: {e}")
        
        return self._registry_cache
    
    def _load_recipe(self, recipe_filename: str) -> Dict[str, Any]:
        """Load a specific recipe file"""
        if recipe_filename not in self._recipe_cache:
            recipe_path = self.recipes_dir / recipe_filename
            try:
                with open(recipe_path, 'r') as f:
                    self._recipe_cache[recipe_filename] = json.load(f)
            except FileNotFoundError:
                raise Exception(f"Recipe file not found: {recipe_path}")
            except json.JSONDecodeError as e:
                raise Exception(f"Invalid JSON in recipe file {recipe_filename}: {e}")
        
        return self._recipe_cache[recipe_filename]
    
    def get_recipe(self, playlist_type: str) -> Dict[str, Any]:
        """Get the current recipe for a playlist type"""
        registry = self._load_registry()
        
        if playlist_type not in registry:
            raise Exception(f"No recipe registered for playlist type: {playlist_type}")
        
        recipe_filename = registry[playlist_type]
        return self._load_recipe(recipe_filename)
    
    def _evaluate_math_expressions(self, obj: Any, inputs: Dict[str, Any]) -> Any:
        """First pass: Evaluate {{MATH:...}} expressions before regular replacements."""
        import re
        import math
        
        if isinstance(obj, str):
            # Find all {{MATH:...}} patterns
            math_pattern = r'\{\{MATH:([^}]+)\}\}'
            
            def evaluate_math(match):
                expression = match.group(1)
                
                # Replace DESIRED_TRACK_COUNT with actual value inside math expression
                if "DESIRED_TRACK_COUNT" in expression:
                    expression = expression.replace("DESIRED_TRACK_COUNT", str(inputs.get("num_tracks", 25)))
                
                try:
                    # Evaluate the math expression safely
                    # Allow basic math operations and functions
                    allowed_names = {
                        "__builtins__": {},
                        "abs": abs, "round": round, "min": min, "max": max,
                        "ceil": math.ceil, "floor": math.floor,
                        "pow": pow, "sqrt": math.sqrt
                    }
                    
                    result = eval(expression, allowed_names, {})
                    
                    # Convert to integer if it's a whole number
                    if isinstance(result, float) and result.is_integer():
                        result = int(result)
                    
                    return str(result)
                    
                except Exception as e:
                    print(f"❌ Math evaluation failed for '{expression}': {e}")
                    return match.group(0)  # Return original if evaluation fails
            
            # Replace all math expressions
            return re.sub(math_pattern, evaluate_math, obj)
            
        elif isinstance(obj, dict):
            return {key: self._evaluate_math_expressions(value, inputs) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._evaluate_math_expressions(item, inputs) for item in obj]
        else:
            return obj

    def _recursive_replace(self, obj: Any, replacements: Dict[str, str]) -> Any:
        """Recursively traverse and replace placeholders in strings within nested structures"""
        if isinstance(obj, dict):
            return {key: self._recursive_replace(value, replacements) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._recursive_replace(item, replacements) for item in obj]
        elif isinstance(obj, str):
            # Replace all placeholders in the string
            result = obj
            for placeholder, replacement in replacements.items():
                result = result.replace(placeholder, replacement)
            return result
        else:
            # Return unchanged for other types (int, float, bool, None)
            return obj
    
    def apply_recipe(self, playlist_type: str, inputs: Dict[str, Any], include_description: bool = False) -> Dict[str, Any]:
        """Apply a recipe with given inputs and return the fully substituted recipe"""
        recipe = self.get_recipe(playlist_type)
        
        # Get recipe filename for logging
        registry = self._load_registry()
        recipe_filename = registry.get(playlist_type, "unknown")
        
        # Check if this is a new-style recipe (has llm_config) or legacy recipe
        if "llm_config" in recipe:
            # New recipe format - use recursive replacement
            replacements = {}

            # General placeholder replacement for all recipe user_parameters keys.
            # This is required for recipes like re_discover_phase1_v2 where the prompt
            # contains placeholders such as {{tracks_found}} and {{available_genres}}.
            for key, value in inputs.items():
                replacements[f"{{{{{key}}}}}"] = str(value)

            # Map common inputs to new placeholder format
            if "artists" in inputs:
                replacements["{{TARGET_ARTIST}}"] = str(inputs["artists"])
            if "genres" in inputs:
                replacements["{{TARGET_GENRE}}"] = str(inputs["genres"])
            if "num_tracks" in inputs:
                replacements["{{DESIRED_TRACK_COUNT}}"] = str(inputs["num_tracks"])

            print(f"🔄 Processing recipe with {len(replacements)} placeholder replacements")

            # Map re-discover specific inputs
            if "candidate_tracks" in inputs:
                replacements["{{CANDIDATE_TRACKS_JSON}}"] = str(inputs["candidate_tracks_json"])
            if "analysis_summary" in inputs:
                replacements["{{ANALYSIS_SUMMARY}}"] = str(inputs["analysis_summary"])

            # Pass 1: Evaluate math expressions first
            math_evaluated_recipe = self._evaluate_math_expressions(recipe, inputs)

            # Pass 2: Apply recursive replacement to the entire recipe
            final_recipe = self._recursive_replace(math_evaluated_recipe, replacements)

            # Verify critical replacements occurred
            model_instructions = final_recipe.get("model_instructions", "")
            unresolved = [
                token for token in ["{{TARGET_ARTIST}}", "{{DESIRED_TRACK_COUNT}}", "{{tracks_found}}", "{{top_genres}}", "{{top_artists}}", "{{top_decades}}", "{{avg_play_count}}", "{{available_genres}}"]
                if token in model_instructions
            ]
            if unresolved:
                print(f"⚠️  Placeholder replacement failed for: {unresolved}")
            else:
                print(f"✅ Recipe processed successfully")

            # Add tracks data to the final recipe for AI processing
            if "tracks_data" in inputs:
                final_recipe["tracks_data"] = inputs["tracks_data"]

            return final_recipe
        
        else:
            # Legacy recipe format - maintain backward compatibility
            print(f"🍳 Using LEGACY recipe format: {recipe_filename}")
            print(f"📋 Recipe version: {recipe.get('version', 'N/A')}")
            print(f"📝 Recipe description: {recipe.get('description', 'N/A')[:100]}...")
            if recipe.get('llm_params'):
                print(f"🤖 Model fallback: {recipe.get('llm_params', {}).get('model_fallback', 'N/A')}")
                print(f"🌡️ Temperature: {recipe.get('llm_params', {}).get('temperature', 'N/A')}")
                print(f"🔢 Max tokens: {recipe.get('llm_params', {}).get('max_tokens', 'N/A')}")
            # Validate inputs
            required_inputs = recipe.get("inputs", [])
            missing_inputs = [inp for inp in required_inputs if inp not in inputs]
            if missing_inputs:
                raise Exception(f"Missing required inputs for {playlist_type}: {missing_inputs}")
            
            # Select the appropriate prompt template
            if include_description and "prompt_template_with_description" in recipe:
                prompt_template = recipe["prompt_template_with_description"]
            else:
                prompt_template = recipe["prompt_template"]
            
            if prompt_template is None:
                # This recipe doesn't use LLM (e.g., re_discover uses algorithmic approach)
                return {
                    "recipe": recipe,
                    "prompt": None,
                    "llm_params": recipe.get("llm_params"),
                    "inputs": inputs
                }
            
            # Fill in the prompt template
            try:
                filled_prompt = prompt_template.format(**inputs)
            except KeyError as e:
                raise Exception(f"Missing template variable in recipe {playlist_type}: {e}")
            
            # Get LLM parameters
            llm_params = recipe.get("llm_params", {})
            
            return {
                "recipe": recipe,
                "prompt": filled_prompt,
                "llm_params": llm_params,
                "inputs": inputs
            }
    
    def list_available_recipes(self) -> Dict[str, Dict[str, Any]]:
        """List all available recipes with their metadata"""
        registry = self._load_registry()
        recipes_info = {}
        
        for playlist_type, recipe_filename in registry.items():
            try:
                recipe = self._load_recipe(recipe_filename)
                recipes_info[playlist_type] = {
                    "filename": recipe_filename,
                    "version": recipe.get("version"),
                    "description": recipe.get("description"),
                    "inputs": recipe.get("inputs", []),
                    "uses_llm": recipe.get("prompt_template") is not None
                }
            except Exception as e:
                recipes_info[playlist_type] = {
                    "filename": recipe_filename,
                    "error": str(e)
                }
        
        return recipes_info
    
    # Placeholders filled by RecipeManager/apply_recipe at request time and therefore
    # not expected to be declared in a recipe's "user_parameters" block.
    RUNTIME_PLACEHOLDERS = {
        "TARGET_ARTIST",
        "TARGET_GENRE",
        "ARTISTS",
        "DESIRED_TRACK_COUNT",
        "CANDIDATE_TRACKS_JSON",
        "ANALYSIS_SUMMARY",
    }

    def validate_recipe(self, recipe_filename: str) -> List[str]:
        """Validate a recipe file and return any errors"""
        errors = []

        try:
            recipe = self._load_recipe(recipe_filename)
        except Exception as e:
            return [f"Failed to load recipe: {e}"]

        if not isinstance(recipe, dict):
            return ["Recipe must be a JSON object"]

        if "user_parameters" in recipe or "llm_config" in recipe:
            errors.extend(self._validate_current_format(recipe))
        else:
            errors.extend(self._validate_parameterized_format(recipe))

        return errors

    def _validate_llm_config(self, recipe: Dict[str, Any], key: str, errors: List[str]) -> None:
        """Validate an LLM config block (max_output_tokens / temperature)"""
        config = recipe.get(key)
        if config is None:
            return

        if not isinstance(config, dict):
            errors.append(f"'{key}' must be an object")
            return

        if "temperature" in config:
            temp = config["temperature"]
            if isinstance(temp, bool) or not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                errors.append(f"'{key}.temperature' must be a number between 0 and 2")

        if "max_output_tokens" in config:
            tokens = config["max_output_tokens"]
            if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
                errors.append(f"'{key}.max_output_tokens' must be a positive integer")

    def _validate_current_format(self, recipe: Dict[str, Any]) -> List[str]:
        """Validate a recipe in the current format (user_parameters + {{PLACEHOLDER}} prompts)"""
        errors = []

        # Required metadata
        for field in ("recipe_id", "name"):
            if not recipe.get(field):
                errors.append(f"Missing required field: {field}")

        # At least one selection prompt is required
        has_selection = any(recipe.get(f) for f in ("model_instructions", "selection_instructions"))
        if not has_selection:
            errors.append("Missing required field: model_instructions")

        # user_parameters must be a flat name -> {{PLACEHOLDER}} mapping
        declared_placeholders = set()
        user_parameters = recipe.get("user_parameters", {})
        if not isinstance(user_parameters, dict):
            errors.append("'user_parameters' must be an object")
        else:
            for name, value in user_parameters.items():
                if not isinstance(value, str) or not re.fullmatch(r'\{\{\s*\w+\s*\}\}', value.strip()):
                    errors.append(f"'user_parameters.{name}' must be a single {{{{PLACEHOLDER}}}} token")
                    continue
                declared_placeholders.add(value.strip()[2:-2].strip())

        # Every prompt must be a non-empty string
        for field in ("model_instructions", "selection_instructions", "description_instructions"):
            if field in recipe and not isinstance(recipe[field], str):
                errors.append(f"'{field}' must be a string")

        # Every placeholder used in a prompt must be resolvable
        known = declared_placeholders | self.RUNTIME_PLACEHOLDERS
        for field in ("model_instructions", "selection_instructions", "description_instructions"):
            prompt = recipe.get(field)
            if not isinstance(prompt, str):
                continue
            for token in re.findall(r'\{\{(MATH:)?\s*([A-Za-z_]\w*)\s*\}\}', prompt):
                is_math, name = token
                if is_math:
                    continue
                if name not in known:
                    errors.append(f"Placeholder '{{{{{name}}}}}' in {field} is not provided by user_parameters")

        # Math expressions must be evaluable
        for field in ("model_instructions", "selection_instructions", "description_instructions"):
            prompt = recipe.get(field)
            if not isinstance(prompt, str):
                continue
            for expression in re.findall(r'\{\{MATH:([^}]+)\}\}', prompt):
                candidate = expression.replace("DESIRED_TRACK_COUNT", "25")
                try:
                    result = eval(candidate, {"__builtins__": {}, **_SAFE_MATH_NAMES}, {})
                except Exception:
                    errors.append(f"Invalid math expression in {field}: {expression}")
                    continue
                if not isinstance(result, (int, float)):
                    errors.append(f"Math expression in {field} did not produce a number: {expression}")

        # LLM configs
        self._validate_llm_config(recipe, "llm_config", errors)
        self._validate_llm_config(recipe, "description_llm_config", errors)

        if "llm_config" not in recipe:
            errors.append("Missing required field: llm_config")

        # Optional numeric config blocks
        if "max_candidate_tracks" in recipe:
            limit = recipe["max_candidate_tracks"]
            if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
                errors.append("'max_candidate_tracks' must be a positive integer")

        for key in ("output_sorting", "source_filtering"):
            if key in recipe and not isinstance(recipe[key], dict):
                errors.append(f"'{key}' must be an object")

        if isinstance(recipe.get("output_sorting"), dict):
            for sort_key, value in recipe["output_sorting"].items():
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    errors.append(f"'output_sorting.{sort_key}' must be a non-negative integer")

        if isinstance(recipe.get("source_filtering"), dict):
            for ratio_key in ("exploration_ratio", "high_tier_ratio"):
                if ratio_key in recipe["source_filtering"]:
                    ratio = recipe["source_filtering"][ratio_key]
                    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or ratio < 0 or ratio > 1:
                        errors.append(f"'source_filtering.{ratio_key}' must be a number between 0 and 1")

        return errors

    def _validate_parameterized_format(self, recipe: Dict[str, Any]) -> List[str]:
        """Validate a recipe that declares its parameters via an 'inputs' list"""
        errors = []

        for field in ("version", "description", "inputs", "strategy_notes"):
            if field not in recipe:
                errors.append(f"Missing required field: {field}")

        inputs = recipe.get("inputs", [])
        if not isinstance(inputs, list):
            errors.append("'inputs' must be a list")
            inputs = []

        prompt_template = recipe.get("prompt_template")
        if prompt_template is not None:
            if not isinstance(prompt_template, str):
                errors.append("'prompt_template' must be a string")
            else:
                for placeholder in re.findall(r'\{(\w+)\}', prompt_template):
                    if placeholder not in inputs and placeholder not in ("tracks_data", "num_tracks"):
                        errors.append(f"Placeholder '{placeholder}' in prompt_template not found in inputs")

        if "prompt_template_with_description" in recipe and not isinstance(
            recipe["prompt_template_with_description"], str
        ):
            errors.append("'prompt_template_with_description' must be a string")

        if "llm_params" in recipe:
            llm_params = recipe["llm_params"]
            if not isinstance(llm_params, dict):
                errors.append("'llm_params' must be an object")
            else:
                if "temperature" in llm_params:
                    temp = llm_params["temperature"]
                    if isinstance(temp, bool) or not isinstance(temp, (int, float)) or temp < 0 or temp > 2:
                        errors.append("'llm_params.temperature' must be a number between 0 and 2")
                if "max_tokens" in llm_params:
                    tokens = llm_params["max_tokens"]
                    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
                        errors.append("'llm_params.max_tokens' must be a positive integer")

        return errors
    
    def clear_cache(self):
        """Clear the internal cache (useful for development/testing)"""
        self._registry_cache = None
        self._recipe_cache = {}

# Global instance for use throughout the application
recipe_manager = RecipeManager()