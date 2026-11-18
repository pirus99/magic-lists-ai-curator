"""Central logging configuration for MagicLists.

One policy, four levels, applied to both the application's own log records and
the HTTP access log so that ``docker logs`` behaves predictably:

``ALL``
    Everything ``DEBUG`` shows, plus database driver logs (``aiosqlite`` /
    ``sqlite3``). Use this when a query or connection problem is suspected.

``DEBUG``
    Everything except database driver logs: application debug output, progress
    detail, third-party INFO records, and every HTTP request including
    successful ones.

``INFO``
    Everything except successful HTTP traffic and detailed status messages.
    Requests answered with a 2xx or 3xx status are dropped; 4xx and 5xx are
    kept. This is the default.

``ERROR``
    Only errors, plus a small set of startup messages that tell the operator the
    application came up at all. Everything else — progress, success, warnings,
    successful requests — is suppressed.

Anything else (including ``WARNING``) falls back to ``INFO`` so a typo in
``LOG_LEVEL`` never silences the log.

The module is deliberately dependency-free so it can be imported from
``backend.main`` before any other backend module is loaded.
"""
import logging
import os
import sys
from typing import Any, Optional

#: Environment variable that selects the log level.
LOG_LEVEL_ENV = "LOG_LEVEL"

#: Default level when the variable is unset or unrecognised.
DEFAULT_LEVEL_NAME = "INFO"

#: Policies the application supports. ``WARNING`` is intentionally absent: it is
#: not a meaningful policy for this app (it would hide errors' context while
#: still printing every recoverable problem), so it resolves to ``INFO``.
SUPPORTED_LEVELS = ("ALL", "DEBUG", "INFO", "ERROR")

#: Log format shared by every handler.
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"

#: ``extra`` key used to mark records that must survive ``LOG_LEVEL=ERROR``.
STARTUP_FLAG = "startup"

#: Third-party loggers and the level they get when the app runs at DEBUG or ALL.
#: At INFO and ERROR they are pinned to WARNING so their chatter stays out.
_DEBUG_LEVEL_LOGGERS = ("httpx", "httpcore", "apscheduler")

#: Database driver loggers. They are only enabled at ``ALL``: at ``DEBUG`` the
#: per-query noise would drown out the application's own debug output.
_DATABASE_LOGGERS = ("aiosqlite", "sqlite3")

#: Loggers that must never emit their own records: uvicorn's access log is
#: replaced by :func:`access_level` + the middleware in ``backend.main``.
_SILENCED_LOGGERS = ("uvicorn.access",)

#: Loggers that should hand their records to the root logger so the unified
#: format and the level policy apply to them.
_PROPAGATING_LOGGERS = ("uvicorn", "uvicorn.error")

#: Uvicorn logs its lifecycle messages through ``uvicorn.error``, which reads as
#: a failure in the output even though the records are INFO. Rename them so the
#: log line says ``uvicorn``.
_LOGGER_NAME_ALIASES = {"uvicorn.error": "uvicorn"}

_configured = False
_active_policy = DEFAULT_LEVEL_NAME


def resolve_policy(raw: Optional[str]) -> str:
    """Return the canonical policy name for a ``LOG_LEVEL`` value.

    Args:
        raw: The raw environment value. ``None`` or an empty string means
            "use the default".

    Returns:
        One of ``ALL``, ``DEBUG``, ``INFO`` or ``ERROR``. Unrecognised values
        (including ``WARNING``) resolve to ``INFO``.
    """
    name = (raw or "").strip().upper()
    if name in SUPPORTED_LEVELS:
        return name
    return DEFAULT_LEVEL_NAME


def resolve_level(raw: Optional[str]) -> int:
    """Translate a ``LOG_LEVEL`` value into a :mod:`logging` level.

    ``ALL`` and ``DEBUG`` both map to ``logging.DEBUG``; they differ only in
    whether database driver loggers are enabled (see :func:`configure_logging`).
    """
    policy = resolve_policy(raw)
    if policy in ("ALL", "DEBUG"):
        return logging.DEBUG
    if policy == "ERROR":
        return logging.ERROR
    return logging.INFO


def level_name(level: int) -> str:
    """Return the canonical name for a resolved level."""
    return logging.getLevelName(level)


def active_policy_name() -> str:
    """Return the policy name used by the most recent :func:`configure_logging`."""
    return _active_policy


def access_level(status_code: int) -> int:
    """Return the log level an HTTP response should be recorded at.

    Successful and redirected responses are only interesting when debugging;
    client errors are worth a warning; server errors are errors.
    """
    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.DEBUG


class LevelPolicyFilter(logging.Filter):
    """Enforce the ``LOG_LEVEL=ERROR`` policy on a handler.

    At ``ERROR`` the root logger still runs at ``INFO`` so that startup records
    can reach this filter; the filter then drops everything that is neither an
    error nor explicitly flagged as a startup message. At every other level the
    filter is a no-op and the logger's own level does the work.
    """

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level

    def filter(self, record: logging.LogRecord) -> bool:
        if self.level < logging.ERROR:
            return True
        if record.levelno >= logging.ERROR:
            return True
        return bool(getattr(record, STARTUP_FLAG, False))


class LoggerNameAliasFilter(logging.Filter):
    """Rewrite misleading logger names before formatting.

    Uvicorn emits its lifecycle messages ("Started server process", "Application
    startup complete") through a logger called ``uvicorn.error``. The records are
    INFO, so the name reads as a failure. Renaming them to ``uvicorn`` keeps the
    output honest without touching uvicorn itself.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        alias = _LOGGER_NAME_ALIASES.get(record.name)
        if alias:
            record.name = alias
        return True


def log_startup(logger: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
    """Log a startup message that survives ``LOG_LEVEL=ERROR``.

    Startup messages are the only non-error output an operator sees at the
    strictest level, so they must be emitted at ``INFO`` (never ``DEBUG``) and
    carry the :data:`STARTUP_FLAG` marker.
    """
    extra = dict(kwargs.pop("extra", None) or {})
    extra[STARTUP_FLAG] = True
    logger.info(message, *args, extra=extra, **kwargs)


def configure_logging(raw_level: Optional[str] = None) -> int:
    """Configure the root logger and third-party loggers.

    Idempotent: calling it twice replaces the handler instead of stacking a
    second one, so a reload or a test that reconfigures logging does not
    duplicate every line.

    Args:
        raw_level: Override for the ``LOG_LEVEL`` environment variable. When
            omitted the variable is read (default ``INFO``).

    Returns:
        The resolved :mod:`logging` level.
    """
    global _configured, _active_policy

    if raw_level is None:
        raw_level = os.getenv(LOG_LEVEL_ENV, DEFAULT_LEVEL_NAME)
    policy = resolve_policy(raw_level)
    level = resolve_level(raw_level)

    root = logging.getLogger()

    # Replace handlers rather than adding to them so repeated calls (reloads,
    # tests) cannot duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # noqa: BLE001 - closing a handler must never fail setup
            pass

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(LoggerNameAliasFilter())
    handler.addFilter(LevelPolicyFilter(level))
    root.addHandler(handler)

    # At ERROR the root logger must stay at INFO so startup records reach the
    # filter; the filter is what enforces the policy.
    root.setLevel(logging.INFO if level == logging.ERROR else level)

    # Third-party noise: verbose only when the app itself is verbose.
    third_party_level = logging.INFO if level == logging.DEBUG else logging.WARNING
    for name in _DEBUG_LEVEL_LOGGERS:
        logging.getLogger(name).setLevel(third_party_level)

    # Database driver logs are opt-in: only ``ALL`` enables them. At ``DEBUG``
    # the per-query output would bury the application's own debug messages.
    database_level = logging.DEBUG if policy == "ALL" else logging.WARNING
    for name in _DATABASE_LOGGERS:
        logging.getLogger(name).setLevel(database_level)

    # Uvicorn's own loggers must not keep their default handlers, or the
    # unified format and the level policy would not apply to them.
    for name in _PROPAGATING_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)

    for name in _SILENCED_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = False
        logger.disabled = True

    _configured = True
    _active_policy = policy
    return level


def is_configured() -> bool:
    """Return ``True`` once :func:`configure_logging` has run."""
    return _configured
