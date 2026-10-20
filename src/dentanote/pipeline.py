"""Pipeline orchestration: audio/text -> transcription -> extraction -> draft.

The pipeline is the only place where the pieces meet. It guarantees:

* the user always gets a draft plus warnings, never a raw exception;
* metrics for every run are appended to ``metrics.jsonl`` without any clinical
  text (sizes, timings, tokens, models only).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from dentanote.config import Settings, get_settings
from dentanote.extract import ExtractionResult, OllamaClient, extract_note
from dentanote.metrics import RunMetrics, make_metrics, record_metrics
from dentanote.render import render_note
from dentanote.schema import ClinicalNote
from dentanote.transcribe import TranscriptionResult, transcribe_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """Everything a caller (CLI/UI) needs to present a reviewable draft."""

    transcript: str
    note: ClinicalNote
    rendered: str
    metrics: RunMetrics
    warnings: list[str]
    extraction: ExtractionResult
    transcription: TranscriptionResult | None = None


def _finalize(
    *,
    transcript: str,
    extraction: ExtractionResult,
    transcription: TranscriptionResult | None,
    source: str,
    started: float,
    settings: Settings,
    record: bool,
) -> PipelineResult:
    total = time.perf_counter() - started
    note = extraction.note
    rendered = render_note(note)
    metrics = make_metrics(
        source=source,
        llm_model=extraction.model,
        whisper_model=transcription.model if transcription else None,
        audio_duration_s=transcription.audio_duration_s if transcription else None,
        transcription_s=transcription.transcription_s if transcription else None,
        extraction_s=extraction.extraction_s,
        total_s=total,
        prompt_tokens=extraction.prompt_tokens,
        completion_tokens=extraction.completion_tokens,
        repair_attempts=extraction.repair_attempts,
        valid_first_try=extraction.valid_first_try,
        transcript_chars=len(transcript),
        note_chars=len(rendered),
        uncertain_count=len(note.uncertain_items),
        warnings_count=len(extraction.warnings),
    )
    if record:
        record_metrics(settings.metrics_path, metrics)
    logger.info(
        "pipeline finished source=%s total_s=%.2f repairs=%d warnings=%d",
        source,
        total,
        extraction.repair_attempts,
        len(extraction.warnings),
    )
    return PipelineResult(
        transcript=transcript,
        note=note,
        rendered=rendered,
        metrics=metrics,
        warnings=list(extraction.warnings),
        extraction=extraction,
        transcription=transcription,
    )


def run_from_text(
    transcript: str,
    settings: Settings | None = None,
    client: OllamaClient | None = None,
    record: bool = True,
) -> PipelineResult:
    """Run the pipeline from an already-written transcript (no audio, no Whisper)."""
    settings = settings or get_settings()
    started = time.perf_counter()
    text = transcript.strip()
    extraction = extract_note(text, settings, client=client)
    return _finalize(
        transcript=text,
        extraction=extraction,
        transcription=None,
        source="text",
        started=started,
        settings=settings,
        record=record,
    )


def run_from_audio(
    audio_path: str | Path,
    settings: Settings | None = None,
    client: OllamaClient | None = None,
    record: bool = True,
) -> PipelineResult:
    """Run the pipeline from an audio file (Whisper first, then extraction)."""
    settings = settings or get_settings()
    started = time.perf_counter()
    transcription = transcribe_file(audio_path, settings)
    extraction = extract_note(transcription.text, settings, client=client)
    return _finalize(
        transcript=transcription.text,
        extraction=extraction,
        transcription=transcription,
        source="audio",
        started=started,
        settings=settings,
        record=record,
    )
