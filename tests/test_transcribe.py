"""Transcription tests — faster-whisper fully mocked (no model, no network)."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from dentanote import transcribe as transcribe_module
from dentanote.config import Settings
from dentanote.transcribe import TranscriptionError, transcribe_file

SECRET_TRANSCRIPT = "Paciente Exemplo 07 refere dor aguda no dente 47"


def make_settings(**kwargs: object) -> Settings:
    return Settings(_env_file=None, **kwargs)  # type: ignore[call-arg]


def fake_audio(tmp_path: Path, suffix: str = ".wav") -> Path:
    path = tmp_path / f"synthetic_case{suffix}"
    path.write_bytes(b"RIFF....WAVEfake")
    return path


class FakeModel:
    """Records which device it was created for; simulates CUDA stack failures."""

    def __init__(self, device: str, fail: bool, text: str) -> None:
        self.device = device
        self.fail = fail
        self.text = text

    def transcribe(self, path: str, **kwargs: object):  # type: ignore[no-untyped-def]
        if self.fail:
            raise RuntimeError("Library libcublas.so.12 is not found or cannot be loaded")
        segment = SimpleNamespace(text=self.text)
        info = SimpleNamespace(duration=2.0, language="pt")
        return iter([segment]), info


def install_fake_loader(monkeypatch: pytest.MonkeyPatch, *, cuda_broken: bool, text: str):  # type: ignore[no-untyped-def]
    calls: list[str] = []

    def fake_load(model_name: str, device: str, compute_type: str) -> FakeModel:
        del model_name, compute_type
        calls.append(device)
        return FakeModel(device, fail=cuda_broken and device != "cpu", text=text)

    monkeypatch.setattr(transcribe_module, "_load_model", fake_load)
    return calls


def test_missing_audio_file_gives_friendly_error(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError, match="arquivo de áudio não encontrado"):
        transcribe_file(tmp_path / "nao_existe.wav", make_settings())


def test_unsupported_suffix_lists_supported_formats(tmp_path: Path) -> None:
    path = tmp_path / "case.txt"
    path.write_text("não é áudio", encoding="utf-8")
    with pytest.raises(TranscriptionError, match="formato não suportado"):
        transcribe_file(path, make_settings())


def test_transcription_joins_segments_and_keeps_transcript_out_of_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install_fake_loader(monkeypatch, cuda_broken=False, text=f" {SECRET_TRANSCRIPT} ")
    with caplog.at_level(logging.DEBUG):
        result = transcribe_file(fake_audio(tmp_path), make_settings(whisper_device="cpu"))

    assert result.text == SECRET_TRANSCRIPT
    assert result.audio_duration_s == 2.0
    assert result.language == "pt"
    assert result.transcription_s >= 0
    assert result.rtf >= 0
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert SECRET_TRANSCRIPT not in joined  # no PHI in logs (chars only)


def test_auto_device_falls_back_to_cpu_when_cuda_is_broken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls = install_fake_loader(monkeypatch, cuda_broken=True, text="transcrição ok")
    with caplog.at_level(logging.INFO):
        result = transcribe_file(fake_audio(tmp_path), make_settings(whisper_device="auto"))

    assert calls == ["auto", "cpu"]  # CUDA attempted once, then CPU
    assert result.text == "transcrição ok"
    warnings = [
        record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING
    ]
    assert any("GPU unusable" in message for message in warnings)


def test_explicit_cuda_never_silently_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = install_fake_loader(monkeypatch, cuda_broken=True, text="nunca chega aqui")
    with pytest.raises(TranscriptionError, match="falha ao transcrever o áudio"):
        transcribe_file(fake_audio(tmp_path), make_settings(whisper_device="cuda"))
    assert calls == ["cuda"]  # user asked for CUDA explicitly: report, do not guess


def test_empty_transcript_raises_friendly_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_fake_loader(monkeypatch, cuda_broken=False, text="   ")
    with pytest.raises(TranscriptionError, match="não foi possível reconhecer fala"):
        transcribe_file(fake_audio(tmp_path), make_settings(whisper_device="cpu"))
