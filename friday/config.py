"""Load Friday's settings from the .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class ConfigError(Exception):
    """Raised when a required setting is missing."""


@dataclass(frozen=True)
class Settings:
    groq_api_key: str = field(repr=False)
    gemini_api_key: str = field(default="", repr=False)
    telegram_bot_token: str = field(default="", repr=False)
    db_path: Path = ROOT / "data" / "friday.db"


def get_settings() -> Settings:
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise ConfigError("GROQ_API_KEY is missing. Add it to your .env file (see .env.example).")
    return Settings(
        groq_api_key=groq_key,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    )