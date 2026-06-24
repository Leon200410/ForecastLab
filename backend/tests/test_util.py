"""extract_json hardening (A2): fences, surrounding prose, multiple objects,
trailing commas — the first candidate that parses to a dict wins, else None."""
from app.lib.util import extract_json


def test_plain_and_fenced():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_surrounding_prose_and_multiple_objects():
    assert extract_json('Here you go: {"a": 1}. Thanks!') == {"a": 1}
    # a stray non-JSON brace group is skipped; the first parseable object wins
    assert extract_json('note {not json} then {"probability": 0.4}') == {"probability": 0.4}


def test_trailing_comma_tolerated():
    assert extract_json('{"a": 1, "b": 2,}') == {"a": 1, "b": 2}


def test_unparseable_returns_none():
    assert extract_json("no json here") is None
    assert extract_json("") is None
    assert extract_json("{ not valid at all ") is None
