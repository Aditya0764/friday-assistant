from types import SimpleNamespace

from friday import db
from friday.graph import build_graph, run_turn
from friday.prompt import FRIDAY_PROMPT
from friday.skills.registry import build_registry


def _capture(tmp_path, **kwargs):
    seen = []

    def fake_llm(messages):
        seen.append(messages)
        return SimpleNamespace(text="hi there", provider="stub", model="stub", ms=0)

    conn = db.connect(tmp_path / "t.db")
    app = build_graph(conn, build_registry(db_path=tmp_path / "t.db"), llm=fake_llm, **kwargs)
    return app, seen, conn


def test_system_prompt_goes_first_then_history_then_the_user(tmp_path):
    app, seen, conn = _capture(tmp_path, system_prompt=FRIDAY_PROMPT)
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
    state = run_turn(app, "how are you", history)
    assert state["reply"] == "hi there"
    assert seen[0] == [
        {"role": "system", "content": FRIDAY_PROMPT},
        *history,
        {"role": "user", "content": "how are you"},
    ]
    conn.close()


def test_without_a_system_prompt_nothing_changes(tmp_path):
    app, seen, conn = _capture(tmp_path)
    run_turn(app, "how are you")
    assert seen[0] == [{"role": "user", "content": "how are you"}]
    conn.close()


def test_skills_never_reach_the_llm_or_its_prompt(tmp_path):
    app, seen, conn = _capture(tmp_path, system_prompt=FRIDAY_PROMPT)
    state = run_turn(app, "What is 2 plus 3?")
    assert seen == []
    assert state["via"] == "rule"
    conn.close()


def test_the_prompt_forbids_fake_actions_and_is_short():
    text = FRIDAY_PROMPT.lower()
    for phrase in ("never say or imply", "reminders", "music", "say it again"):
        assert phrase in text
    assert len(FRIDAY_PROMPT) < 1200