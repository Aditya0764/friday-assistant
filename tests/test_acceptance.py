from pathlib import Path

import yaml

ACCEPTANCE = Path(__file__).resolve().parents[1] / "evals" / "acceptance.yaml"


def _load():
    return yaml.safe_load(ACCEPTANCE.read_text(encoding="utf-8"))


def test_acceptance_file_has_at_least_three_tests():
    assert len(_load()["tests"]) >= 3


def test_every_test_has_id_sentence_and_expected_result():
    for test in _load()["tests"]:
        assert test["id"]
        assert test["say"].strip()
        assert test["expected"]


def test_ids_are_unique():
    ids = [test["id"] for test in _load()["tests"]]
    assert len(ids) == len(set(ids))