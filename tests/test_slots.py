"""P6-03: slot extraction. A fake LLM returns JSON; the real skills parse the sentence we build."""

from types import SimpleNamespace

import pytest

from friday import db
from friday.graph import build_graph, run_turn
from friday.router.router import Router, normalize
from friday.router.slots import fill_slots
from friday.skills.registry import build_registry


class _Scheduler:
    def __init__(self):
        self.added = []

    def add(self, message, due):
        self.added.append((message, due))


class _Player:
    def __init__(self):
        self.calls = []

    def play(self, rest, title, artist):
        self.calls.append(("play", rest, title, artist))
        return "Blinding Lights"

    def next(self):
        self.calls.append(("next",))

    def pause(self):
        self.calls.append(("pause",))


class _Classifier:
    def __init__(self, answer):
        self.answer = answer

    def classify(self, clean):
        return self.answer


def _llm(reply_text):
    calls = []

    def fake(messages):
        calls.append(messages)
        return SimpleNamespace(text=reply_text, provider="stub", model="stub", ms=0)

    fake.calls = calls
    return fake


@pytest.fixture
def parts(tmp_path):
    scheduler, player = _Scheduler(), _Player()
    registry = build_registry(scheduler, tmp_path / "slots.db", player)
    return registry, scheduler, player


def _fill(registry, label, said, reply):
    return fill_slots(label, said, normalize(said), registry, _llm(reply))


def test_lists_add(parts):
    registry, _, _ = parts
    found = _fill(
        registry, "lists_notes", "pop milk on the shopping list for me",
        '{"action":"add","items":["milk"],"list":"shopping"}',
    )
    assert found is not None
    skill, args = found
    assert skill.name == "lists"
    assert args["clean"] == "add milk to my shopping list"
    reply = skill.run(args)
    assert "milk" in reply and "shopping" in reply


def test_lists_remove_read_and_note(parts):
    registry, _, _ = parts
    skill, args = _fill(
        registry, "lists_notes", "drop the eggs from the gym list",
        '{"action":"remove","items":["eggs"],"list":"gym"}',
    )
    assert args["clean"] == "remove eggs from my gym list"
    assert "eggs" in skill.run(args)
    skill, args = _fill(
        registry, "lists_notes", "what is left on my gym list",
        '{"action":"read","items":[],"list":"gym"}',
    )
    assert args["clean"] == "what's on my gym list"
    assert "gym" in skill.run(args)
    skill, args = _fill(
        registry, "lists_notes", "jot this down buy a gift",
        '{"action":"note","items":["buy a gift"],"list":""}',
    )
    assert args["clean"] == "take a note buy a gift"
    assert "buy a gift" in skill.run(args)


def test_reminder_timer_and_alarm(parts):
    registry, scheduler, _ = parts
    skill, args = _fill(
        registry, "timers_reminders", "nudge me at 9 pm to call mom",
        '{"kind":"reminder","task":"call mom","when":"at 9 pm"}',
    )
    assert args["clean"] == "remind me at 9 pm to call mom"
    assert "call mom" in skill.run(args)
    assert scheduler.added[-1][0] == "Reminder: call mom."
    skill, args = _fill(
        registry, "timers_reminders", "start the rice timer for 10 minutes",
        '{"kind":"timer","task":"","when":"10 minutes"}',
    )
    assert skill.run(args) == "Okay, timer set for 10 minutes."
    skill, args = _fill(
        registry, "timers_reminders", "wake me at 6:30 am",
        '{"kind":"alarm","task":"","when":"6:30 am"}',
    )
    assert args["clean"] == "set an alarm for 6 30 am"
    assert "alarm set" in skill.run(args)
    assert len(scheduler.added) == 3


def test_music_play_and_next(parts):
    registry, _, player = parts
    skill, args = _fill(
        registry, "music", "i want to hear blinding lights by the weekend",
        '{"action":"play","song":"blinding lights","artist":"the weekend"}',
    )
    assert args["clean"] == "play blinding lights by the weekend"
    assert skill.run(args) == "Playing Blinding Lights."
    assert player.calls[0] == ("play", "blinding lights by the weekend", "blinding lights", "the weekend")
    skill, args = _fill(registry, "music", "go to the next one", '{"action":"next"}')
    assert skill.run(args) == "Skipping."
    assert player.calls[-1] == ("next",)


def test_json_inside_a_code_fence_still_works(parts):
    registry, _, _ = parts
    reply = '```json\n{"action":"add","items":["milk"],"list":""}\n```'
    found = _fill(registry, "lists_notes", "pop milk on that list", reply)
    assert found is not None
    assert found[1]["clean"] == "add milk to my list"


@pytest.mark.parametrize(
    ("label", "said", "reply"),
    [
        ("lists_notes", "pop milk on the shopping list", '{"action":"add","items":["bread"],"list":"shopping"}'),
        ("lists_notes", "pop milk on that list", '{"action":"add","items":["milk"],"list":"shopping"}'),
        ("lists_notes", "pop milk on that list", '{"action":"add","items":"milk","list":""}'),
        ("lists_notes", "pop milk on that list", '{"action":"delete_all","items":[],"list":""}'),
        ("lists_notes", "pop milk on that list", '{"action":"none"}'),
        ("lists_notes", "pop milk on that list", "sure, done!"),
        ("timers_reminders", "nudge me to call mom later", '{"kind":"reminder","task":"call mom","when":"at 7 pm"}'),
        ("timers_reminders", "set it for soon", '{"kind":"timer","task":"","when":"soon"}'),
        ("timers_reminders", "ping me at 5 about milk", '{"kind":"reminder","task":"buy bread","when":"at 5"}'),
        ("music", "set the mood please", '{"action":"play","song":"the mood","artist":""}'),
        ("music", "play something", '{"action":"play","song":"","artist":""}'),
        ("music", "turn it up", '{"action":"none"}'),
    ],
)
def test_bad_or_made_up_slots_are_rejected(parts, label, said, reply):
    registry, _, _ = parts
    assert _fill(registry, label, said, reply) is None


def test_eleven_items_are_rejected(parts):
    registry, _, _ = parts
    items = ", ".join(f'"a{i}"' for i in range(11))
    said = "pop " + " ".join(f"a{i}" for i in range(11)) + " on that list"
    assert _fill(registry, "lists_notes", said, '{"action":"add","items":[' + items + '],"list":""}') is None


def test_llm_error_is_rejected(parts):
    registry, _, _ = parts

    def broken(messages):
        raise RuntimeError("down")

    assert fill_slots("music", "play x", "play x", registry, broken) is None


def test_missing_skill_is_rejected():
    registry = build_registry()  # no scheduler and no player: no reminders, no music
    assert _fill(registry, "music", "go to the next one", '{"action":"next"}') is None
    assert _fill(registry, "timers_reminders", "x", '{"kind":"timer","when":"5 minutes"}') is None


def test_router_marks_which_classes_get_slots(parts):
    registry, _, _ = parts
    music = Router(registry, _Classifier(("music", 0.95))).route("zzz banana quantum")
    assert (music.via, music.skill.name, music.slots_for) == ("model", "catch", "music")
    maths = Router(registry, _Classifier(("math_time", 0.95))).route("zzz banana quantum")
    assert (maths.skill.name, maths.slots_for) == ("catch", "")
    bare = Router(build_registry(), _Classifier(("timers_reminders", 0.95))).route("zzz banana quantum")
    assert bare.slots_for == ""  # no reminder skill in this registry


def test_graph_slots_path_runs_the_skill(parts, tmp_path):
    registry, _, player = parts
    conn = db.connect(tmp_path / "graph.db")
    fake = _llm('{"action":"play","song":"blinding lights","artist":"the weekend"}')
    app = build_graph(conn, registry, llm=fake, classifier=_Classifier(("music", 0.97)))
    state = run_turn(app, "zzz play blinding lights by the weekend please")
    assert state["reply"] == "Playing Blinding Lights."
    assert [row["step"] for row in db.get_traces(conn, state["run_id"])] == [
        "router", "slots", "safety", "skill", "reply",
    ]
    assert len(fake.calls) == 1  # one LLM call, for the details only
    assert player.calls[0][0] == "play"
    conn.close()


def test_graph_bad_slots_say_it_again_and_do_nothing(parts, tmp_path):
    registry, _, player = parts
    conn = db.connect(tmp_path / "graph.db")
    app = build_graph(conn, registry, llm=_llm("I cannot do that"), classifier=_Classifier(("music", 0.97)))
    state = run_turn(app, "zzz play blinding lights by the weekend please")
    assert "say it again" in state["reply"].lower()
    assert player.calls == []
    conn.close()

def test_hearing_counts_as_a_play_word(parts):
    registry, _, _ = parts
    found = _fill(
        registry, "music", "i feel like hearing believer by imagine dragons",
        '{"action":"play","song":"believer","artist":"imagine dragons"}',
    )
    assert found is not None
    assert found[1]["clean"] == "play believer by imagine dragons"


CAUGHT = "stick bread on the grocery list"  # the catch skill takes this one


def test_model_can_upgrade_a_catch_sentence_to_slots(parts):
    registry, _, _ = parts
    route = Router(registry, _Classifier(("lists_notes", 0.95))).route(CAUGHT)
    assert (route.via, route.skill.name, route.slots_for) == ("model", "catch", "lists_notes")


def test_model_never_sends_a_catch_sentence_to_the_llm(parts):
    registry, _, _ = parts
    for answer in (("other", 1.0), ("lists_notes", 0.5), ("math_time", 0.99), None):
        route = Router(registry, _Classifier(answer)).route(CAUGHT)
        assert route.skill.name == "catch"
        assert route.via == "rule"
        assert route.slots_for == ""


def test_graph_catch_sentence_gets_slots_and_runs_the_skill(parts, tmp_path):
    registry, _, _ = parts
    conn = db.connect(tmp_path / "graph.db")
    fake = _llm('{"action":"add","items":["bread"],"list":"grocery"}')
    app = build_graph(conn, registry, llm=fake, classifier=_Classifier(("lists_notes", 0.97)))
    state = run_turn(app, CAUGHT)
    assert "bread" in state["reply"] and "grocery" in state["reply"]
    assert [row["step"] for row in db.get_traces(conn, state["run_id"])] == [
        "router", "slots", "safety", "skill", "reply",
    ]
    conn.close()

@pytest.mark.parametrize("said_list", ["grocery", "grocery list", "the grocery list"])
def test_list_name_never_gets_a_second_list_word(parts, said_list):
    registry, _, _ = parts
    found = _fill(
        registry, "lists_notes", "stick bread on the grocery list",
        '{"action":"add","items":["bread"],"list":"' + said_list + '"}',
    )
    assert found is not None
    assert found[1]["clean"] == "add bread to my grocery list"