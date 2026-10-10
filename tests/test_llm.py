import time

import pytest

from friday import llm

MESSAGES = [{"role": "user", "content": "hello"}]


def test_uses_groq_when_it_works(monkeypatch):
    monkeypatch.setattr(llm, "_call_groq", lambda messages: "from groq")
    reply = llm.ask(MESSAGES)
    assert reply.text == "from groq"
    assert reply.provider == "groq"
    assert reply.model == llm.GROQ_MODEL


def test_falls_back_to_gemini_when_groq_fails(monkeypatch):
    def broken(messages):
        raise RuntimeError("groq down")

    monkeypatch.setattr(llm, "_call_groq", broken)
    monkeypatch.setattr(llm, "_call_gemini", lambda messages: "from gemini")
    reply = llm.ask(MESSAGES)
    assert reply.text == "from gemini"
    assert reply.provider == "gemini"
    assert reply.model == llm.GEMINI_MODEL


def test_timeout_helper_gives_up():
    def slow():
        time.sleep(2)

    with pytest.raises(TimeoutError):
        llm._with_timeout(slow, 0.1)


def test_timeout_helper_passes_errors_through():
    def broken():
        raise ValueError("bad")

    with pytest.raises(ValueError):
        llm._with_timeout(broken, 1)