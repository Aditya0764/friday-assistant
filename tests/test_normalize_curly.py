from friday.router.router import Router, normalize
from friday.skills.registry import build_registry


def test_curly_apostrophes_become_plain_ones():
    assert normalize("What\u2019s 18% of 2,400?") == "what's 18% of 2400"
    assert normalize("\u2018hello\u2019 Friday") == "'hello' friday"


def test_phone_style_sentences_reach_the_right_skill(tmp_path):
    router = Router(build_registry(db_path=tmp_path / "r.db"))
    assert router.route("What\u2019s 18% of 2400?").skill.name == "calc"
    assert router.route("What\u2019s on my shopping list").skill.name == "lists"