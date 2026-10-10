"""One swappable LLM interface. Groq first, Gemini as backup."""

import threading
import time
from dataclasses import dataclass

from groq import Groq

from friday.config import get_settings

GROQ_MODEL = "openai/gpt-oss-20b"
GEMINI_MODEL = "gemini-3.5-flash-lite"
GROQ_TIMEOUT_S = 15
GEMINI_TIMEOUT_S = 30


@dataclass(frozen=True)
class LLMReply:
    text: str
    provider: str
    model: str
    ms: int


def _call_groq(messages: list[dict]) -> str:
    client = Groq(api_key=get_settings().groq_api_key, timeout=GROQ_TIMEOUT_S)
    resp = client.chat.completions.create(model=GROQ_MODEL, messages=messages)
    return resp.choices[0].message.content or ""


def _call_gemini(messages: list[dict]) -> str:
    from google import genai

    api_key = get_settings().gemini_api_key
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing, so there is no backup available.")
    # Simple v1 approach: flatten the chat into one text prompt.
    prompt = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(model=GEMINI_MODEL, input=prompt)
    return interaction.output_text or ""


def _with_timeout(fn, seconds: float, *args):
    """Run fn in a background thread and give up after `seconds`."""
    box: dict = {}

    def runner():
        try:
            box["value"] = fn(*args)
        except Exception as exc:  # noqa: BLE001 - re-raised in the caller
            box["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise TimeoutError(f"{fn.__name__} took longer than {seconds} seconds")
    if "error" in box:
        raise box["error"]
    return box["value"]


def ask(messages: list[dict]) -> LLMReply:
    """Ask Groq; if it fails for any reason, fall back to Gemini."""
    start = time.perf_counter()
    try:
        text, provider, model = _call_groq(messages), "groq", GROQ_MODEL
    except Exception:  # noqa: BLE001 - any Groq failure should trigger the backup
        text = _with_timeout(_call_gemini, GEMINI_TIMEOUT_S, messages)
        provider, model = "gemini", GEMINI_MODEL
    ms = round((time.perf_counter() - start) * 1000)
    return LLMReply(text=text, provider=provider, model=model, ms=ms)