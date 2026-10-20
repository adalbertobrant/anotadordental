"""Local speech-to-text wrapper around ``faster-whisper``.

Everything here runs on the machine: the model weights are downloaded once
(model cache) and no audio ever leaves the process. Only timing metrics are
collected — the transcript itself is never logged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dentanote.config import Settings, get_settings

logger = logging.getLogger(__name__)

SUPPORTED_AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}


class TranscriptionError(RuntimeError):
    """Raised when the audio cannot be transcribed (friendly message for users)."""


@dataclass(frozen=True)
class TranscriptionResult:
    """Transcript plus timing metrics (no audio, no PHI beyond the transcript)."""

    text: str
    audio_duration_s: float
    transcription_s: float
    language: str
    model: str

    @property
    def rtf(self) -> float:
        """Real-time factor: seconds of processing per second of audio."""
        if self.audio_duration_s <= 0:
            return 0.0
        return self.transcription_s / self.audio_duration_s


@lru_cache(maxsize=4)
def _load_model(model_name: str, device: str, compute_type: str) -> object:
    """Cache Whisper models by configuration (loading twice is expensive)."""
    from faster_whisper import WhisperModel  # imported lazily: heavy dependency

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def transcribe_file(
    audio_path: str | Path,
    settings: Settings | None = None,
) -> TranscriptionResult:
    """Transcribe an audio file with ``faster-whisper`` (language: pt, VAD on)."""
    settings = settings or get_settings()
    path = Path(audio_path)
    if not path.exists():
        raise TranscriptionError(f"arquivo de áudio não encontrado: {path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_SUFFIXES:
        raise TranscriptionError(
            f"formato não suportado: {path.suffix} (use {', '.join(sorted(SUPPORTED_AUDIO_SUFFIXES))})"
        )

    from dentanote.prompts import WHISPER_INITIAL_PROMPT

    prompt = WHISPER_INITIAL_PROMPT if settings.initial_prompt_enabled else None

    def _transcribe(device: str):  # type: ignore[no-untyped-def]
        model = _load_model(settings.whisper_model, device, settings.whisper_compute_type)
        segments_iter, info = model.transcribe(  # type: ignore[attr-defined]
            str(path),
            language=settings.language,
            vad_filter=settings.vad_filter,
            initial_prompt=prompt,
        )
        return list(segments_iter), info

    started = time.perf_counter()
    try:
        segments, info = _transcribe(settings.whisper_device)
    except Exception as exc:  # pragma: no cover - depends on local codecs/GPU
        if settings.whisper_device != "auto":
            raise TranscriptionError(f"falha ao transcrever o áudio: {exc}") from exc
        # "auto" chose CUDA but the GPU stack does not work on this machine
        # (typical: missing CUDA runtime libs). Fall back to CPU instead of failing.
        logger.warning("GPU unusable for Whisper (%s) — retrying on CPU", type(exc).__name__)
        started = time.perf_counter()
        try:
            segments, info = _transcribe("cpu")
        except Exception as fallback_exc:
            raise TranscriptionError(
                f"falha ao transcrever o áudio: {fallback_exc}"
            ) from fallback_exc
    elapsed = time.perf_counter() - started

    text = " ".join(segment.text.strip() for segment in segments).strip()
    audio_duration = float(getattr(info, "duration", 0.0) or 0.0)
    language = str(getattr(info, "language", settings.language) or settings.language)

    # Timing and sizes only — never the transcript itself (no PHI in logs).
    logger.info(
        "transcription finished model=%s duration_s=%.2f elapsed_s=%.2f chars=%d",
        settings.whisper_model,
        audio_duration,
        elapsed,
        len(text),
    )
    if not text:
        raise TranscriptionError(
            "não foi possível reconhecer fala no áudio (verifique o arquivo ou "
            "use a entrada por texto)."
        )
    return TranscriptionResult(
        text=text,
        audio_duration_s=audio_duration,
        transcription_s=elapsed,
        language=language,
        model=settings.whisper_model,
    )
