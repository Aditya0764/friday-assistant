"""Router v1 (P6-02): the trained model after the rules. A fake classifier stands in for torch."""

import builtins
import functools
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


@pytest.fixture
def built(monkeypatch):
    """Stub ModelClassifier (no torch) and record how many were built."""
    monkeypatch.setattr(model_module, "_shared", {})
    made = []

    class _Stub:
        def __init__(self):
            made.append(1)

    monkeypatch.setattr(model_module, "ModelClassifier", _Stub)
    return made


def test_default_classifier_is_on_without_the_flag(monkeypatch, built):
    monkeypatch.delenv(model_module.ENV_FLAG, raising=False)
    assert model_module.get_default_classifier() is not None
    assert len(built) == 1


@pytest.mark.parametrize("value", ["0", "false", "off", "no", " OFF ", "False"])
def test_flag_zero_and_friends_turn_it_off(monkeypatch, built, value):
    monkeypatch.setenv(model_module.ENV_FLAG, value)
    assert model_module.get_default_classifier() is None
    assert built == []


@pytest.mark.parametrize("value", ["1", "true", "on", "", "maybe"])
def test_flag_one_empty_or_anything_else_is_on(monkeypatch, built, value):
    monkeypatch.setenv(model_module.ENV_FLAG, value)
    assert model_module.get_default_classifier() is not None
    assert len(built) == 1


def test_default_classifier_is_built_once(monkeypatch, built):
    monkeypatch.setenv(model_module.ENV_FLAG, "1")
    first = model_module.get_default_classifier()
    second = model_module.get_default_classifier()
    assert first is second
    assert len(built) == 1


def _no_torch(monkeypatch):
    """Importing torch or transformers fails the test: they must not even be tried."""
    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in ("torch", "transformers"):
            raise AssertionError(f"{name} was imported")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_missing_model_files_fall_back_with_one_log_line(tmp_path, monkeypatch, capsys):
    _no_torch(monkeypatch)
    clf = model_module.ModelClassifier(model_dir=tmp_path / "nope", background=False)
    assert clf.ready is False and clf.error == "ModelNotFound"
    assert clf.classify("what all is on my shopping list") is None
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "rules + LLM" in lines[0] and "FRIDAY_ROUTER_MODEL=0" in lines[0]


def test_unreadable_model_files_fall_back_without_a_crash(tmp_path, monkeypatch, capsys):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")  # there, but not a real model

    real_import = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in ("torch", "transformers"):
            raise OSError("cannot read the model")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)
    clf = model_module.ModelClassifier(model_dir=tmp_path, background=False)
    assert clf.ready is False and clf.error == "OSError"
    assert clf.classify("add milk") is None
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "rules + LLM" in lines[0]


def test_default_with_missing_model_logs_once_and_the_graph_uses_the_llm(
    conn, tmp_path, monkeypatch, capsys
):
    _no_torch(monkeypatch)
    monkeypatch.delenv(model_module.ENV_FLAG, raising=False)
    monkeypatch.setattr(model_module, "_shared", {})
    monkeypatch.setattr(  # the real class, pointed at a missing folder, loading in-line
        model_module,
        "ModelClassifier",
        functools.partial(model_module.ModelClassifier, tmp_path / "nope", background=False),
    )
    fake_llm = _FakeLLM()
    for _ in range(2):  # two graphs, like the API building one per turn
        app = build_graph(conn, build_registry(), llm=fake_llm)
        state = run_turn(app, NOBODY_TAKES_THIS)
    assert state["via"] == "llm" and len(fake_llm.calls) == 2
    assert capsys.readouterr().out.count("Router model not found") == 1