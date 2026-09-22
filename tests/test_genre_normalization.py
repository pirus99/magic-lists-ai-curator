from backend.navidrome.utils import _normalize_genres, _parse_genre_string


def test_parse_genre_string_supports_multiple_genres_and_spaces():
    assert _parse_genre_string("Hip Hop / Electronic") == ["Hip Hop", "Electronic"]
    assert _parse_genre_string("Rock, Pop") == ["Rock", "Pop"]
    assert _parse_genre_string("Techno & House") == ["Techno", "House"]


def test_normalize_genres_handles_list_of_dicts_and_strings():
    assert _normalize_genres([{"name": "Techno"}, {"name": "House"}]) == ["Techno", "House"]
    assert _normalize_genres([" Indie Rock ", "Pop"]) == ["Indie Rock", "Pop"]
    assert _normalize_genres(None) == []
