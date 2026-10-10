import pytest

from friday import config


def test_missing_groq_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(config.ConfigError, match="GROQ_API_KEY"):
        config.get_settings()


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    settings = config.get_settings()
    assert settings.groq_api_key == "test-groq"
    assert settings.gemini_api_key == "test-gemini"


def test_keys_are_hidden_in_repr(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "super-secret-value")
    assert "super-secret-value" not in repr(config.get_settings())