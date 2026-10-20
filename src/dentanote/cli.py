"""Command line interface for DentaNote (typer).

Clinical text only goes where the user asked (stdout draft / JSON / file);
logs carry timings and counts only — never transcript or note content.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated

import typer

from dentanote import __version__
from dentanote.config import get_settings
from dentanote.doctor import run_checks, summarize
from dentanote.extract import ExtractionError
from dentanote.pipeline import PipelineResult, run_from_audio, run_from_text
from dentanote.transcribe import TranscriptionError

app = typer.Typer(
    name="dentanote",
    help=(
        "DentaNote — transcreve a consulta, extrai os dados clínicos e gera um "
        "RASCUNHO de evolução clínica, 100% local. Revise antes de salvar."
    ),
    no_args_is_help=True,
    add_completion=False,
)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _fail(message: str, code: int = 1) -> None:
    typer.secho(message, fg="red", err=True)
    raise typer.Exit(code)


def _emit(result: PipelineResult, as_json: bool, output: Path | None) -> None:
    if as_json:
        payload = {
            "transcript": result.transcript,
            "note": result.note.model_dump(mode="json"),
            "rendered": result.rendered,
            "metrics": result.metrics.to_record(),
            "warnings": result.warnings,
        }
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        rendered = result.rendered.rstrip("\n")

    if output:
        output.write_text(rendered + "\n", encoding="utf-8")
        typer.secho(f"Saída gravada em {output}", fg="green")
    else:
        typer.echo(rendered)

    for warning in result.warnings:
        typer.secho(f"⚠ {warning}", fg="yellow", err=True)
    typer.secho(
        f"Rascunho gerado por IA local ({result.metrics.llm_model}). "
        "Revise antes de salvar no prontuário.",
        fg="cyan",
        err=True,
    )


@app.callback()
def _main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Debug logs (sem texto clínico).")
    ] = False,
) -> None:
    """DentaNote CLI — local, offline, somente rascunho."""
    _configure_logging(verbose)


@app.command("version")
def version_cmd() -> None:
    """Print the installed version."""
    typer.echo(__version__)


@app.command("text")
def text_cmd(
    transcript_path: Annotated[Path, typer.Argument(help="Arquivo .txt com a transcrição.")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Grava a saída em arquivo.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Saída estruturada (JSON) em vez do rascunho.")
    ] = False,
) -> None:
    """Extract a structured note from an already-written transcript (no audio)."""
    if not transcript_path.exists():
        _fail(f"arquivo não encontrado: {transcript_path}")
    transcript = transcript_path.read_text(encoding="utf-8").strip()
    if not transcript:
        _fail(f"arquivo vazio: {transcript_path}")

    try:
        result = run_from_text(transcript, get_settings())
    except ExtractionError as exc:
        _fail(str(exc))
    _emit(result, as_json, output)


@app.command("doctor")
def doctor_cmd() -> None:
    """Check the local environment (Ollama, models, GPU, caches, metrics path)."""
    checks = run_checks(get_settings())
    icons = {"ok": "✔", "warn": "⚠", "fail": "✗"}
    for check in checks:
        color = {"ok": "green", "warn": "yellow", "fail": "red"}[check.status]
        typer.secho(f"{icons[check.status]} {check.name}: {check.detail}", fg=color)
    overall = summarize(checks)
    if overall == "fail":
        typer.secho("\nAmbiente incompleto — corrija os itens ✗ acima.", fg="red")
        raise typer.Exit(1)
    if overall == "warn":
        typer.secho("\nAmbiente funcional, com avisos ⚠ (veja acima).", fg="yellow")
    else:
        typer.secho("\nTudo pronto: DentaNote 100% local.", fg="green")


@app.command("run")
def run_cmd(
    audio: Annotated[Path, typer.Argument(help="Áudio da consulta (wav/mp3/m4a/ogg).")],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Grava a saída em arquivo.")
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Saída estruturada (JSON) em vez do rascunho.")
    ] = False,
) -> None:
    """Transcribe an audio file and generate the clinical evolution draft."""
    settings = get_settings()
    if not audio.exists():
        _fail(f"arquivo não encontrado: {audio}")
    try:
        result = run_from_audio(audio, settings)
    except (TranscriptionError, ExtractionError) as exc:
        _fail(str(exc))
    if result.transcription:
        typer.secho(
            f"Transcrito: {result.transcription.audio_duration_s:.1f}s de áudio em "
            f"{result.transcription.transcription_s:.1f}s "
            f"(whisper {result.transcription.model}).",
            err=True,
        )
    _emit(result, as_json, output)


if __name__ == "__main__":  # pragma: no cover
    app()
