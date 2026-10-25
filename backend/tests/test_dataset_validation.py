"""Dataset import and validation."""

from __future__ import annotations

import json

from app.services.dataset_service import parse_csv, parse_json, validate_rows


def test_accepts_canonical_rows(sample_rows):
    cases, report = validate_rows(sample_rows)
    assert report.valid is True
    assert len(cases) == 3
    assert cases[0].tags == ["refund", "policy"]
    assert report.stats["with_ground_truth"] == 3


def test_maps_column_aliases():
    rows = [{"query": "What is X?", "expected answer": "X is Y.", "Passage": "X is Y."}]
    cases, report = validate_rows(rows)
    assert report.valid is True
    assert cases[0].question == "What is X?"
    assert cases[0].ground_truth == "X is Y."
    assert cases[0].context == "X is Y."


def test_rejects_rows_without_a_question():
    cases, report = validate_rows([{"ground_truth": "an answer with no question"}])
    assert cases == []
    assert report.valid is False
    assert report.errors[0].field == "question"


def test_flags_duplicates_as_warnings_not_errors():
    rows = [{"question": "Same question?"}, {"question": "same   QUESTION?"}]
    cases, report = validate_rows(rows)
    assert len(cases) == 2  # duplicates are kept, but surfaced
    assert any("Duplicate" in w.message for w in report.warnings)


def test_warns_when_ground_truth_missing():
    _, report = validate_rows([{"question": "Anything?"}])
    assert any(w.field == "ground_truth" for w in report.warnings)


def test_normalises_unknown_difficulty():
    cases, report = validate_rows([{"question": "Q?", "difficulty": "impossible"}])
    assert cases[0].difficulty == "medium"
    assert any(w.field == "difficulty" for w in report.warnings)


def test_empty_input_is_invalid():
    cases, report = validate_rows([])
    assert cases == [] and report.valid is False


def test_parse_csv_handles_semicolons():
    payload = b"question;ground_truth\nWhat is X?;X is Y\n"
    rows = parse_csv(payload)
    assert rows[0]["question"] == "What is X?"


def test_parse_json_accepts_wrapped_and_bare_lists():
    bare = json.dumps([{"question": "Q?"}]).encode()
    wrapped = json.dumps({"test_cases": [{"question": "Q?"}]}).encode()
    assert len(parse_json(bare)) == 1
    assert len(parse_json(wrapped)) == 1
