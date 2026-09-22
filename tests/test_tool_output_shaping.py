"""Shaping a long tool output: JSON stays parseable, every key survives, numbers are never
rewritten, and anything that is not JSON still gets cut the old way."""

import json

from my_agent_crew.texts import OUTPUT_SHAPED_NOTE
from my_agent_crew.tools.output_shaping import shape_json, shape_output


def test_output_under_the_cap_is_returned_untouched():
    result = shape_output("ngắn", 1000)
    assert result.text == "ngắn"
    assert result.kind == "none" and result.shaped is False
    assert result.original_chars == 4


def test_long_json_stays_parseable_after_shaping():
    """The whole point: the old character cut produced a fragment that no longer parsed,
    so the model could not read the last key."""
    payload = {"rows": [{"id": i, "note": "x" * 200} for i in range(100)]}
    text = json.dumps(payload, ensure_ascii=False)
    result = shape_output(text, 2000)
    assert result.kind == "json"
    assert len(result.text) <= 2000
    body = result.text[: -len(OUTPUT_SHAPED_NOTE)]
    json.loads(body)  # raises if shaping broke the structure


def test_every_top_level_key_survives_shaping():
    """A missing key reads as 'this data does not exist', which is a different and worse
    message than 'this data was shortened'."""
    payload = {
        "agenda": {"ok": True, "data": "a" * 4000},
        "mail": {"ok": True, "data": "b" * 4000},
        "books": {"ok": False, "error": "c" * 4000},
    }
    result = shape_output(json.dumps(payload, ensure_ascii=False), 1500)
    assert result.kind == "json"
    body = json.loads(result.text[: -len(OUTPUT_SHAPED_NOTE)])
    assert sorted(body) == ["agenda", "books", "mail"]
    assert body["books"]["ok"] is False


def test_numbers_and_booleans_are_never_rewritten():
    """Ledger and health figures pass through here. A wrong number is worse than a missing
    row, because a missing row is visibly missing."""
    payload = {
        "balance": 123456789,
        "rate": 4.875,
        "closed": False,
        "filler": ["z" * 500 for _ in range(50)],
    }
    result = shape_output(json.dumps(payload, ensure_ascii=False), 1200)
    body = json.loads(result.text[: -len(OUTPUT_SHAPED_NOTE)])
    assert body["balance"] == 123456789
    assert body["rate"] == 4.875
    assert body["closed"] is False


def test_a_long_array_keeps_its_head_and_says_how_many_it_dropped():
    payload = [{"i": i} for i in range(500)]
    result = shape_output(json.dumps(payload), 800)
    body = json.loads(result.text[: -len(OUTPUT_SHAPED_NOTE)])
    assert body[0] == {"i": 0}
    assert "phần tử nữa" in str(body[-1])


def test_plain_text_falls_back_to_a_plain_cut():
    result = shape_output("khong phai json " * 500, 300)
    assert result.kind == "cut"
    assert len(result.text) <= 300
    assert "đã cắt bớt" in result.text


def test_json_that_is_only_a_number_is_cut_not_shaped():
    """A bare scalar has no structure to trade away, so shaping it would be a lie."""
    assert shape_json("12345", 10) is None


def test_broken_json_is_cut_rather_than_rejected():
    result = shape_output('{"a": [1, 2, 3' + "0" * 900, 200)
    assert result.kind == "cut"
    assert len(result.text) <= 200


def test_a_tiny_cap_still_returns_something_within_it():
    result = shape_output(json.dumps({"a": ["x" * 100] * 50}), 50)
    assert len(result.text) <= 50
    assert result.original_chars > 50


def test_nothing_shaping_returns_is_ever_longer_than_the_cap():
    """The one promise the whole module makes. A cap is what an agent's profile bought;
    a result that overshoots it by the length of its own marker is not a cap at all."""
    cases = [
        json.dumps({"rows": [{"i": i, "text": "y" * 200} for i in range(300)]}),
        json.dumps(["z" * 500 for _ in range(200)]),
        "văn bản thường " * 4000,
        '{"broken": [1, 2' + "9" * 5000,
        "x" * 50_000,
    ]
    for limit in (40, 100, 199, 200, 512, 2000):
        for text in cases:
            result = shape_output(text, limit)
            assert len(result.text) <= limit, (limit, result.kind, len(result.text))


def test_the_shaped_output_reports_the_original_size():
    text = json.dumps({"rows": ["y" * 100 for _ in range(80)]})
    result = shape_output(text, 900)
    assert result.original_chars == len(text)
    assert result.shaped is True
