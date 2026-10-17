import pytest

from friday import db
from friday.router.router import Router, normalize
from friday.skills.lists import Action, ListsSkill, parse_action
from friday.skills.registry import build_registry


def _say(skill, sentence):
    return skill.run({"text": sentence, "clean": normalize(sentence)})


@pytest.fixture
def skill(tmp_path):
    return ListsSkill(tmp_path / "t.db")


def _items(tmp_path, list_name):
    conn = db.connect(tmp_path / "t.db")
    try:
        return [row["item"] for row in db.get_list_items(conn, list_name)]
    finally:
        conn.close()


def test_acceptance_a2_add_milk(skill, tmp_path):
    assert _say(skill, "Add milk to my shopping list.") == "Okay, I added milk to your shopping list."
    assert _items(tmp_path, "shopping") == ["milk"]


@pytest.mark.parametrize(
    "sentence",
    [
        "Add milk to my shopping list",
        "add milk to the shopping list",
        "Put milk on my shopping list",
        "Please add milk to shopping list",
        "Can you add milk to my shopping list?",
        "Add milk to my shopping list please",
    ],
)
def test_ways_to_say_add(skill, tmp_path, sentence):
    assert skill.can_handle(normalize(sentence))
    _say(skill, sentence)
    assert _items(tmp_path, "shopping") == ["milk"]


def test_several_items_in_one_sentence(skill, tmp_path):
    reply = _say(skill, "Add milk, eggs and bread to my shopping list.")
    assert _items(tmp_path, "shopping") == ["milk", "eggs", "bread"]
    assert reply == "Okay, I added milk, eggs and bread to your shopping list."


def test_two_items_with_and(skill, tmp_path):
    reply = _say(skill, "Add eggs and bread to my shopping list.")
    assert _items(tmp_path, "shopping") == ["eggs", "bread"]
    assert reply == "Okay, I added eggs and bread to your shopping list."


def test_no_list_name_uses_the_main_list(skill, tmp_path):
    assert _say(skill, "Add milk to my list.") == "Okay, I added milk to your list."
    assert _items(tmp_path, "main") == ["milk"]
    assert _say(skill, "What's on my list?") == "On your list: milk."


def test_item_with_the_word_to_inside(skill, tmp_path):
    _say(skill, "Add talk to mom to my todo list.")
    assert _items(tmp_path, "todo") == ["talk to mom"]


def test_to_do_spellings_share_one_list(skill, tmp_path):
    _say(skill, "Add call dad to my to do list.")
    _say(skill, "Add pay rent to my to-do list.")
    assert _items(tmp_path, "todo") == ["call dad", "pay rent"]


def test_duplicate_is_not_added_twice(skill, tmp_path):
    _say(skill, "Add milk to my shopping list.")
    assert _say(skill, "Add milk to my shopping list.") == "Milk is already on your shopping list."
    assert _items(tmp_path, "shopping") == ["milk"]


def test_mixed_new_and_duplicate(skill):
    _say(skill, "Add milk to my shopping list.")
    reply = _say(skill, "Add milk and eggs to my shopping list.")
    assert reply == "Okay, I added eggs to your shopping list. Milk was already there."


def test_lists_are_separate(skill, tmp_path):
    _say(skill, "Add milk to my shopping list.")
    _say(skill, "Add laptop to my packing list.")
    assert _items(tmp_path, "shopping") == ["milk"]
    assert _items(tmp_path, "packing") == ["laptop"]


@pytest.mark.parametrize(
    "sentence",
    [
        "What's on my shopping list?",
        "What is on my shopping list",
        "What do I have on my shopping list?",
        "Read my shopping list",
        "Read me my shopping list.",
        "Show me my shopping list",
        "Tell me what's on my shopping list",
    ],
)
def test_ways_to_ask(skill, sentence):
    _say(skill, "Add milk and eggs to my shopping list.")
    assert _say(skill, sentence) == "On your shopping list: milk and eggs."


def test_three_items_are_read_with_commas(skill):
    _say(skill, "Add milk to my shopping list.")
    _say(skill, "Add eggs to my shopping list.")
    _say(skill, "Add bread to my shopping list.")
    assert _say(skill, "What's on my shopping list?") == "On your shopping list: milk, eggs and bread."


def test_empty_list(skill):
    assert _say(skill, "What's on my shopping list?") == "Your shopping list is empty."


def test_long_list_is_read_in_part(skill):
    for number in range(1, 13):
        _say(skill, f"Add item{number} to my shopping list.")
    reply = _say(skill, "What's on my shopping list?")
    assert reply.endswith("item10, and 2 more.")
    assert "item11" not in reply


def test_remove_exact_and_partial(skill, tmp_path):
    _say(skill, "Add whole milk and eggs to my shopping list.")
    assert _say(skill, "Remove eggs from my shopping list.") == "Okay, I removed eggs from your shopping list."
    assert _say(skill, "Take milk off my shopping list.") == "Okay, I removed whole milk from your shopping list."
    assert _items(tmp_path, "shopping") == []


def test_remove_missing_item(skill):
    _say(skill, "Add milk to my shopping list.")
    assert _say(skill, "Remove bread from my shopping list.") == "I couldn't find bread on your shopping list."


def test_remove_ambiguous_partial_removes_nothing(skill, tmp_path):
    _say(skill, "Add oat milk and soy milk to my shopping list.")
    assert "couldn't find" in _say(skill, "Remove milk from my shopping list.")
    assert len(_items(tmp_path, "shopping")) == 2


def test_notes(skill, tmp_path):
    assert _say(skill, "Take a note that the demo is on Friday.") == "Okay, noted: the demo is on friday."
    _say(skill, "Make a note to call the bank.")
    assert _items(tmp_path, "notes") == ["the demo is on friday", "call the bank"]
    assert _say(skill, "What are my notes?") == "Your notes: the demo is on friday and call the bank."


def test_no_notes_yet(skill):
    assert _say(skill, "Read my notes") == "You don't have any notes yet."


def test_lists_survive_a_new_skill_object(tmp_path):
    _say(ListsSkill(tmp_path / "t.db"), "Add milk to my shopping list.")
    assert _say(ListsSkill(tmp_path / "t.db"), "What's on my shopping list?") == "On your shopping list: milk."


@pytest.mark.parametrize(
    "sentence",
    [
        "Add 2 and 3",
        "Add 5 to 7",
        "What's 18% of 2,400?",
        "What time is it?",
        "What's on my calendar?",
        "What's on my mind?",
        "Remind me to add milk to my list.",
        "Tell me a fun fact.",
        "Make a list of fun facts",
        "Add",
        "My shopping list is long",
    ],
)
def test_ordinary_sentences_are_not_claimed(sentence):
    assert parse_action(normalize(sentence)) is None


def test_router_sends_lists_to_the_lists_skill_not_math(tmp_path):
    router = Router(build_registry(db_path=tmp_path / "t.db"))
    route = router.route("Add 5 to my shopping list.")
    assert route.skill is not None
    assert route.skill.name == "lists"
    assert route.skill.run(route.args) == "Okay, I added 5 to your shopping list."
    assert router.route("What is 2 plus 3").skill.name == "calc"


def test_registry_has_the_lists_skill(tmp_path):
    assert "lists" in build_registry(db_path=tmp_path / "t.db").names()



@pytest.mark.parametrize(
    ("sentence", "action"),
    [
        ("I need to add rice and lentils to the grocery list", Action("add", "grocery", ("rice", "lentils"))),
        ("I'd like to put batteries on the hardware list", Action("add", "hardware", ("batteries",))),
        ("I want to add eggs and flour to my baking list", Action("add", "baking", ("eggs", "flour"))),
        ("read out the shopping list", Action("read", "shopping")),
        ("Can you read out my to-do list", Action("read", "todo")),
        ("read out my notes", Action("read", "notes")),
    ],
)
def test_lead_ins_and_read_out(sentence, action):
    assert parse_action(normalize(sentence)) == action


@pytest.mark.parametrize("sentence", ["I need to think about my list", "I need to read a book"])
def test_lead_in_does_not_claim_ordinary_sentences(sentence):
    assert parse_action(normalize(sentence)) is None
