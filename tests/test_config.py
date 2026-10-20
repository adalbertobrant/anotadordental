"""Config tests: env overrides, defaults and privacy-safe defaults."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dentanote.config import Settings, get_settings


def test_defaults_are_local_only() -> None:
    settings = Settings(_env_file=None)
    assert settings.ollama_url.startswith(("http://localhost", "http://127.0.0.1"))
    assert settings.temperature <= 0.2
    assert settings.max_repairs == 2
    assert settings.language == "pt"
    assert settings.think is False


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DENTANOTE_LLM_MODEL", "gemma3:4b")
    monkeypatch.setenv("DENTANOTE_WHISPER_MODEL", "medium")
    settings = Settings(_env_file=None)
    assert settings.llm_model == "gemma3:4b"
    assert settings.whisper_model == "medium"


def test_invalid_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(max_repairs=-1, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(temperature=2.5, _env_file=None)


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
