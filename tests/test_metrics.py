"""Metrics tests: JSONL round-trip and the hard no-PHI guarantee."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dentanote.metrics import (
    FORBIDDEN_METRIC_KEYS,
    RunMetrics,
    load_metrics,
    make_metrics,
    new_run_id,
    record_metrics,
)


def sample_metrics() -> RunMetrics:
    return make_metrics(
        source="text",
        llm_model="gemma4:e4b",
        whisper_model=None,
        audio_duration_s=None,
        transcription_s=None,
        extraction_s=1.234,
        total_s=1.5,
        prompt_tokens=1000,
        completion_tokens=150,
        repair_attempts=0,
        valid_first_try=True,
        transcript_chars=900,
        note_chars=600,
        uncertain_count=1,
        warnings_count=0,
    )


def test_record_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    metrics = sample_metrics()
    record_metrics(path, metrics)
    record_metrics(path, sample_metrics())
    records = load_metrics(path)
    assert len(records) == 2
    assert records[0]["run_id"] == metrics.run_id
    assert records[0]["llm_model"] == "gemma4:e4b"
    assert records[0]["tokens_per_s"] > 0


def test_metrics_record_has_no_clinical_text_fields() -> None:
    record = sample_metrics().to_record()
    assert not (FORBIDDEN_METRIC_KEYS & record.keys())
    serialized = json.dumps(record, ensure_ascii=False)
    for clinical_word in ("cárie", "dor", "restauração", "Paciente"):
        assert clinical_word not in serialized


def test_record_metrics_refuses_forbidden_keys(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    bogus = {
        "run_id": new_run_id(),
        "timestamp": "2026-01-01T00:00:00+00:00",
        "source": "text",
        "llm_model": "x",
        "whisper_model": None,
        "audio_duration_s": None,
        "transcription_s": None,
        "extraction_s": 1.0,
        "total_s": 1.0,
        "prompt_tokens": 1,
        "completion_tokens": 1,
        "repair_attempts": 0,
        "valid_first_try": True,
        "transcript_chars": 10,
        "note_chars": 10,
        "uncertain_count": 0,
        "warnings_count": 0,
        "transcript": "Paciente Exemplo 01 tem dor",  # PHI leak attempt
    }
    with pytest.raises(ValueError, match="forbidden keys"):
        record_metrics(path, bogus)
    assert not path.exists()


def test_load_metrics_missing_file(tmp_path: Path) -> None:
    assert load_metrics(tmp_path / "nope.jsonl") == []


def test_load_metrics_ignores_corrupt_lines(tmp_path: Path) -> None:
    path = tmp_path / "metrics.jsonl"
    path.write_text('{"run_id": "a", "total_s": 1.0}\nnot-json\n\n', encoding="utf-8")
    assert len(load_metrics(path)) == 1
