"""Per-run metrics with a hard no-PHI guarantee (PROMPT.md sections 5.5, 10).

Only durations, counts, sizes, model names and attempt numbers are stored —
never the transcript, never the clinical note, never a log line with content.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

# Keys that must never appear in a metrics record (defence in depth for the
# "no PHI in logs" test).
FORBIDDEN_METRIC_KEYS = frozenset(
    {"transcript", "text", "note", "content", "rendered", "clinical_text"}
)


def new_run_id() -> str:
    """Short opaque identifier for one pipeline execution."""
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True)
class RunMetrics:
    """Everything we measure about a run — sizes and timings only."""

    run_id: str
    timestamp: str
    source: str  # "audio" | "text"
    llm_model: str
    whisper_model: str | None
    audio_duration_s: float | None
    transcription_s: float | None
    extraction_s: float
    total_s: float
    prompt_tokens: int
    completion_tokens: int
    repair_attempts: int
    valid_first_try: bool
    transcript_chars: int
    note_chars: int
    uncertain_count: int
    warnings_count: int

    @property
    def tokens_per_s(self) -> float:
        """Generation speed (completion tokens per second of extraction)."""
        if self.extraction_s <= 0:
            return 0.0
        return self.completion_tokens / self.extraction_s

    def to_record(self) -> dict[str, object]:
        record = asdict(self)
        record["tokens_per_s"] = round(self.tokens_per_s, 2)
        return record


def make_metrics(
    *,
    source: str,
    llm_model: str,
    whisper_model: str | None,
    audio_duration_s: float | None,
    transcription_s: float | None,
    extraction_s: float,
    total_s: float,
    prompt_tokens: int,
    completion_tokens: int,
    repair_attempts: int,
    valid_first_try: bool,
    transcript_chars: int,
    note_chars: int,
    uncertain_count: int,
    warnings_count: int,
    run_id: str | None = None,
) -> RunMetrics:
    """Build a metrics record with an id and an UTC timestamp."""
    return RunMetrics(
        run_id=run_id or new_run_id(),
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        source=source,
        llm_model=llm_model,
        whisper_model=whisper_model,
        audio_duration_s=audio_duration_s,
        transcription_s=transcription_s,
        extraction_s=round(extraction_s, 3),
        total_s=round(total_s, 3),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        repair_attempts=repair_attempts,
        valid_first_try=valid_first_try,
        transcript_chars=transcript_chars,
        note_chars=note_chars,
        uncertain_count=uncertain_count,
        warnings_count=warnings_count,
    )


def record_metrics(path: Path, metrics: RunMetrics | dict[str, object]) -> Path:
    """Append one JSON line to ``metrics.jsonl`` (creating parents if needed)."""
    record = metrics.to_record() if isinstance(metrics, RunMetrics) else dict(metrics)
    forbidden = FORBIDDEN_METRIC_KEYS & record.keys()
    if forbidden:  # pragma: no cover - guards against future refactors
        raise ValueError(f"metrics record contains forbidden keys: {sorted(forbidden)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def load_metrics(path: Path) -> list[dict[str, object]]:
    """Read every metrics record back (used by the CLI and evaluation script)."""
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records
