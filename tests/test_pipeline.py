"""Pipeline integration tests with a mocked Ollama client (no model needed)."""

from __future__ import annotations

import json
from pathlib import Path

from dentanote.config import Settings
from dentanote.extract import OllamaReply
from dentanote.metrics import load_metrics
from dentanote.pipeline import run_from_text
from dentanote.render import DRAFT_HEADER

VALID_NOTE = {
    "chief_complaint": "dor no dente 36",
    "history": None,
    "findings": ["cárie oclusal"],
    "teeth": [{"fdi_number": 36, "surfaces": ["O"], "note": None}],
    "procedures": [{"name": "restauração em resina", "tooth_fdi": [36], "details": None}],
    "materials_anesthesia": [],
    "medications_prescribed": [],
    "guidance_given": [],
    "follow_up": "retorno em 7 dias",
    "uncertain_items": [],
}


class FakeClient:
    def __init__(self, texts: list[str]) -> None:
        self.texts = texts
        self.calls = 0

    def chat(self, messages: list[dict[str, str]]) -> OllamaReply:
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return OllamaReply(
            text=text, prompt_tokens=10, completion_tokens=5, model="fake:1", latency_s=0.01
        )


def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, metrics_path=tmp_path / "metrics.jsonl")


def test_text_pipeline_end_to_end(tmp_path: Path) -> None:
    transcript = "Paciente Exemplo 01, dor no trinta e seis, feita restauração."
    result = run_from_text(
        transcript, settings(tmp_path), client=FakeClient([json.dumps(VALID_NOTE)])
    )
    assert result.note.teeth[0].fdi_number == 36
    assert result.rendered.startswith(DRAFT_HEADER)
    assert "restauração em resina" in result.rendered
    assert result.transcription is None
    assert result.metrics.source == "text"
    assert result.metrics.valid_first_try is True


def test_pipeline_records_metrics_without_transcript(tmp_path: Path) -> None:
    transcript = "Paciente Exemplo 07: fratura no dente 46"
    cfg = settings(tmp_path)
    run_from_text(transcript, cfg, client=FakeClient([json.dumps(VALID_NOTE)]))
    raw = cfg.metrics_path.read_text(encoding="utf-8")
    assert "Paciente Exemplo 07" not in raw
    assert "fratura" not in raw
    records = load_metrics(cfg.metrics_path)
    assert records and records[0]["transcript_chars"] == len(transcript)


def test_pipeline_can_skip_recording(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    run_from_text("texto", cfg, client=FakeClient([json.dumps(VALID_NOTE)]), record=False)
    assert not cfg.metrics_path.exists()


def test_pipeline_surfaces_warnings_instead_of_raising(tmp_path: Path) -> None:
    cfg = settings(tmp_path)
    result = run_from_text(
        "texto ambíguo", cfg, client=FakeClient(["resposta sem json"]), record=False
    )
    assert result.warnings
    assert result.rendered.startswith(DRAFT_HEADER)
    assert "⚠" in result.rendered  # uncertain block for the professional
