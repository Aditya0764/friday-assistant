"""Router v1 (P6-02): the trained model after the rules. A fake classifier stands in for torch."""

from types import SimpleNamespace

import pytest

from friday import db
from friday.graph import build_graph, run_turn
from friday.router import model as model_module
from friday.router.router import Router
from friday.skills.registry import build_registry

NOBODY_TAKES_THIS = "zzz banana quantum"


class _FakeClassifier:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def classify(self, clean):
        self.calls.append(clean)
        return self.answer


class _FakeLLM:
    def __init__(self):
        self.calls = []

    def __call__(self, messages):
        self.calls.append(messages)
        return SimpleNamespace(text="stub reply", provider="stub", model="stub", ms=0)


@pytest.fixture
def conn(tmp_path):
    connection = db.connect(tmp_path / "test.db")
    yield connection
    connection.close()


def _route(answer, text=NOBODY_TAKES_THIS, threshold=0.9):
    classifier = _FakeClassifier(answer)
    route = Router(build_registry(), classifier=classifier, threshold=threshold).route(text)
    return route, classifier


def test_rules_win_over_the_model():
    route, classifier = _route(("doc_qa", 0.99), text="What time is it?")
    assert route.via == "rule"
    assert route.skill.name == "clock"
    assert classifier.calls == []  # the model is not even asked


def test_confident_doc_qa_runs_the_docs_skill():
    route, _ = _route(("doc_qa", 0.95))
    assert route.via == "model"
    assert route.skill.name == "docs"
    assert (route.model, route.conf) == ("doc_qa", 0.95)


def test_confident_other_skill_class_says_please_repeat():
    route, _ = _route(("math_time", 0.95))
    assert route.via == "model"
    assert route.skill.name == "catch"
    assert "say it again" in route.skill.run(route.args).lower()


def test_below_threshold_goes_to_the_llm_but_keeps_the_guess():
    route, _ = _route(("doc_qa", 0.80))
    assert route.skill is None
    assert route.via == "llm"
    assert (route.model, route.conf) == ("doc_qa", 0.80)


def test_threshold_is_inclusive():
    route, _ = _route(("music", 0.9))
    assert route.via == "model"


def test_other_goes_to_the_llm_even_when_sure():
    route, _ = _route(("other", 1.0))
    assert route.skill is None
    assert route.via == "llm"
    assert route.model == "other"


def test_model_not_ready_goes_to_the_llm():
    route, _ = _route(None)
    assert route.skill is None
    assert route.via == "llm"
    assert route.model == ""


def test_empty_sentence_never_reaches_the_model():
    route, classifier = _route(("music", 1.0), text="")
    assert route.skill is None
    assert classifier.calls == []


def test_no_classifier_is_the_old_behaviour():
    route = Router(build_registry()).route(NOBODY_TAKES_THIS)
    assert route.skill is None
    assert route.via == "llm"


def test_graph_model_path_skips_the_llm(conn):
    fake_llm = _FakeLLM()
    app = build_graph(conn, build_registry(), llm=fake_llm, classifier=_FakeClassifier(("math_time", 0.97)))
    state = run_turn(app, NOBODY_TAKES_THIS)
    assert state["via"] == "model"
    assert "say it again" in state["reply"].lower()
    steps = [row["step"] for row in db.get_traces(conn, state["run_id"])]
    assert steps == ["router", "safety", "skill", "reply"]
    assert fake_llm.calls == []


def test_graph_llm_path_logs_the_model_guess(conn):
    fake_llm = _FakeLLM()
    app = build_graph(conn, build_registry(), llm=fake_llm, classifier=_FakeClassifier(("other", 0.99)))
    state = run_turn(app, NOBODY_TAKES_THIS)
    assert state["via"] == "llm"
    assert len(fake_llm.calls) == 1
    rows = db.get_traces(conn, state["run_id"])
    assert [row["step"] for row in rows] == ["router", "llm", "reply"]
    assert "model other 0.99" in rows[0]["output"]


def test_default_classifier_is_off_without_the_flag(monkeypatch):
    monkeypatch.delenv(model_module.ENV_FLAG, raising=False)
    assert model_module.get_default_classifier() is None


def test_default_classifier_is_built_once_when_flagged(monkeypatch):
    monkeypatch.setenv(model_module.ENV_FLAG, "1")
    monkeypatch.setattr(model_module, "_shared", {})
    built = []

    class _Stub:
        def __init__(self):
            built.append(1)

    monkeypatch.setattr(model_module, "ModelClassifier", _Stub)
    first = model_module.get_default_classifier()
    second = model_module.get_default_classifier()
    assert first is second
    assert len(built) == 1