"""LangGraph pipeline: router -> safety -> skill -> reply (or router -> llm -> reply).

Every node writes one trace row (input, output, ms) under the same run_id.
- router: rules first (friday.router.router). If no rule matches and the trained model is on
  (on by default; FRIDAY_ROUTER_MODEL=0 turns it off), it guesses: a confident doc_qa runs the docs skill, a confident
  lists/reminders/music goes to the slots node, another skill class answers "please say it
  again", the rest goes to the LLM. The model's guess is written into the router trace row,
  e.g. "llm: llm [model other 0.99]".
- slots: asks the LLM for the details (item, time, song) as JSON, checks them, and hands the
  skill a plain sentence its own rules accept. If anything fails, the router's "please say it
  again" stays. The LLM never acts or speaks here (friday.router.slots).
- safety: a skill with needs_approval=True only runs if approve(skill_name) says yes.
  With no approve function, risky skills are denied.
- skill / llm: produce the reply text. The llm node sends the system prompt first (if
  one is given), then the chat history, then the user's sentence.
- reply: final node (the caller speaks or shows state["reply"]).

Saving messages and memory stay with the caller (voice loop), not the graph.
Run `python -m friday.graph` for the self-test (no network, uses a stub LLM).
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from friday.llm import ask
from friday.router.model import DEFAULT_THRESHOLD, get_default_classifier
from friday.router.router import Router
from friday.router.slots import fill_slots
from friday.skills.base import SkillRegistry
from friday.trace import Tracer

_UNSET = object()


class State(TypedDict, total=False):
    run_id: str
    text: str
    history: list[dict]
    args: dict[str, str]
    via: str  # "rule", "model" or "llm"
    skill_name: str
    slots_for: str  # router class whose slots the slots node should fill, else ""
    approved: bool
    reply: str
    provider: str


def build_graph(
    conn: sqlite3.Connection,
    registry: SkillRegistry,
    approve: Callable[[str], bool] | None = None,
    llm: Callable = ask,
    llm_suffix: str = "",
    system_prompt: str = "",
    classifier=_UNSET,
    threshold: float = DEFAULT_THRESHOLD,
):
    """Compile the graph.

    system_prompt: who Friday is and what it must not claim (sent first to the LLM).
    llm_suffix: optional text appended to the user's sentence (kept for old callers).
    classifier: the trained router. Left out, it is the shared model unless FRIDAY_ROUTER_MODEL=0
        (then None: rules + LLM only). Pass None to force it off.
    """
    if classifier is _UNSET:
        classifier = get_default_classifier()
    router = Router(registry, classifier=classifier, threshold=threshold)

    def tracer_for(state: State) -> Tracer:
        return Tracer(conn, state["run_id"])

    def router_node(state: State) -> dict:
        with tracer_for(state).step("router", state["text"]) as out:
            route = router.route(state["text"])
            name = route.skill.name if route.skill else ""
            shown = f"{route.via}: {name or 'llm'}"
            if route.model:
                shown += f" [model {route.model} {route.conf:.2f}]"
            out["output"] = shown
        return {
            "args": route.args,
            "via": route.via,
            "skill_name": name,
            "slots_for": route.slots_for,
        }

    def after_router(state: State) -> str:
        if state["via"] not in ("rule", "model"):
            return "llm"
        return "slots" if state.get("slots_for") else "safety"

    def slots_node(state: State) -> dict:
        label = state["slots_for"]
        with tracer_for(state).step("slots", f"{label}: {state['text']}") as out:
            found = fill_slots(label, state["text"], state["args"]["clean"], registry, llm)
            if found is None:
                out["output"] = "no valid slots: asking to say it again"
                return {}
            skill, args = found
            out["output"] = f"{skill.name}: {args['text']}"
        return {"skill_name": skill.name, "args": args}

    def safety_node(state: State) -> dict:
        skill = registry.get(state["skill_name"])
        with tracer_for(state).step("safety", state["skill_name"]) as out:
            if skill is None or not skill.needs_approval:
                approved = skill is not None
                out["output"] = "no approval needed" if approved else "unknown skill, denied"
            else:
                approved = bool(approve and approve(skill.name))
                out["output"] = "approved" if approved else "denied"
        update: dict = {"approved": approved}
        if not approved:
            update["reply"] = "Okay, I won't do that."
        return update

    def after_safety(state: State) -> str:
        return "skill" if state["approved"] else "reply"

    def skill_node(state: State) -> dict:
        skill = registry.get(state["skill_name"])
        with tracer_for(state).step("skill", state["skill_name"]) as out:
            reply = skill.run(state["args"])
            out["output"] = reply
        return {"reply": reply}

    def llm_node(state: State) -> dict:
        user_text = state["text"] + llm_suffix
        history = state.get("history", [])
        messages = [*history, {"role": "user", "content": user_text}]
        if system_prompt:
            messages = [{"role": "system", "content": system_prompt}, *messages]
        with tracer_for(state).step("llm", f"[{len(history)} history msgs] {state['text']}") as out:
            result = llm(messages)
            out["output"] = f"{result.provider}/{result.model}: {result.text}"
        return {"reply": result.text, "provider": result.provider}

    def reply_node(state: State) -> dict:
        reply = state.get("reply", "")
        with tracer_for(state).step("reply", reply) as out:
            out["output"] = "ready"
        return {"reply": reply}

    graph = StateGraph(State)
    graph.add_node("router", router_node)
    graph.add_node("slots", slots_node)
    graph.add_node("safety", safety_node)
    graph.add_node("skill", skill_node)
    graph.add_node("llm", llm_node)
    graph.add_node("reply", reply_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", after_router, {"safety": "safety", "slots": "slots", "llm": "llm"}
    )
    graph.add_edge("slots", "safety")
    graph.add_conditional_edges("safety", after_safety, {"skill": "skill", "reply": "reply"})
    graph.add_edge("skill", "reply")
    graph.add_edge("llm", "reply")
    graph.add_edge("reply", END)
    return graph.compile()


def run_turn(app, text: str, history: list[dict] | None = None) -> State:
    """Run one command through the graph. Returns the final state (has reply, run_id)."""
    return app.invoke({"run_id": uuid.uuid4().hex[:12], "text": text, "history": history or []})


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    from types import SimpleNamespace

    from friday import db
    from friday.skills.base import Skill

    class RepeatSkill(Skill):
        name = "repeat"

        def can_handle(self, text: str) -> bool:
            return text.startswith("repeat after me")

        def run(self, args: dict[str, str]) -> str:
            return args["clean"].removeprefix("repeat after me").strip()

    class DeleteSkill(Skill):
        name = "delete"
        needs_approval = True

        def can_handle(self, text: str) -> bool:
            return text.startswith("delete everything")

        def run(self, args: dict[str, str]) -> str:
            return "Deleted (pretend)."

    def fake_llm(messages: list[dict]) -> SimpleNamespace:
        return SimpleNamespace(text="(stub LLM reply)", provider="stub", model="stub", ms=0)

    registry = SkillRegistry()
    registry.register(RepeatSkill())
    registry.register(DeleteSkill())

    with tempfile.TemporaryDirectory() as tmp:
        conn = db.connect(Path(tmp) / "graph_test.db")
        deny_app = build_graph(conn, registry, approve=None, llm=fake_llm, classifier=None)
        yes_app = build_graph(conn, registry, approve=lambda name: True, llm=fake_llm, classifier=None)

        cases = [
            ("deny", deny_app, "Repeat after me, hello Friday."),
            ("deny", deny_app, "Tell me a joke."),
            ("deny", deny_app, "Delete everything."),
            ("yes", yes_app, "Delete everything."),
        ]
        for label, app, sentence in cases:
            state = run_turn(app, sentence)
            steps = [t["step"] for t in db.get_traces(conn, state["run_id"])]
            print(f"[approve={label}] {sentence!r}")
            print(f"    reply: {state['reply']!r}")
            print(f"    trace: {' -> '.join(steps)}")
        conn.close()