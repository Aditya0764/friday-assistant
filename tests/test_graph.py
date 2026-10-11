from types import SimpleNamespace

import pytest

from friday import db
from friday.graph import build_graph, run_turn
from friday.skills.base import Skill, SkillRegistry
from friday.skills.registry import build_registry


class _RiskySkill(Skill):
    name = "risky"
    needs_approval = True

    def can_handle(self, text):
        return text.startswith("do the risky thing")

    def run(self, args):
        return "done"


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


def _steps(conn, state):
    return [row["step"] for row in db.get_traces(conn, state["run_id"])]


def _risky_registry():
    registry = SkillRegistry()
    registry.register(_RiskySkill())
    return registry


def test_skill_path_writes_every_node(conn):
    fake = _FakeLLM()
    app = build_graph(conn, build_registry(), llm=fake)
    state = run_turn(app, "What time is it?")
    assert state["via"] == "rule"
    assert _steps(conn, state) == ["router", "safety", "skill", "reply"]
    assert fake.calls == []  # a skill answer never calls the LLM


def test_llm_path_writes_every_node(conn):
    fake = _FakeLLM()
    app = build_graph(conn, build_registry(), llm=fake)
    state = run_turn(app, "Tell me a joke.")
    assert state["via"] == "llm"
    assert state["reply"] == "stub reply"
    assert _steps(conn, state) == ["router", "llm", "reply"]
    assert len(fake.calls) == 1


def test_llm_gets_history_and_suffix(conn):
    fake = _FakeLLM()
    app = build_graph(conn, build_registry(), llm=fake, llm_suffix=" (short)")
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    run_turn(app, "Tell me a joke.", history=history)
    messages = fake.calls[0]
    assert messages[:2] == history
    assert messages[-1] == {"role": "user", "content": "Tell me a joke. (short)"}


def test_risky_skill_denied_without_approve(conn):
    app = build_graph(conn, _risky_registry(), approve=None, llm=_FakeLLM())
    state = run_turn(app, "Do the risky thing.")
    assert state["reply"] == "Okay, I won't do that."
    assert _steps(conn, state) == ["router", "safety", "reply"]


def test_risky_skill_runs_when_approved(conn):
    app = build_graph(conn, _risky_registry(), approve=lambda name: True, llm=_FakeLLM())
    state = run_turn(app, "Do the risky thing.")
    assert state["reply"] == "done"
    assert _steps(conn, state) == ["router", "safety", "skill", "reply"]


def test_approve_function_receives_skill_name(conn):
    asked = []

    def approve(name):
        asked.append(name)
        return False

    app = build_graph(conn, _risky_registry(), approve=approve, llm=_FakeLLM())
    run_turn(app, "Do the risky thing.")
    assert asked == ["risky"]


def test_each_run_gets_its_own_run_id(conn):
    app = build_graph(conn, build_registry(), llm=_FakeLLM())
    first = run_turn(app, "What time is it?")
    second = run_turn(app, "What time is it?")
    assert first["run_id"] != second["run_id"]