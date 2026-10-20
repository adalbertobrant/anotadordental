"""Runtime settings for DentaNote.

All settings are read from environment variables prefixed with ``DENTANOTE_``
(or from a local ``.env`` file, if present). No telemetry, no remote calls:
every default points at localhost.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Immutable-by-convention configuration, overridable via environment."""

    model_config = SettingsConfigDict(
        env_prefix="DENTANOTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # --- transcription (faster-whisper) -------------------------------------
    whisper_model: str = "small"
    whisper_device: Literal["auto", "cpu", "cuda"] = "auto"
    whisper_compute_type: str = "default"
    language: str = "pt"
    vad_filter: bool = True
    initial_prompt_enabled: bool = True

    # --- extraction (Ollama, localhost only) --------------------------------
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "gemma4:e4b"
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    max_repairs: int = Field(default=2, ge=0, le=5)
    request_timeout_s: float = Field(default=300.0, gt=0)
    # Gemma 4 is a "thinking" model; thinking can bypass the JSON schema in
    # some Ollama versions, so we force direct answers (ADR-001).
    think: bool = False

    # --- output / metrics ---------------------------------------------------
    metrics_path: Path = Path("metrics.jsonl")
    draft_banner: str = (
        "Rascunho gerado por IA local. Revise antes de salvar no prontuário. "
        "Nenhum dado sai deste computador."
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings object (cheap: settings are read once)."""
    return Settings()
