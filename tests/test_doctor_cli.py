"""Doctor and CLI tests (fully mocked: no Ollama, no GPU, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from dentanote.cli import app
from dentanote.config import Settings
from dentanote.doctor import Check, run_checks, summarize

runner = CliRunner()


class FakeClient:
    base_url = "http://localhost:11434"

    def __init__(self, alive: bool = True, models: list[str] | None = None) -> None:
        self._alive = alive
        self._models = models if models is not None else ["gemma4:e4b:latest"]

    def is_alive(self) -> bool:
        return self._alive

    def available_models(self) -> list[str]:
        return self._models


# --- doctor -----------------------------------------------------------------


def test_ready_machine_has_no_failing_checks(tmp_path: Path) -> None:
    """Local checks must pass; GPU/Whisper cache depend on the machine (warn at worst)."""
    settings = Settings(metrics_path=tmp_path / "metrics.jsonl")
    checks = run_checks(settings, client=FakeClient(models=["gemma4:e4b"]))
    statuses = {check.name: check.status for check in checks}
    assert statuses["Python"] == "ok"
    assert statuses["Servidor Ollama"] == "ok"
    assert statuses["Modelo LLM"] == "ok"
    assert statuses["Métricas"] == "ok"
    # Machine-dependent checks may warn (no nvidia-smi, model not cached yet) but never fail.
    assert statuses["GPU"] in {"ok", "warn"}
    assert statuses["Modelo Whisper"] in {"ok", "warn"}
    assert summarize(checks) in {"ok", "warn"}
    assert all(check.status in {"ok", "warn"} for check in checks)


def test_ollama_down_is_a_failure(tmp_path: Path) -> None:
    settings = Settings(metrics_path=tmp_path / "metrics.jsonl")
    checks = run_checks(settings, client=FakeClient(alive=False, models=[]))
    assert summarize(checks) == "fail"
    ollama = next(check for check in checks if check.name == "Servidor Ollama")
    assert ollama.status == "fail"


def test_missing_model_suggests_pull(tmp_path: Path) -> None:
    settings = Settings(metrics_path=tmp_path / "metrics.jsonl", llm_model="gemma4:e4b")
    checks = run_checks(settings, client=FakeClient(models=["llama3:8b"]))
    model_check = next(check for check in checks if check.name == "Modelo LLM")
    assert model_check.status == "fail"
    assert "ollama pull gemma4:e4b" in model_check.detail


def test_summarize_precedence() -> None:
    assert summarize([Check("a", "ok", ""), Check("b", "warn", "")]) == "warn"
    assert summarize([Check("a", "warn", ""), Check("b", "fail", "")]) == "fail"
    assert summarize([]) == "ok"


# --- CLI --------------------------------------------------------------------


def test_cli_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip()


def test_cli_text_missing_file_is_friendly() -> None:
    result = runner.invoke(app, ["text", "nao_existe.txt"])
    assert result.exit_code == 1
    assert "arquivo não encontrado" in result.stdout + str(result.output)


@pytest.mark.enable_socket
def test_cli_reports_ollama_failure_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the local server unreachable, users get a message — never a traceback."""
    from dentanote.config import get_settings

    transcript = tmp_path / "caso.txt"
    transcript.write_text("Paciente Exemplo 01: dor no dente 36.", encoding="utf-8")
    # Point at a closed local port and a private metrics file (no real server, no side effects).
    monkeypatch.setenv("DENTANOTE_OLLAMA_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("DENTANOTE_METRICS_PATH", str(tmp_path / "metrics.jsonl"))
    get_settings.cache_clear()
    try:
        result = runner.invoke(app, ["text", str(transcript)])
    finally:
        get_settings.cache_clear()
    output = result.output
    assert result.exit_code == 1
    assert "Traceback" not in output
    assert "Ollama" in output


def test_cli_doctor_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dentanote import cli as cli_module

    def fake_checks(settings: object | None = None, client: object | None = None) -> list[Check]:  # type: ignore[no-untyped-def]
        return [Check("Servidor Ollama", "ok", "respondendo em http://localhost:11434")]

    monkeypatch.setattr(cli_module, "run_checks", fake_checks)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Servidor Ollama" in result.output
    assert "Tudo pronto" in result.output or "funcional" in result.output


def test_cli_eval_mock_writes_report(tmp_path: Path) -> None:
    """``dentanote eval --mock`` validates the harness offline and writes the report."""
    out = tmp_path / "results.md"
    result = runner.invoke(app, ["eval", "--mock", "--limit", "2", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "Resultados da avaliação" in result.output
    assert out.exists()
    assert "Relatório gravado" in result.output
