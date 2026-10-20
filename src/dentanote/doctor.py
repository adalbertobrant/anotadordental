"""Environment diagnostics for the ``dentanote doctor`` command.

Every check is local: we talk to the local Ollama server, inspect caches and
subprocesses. No data is sent anywhere, and nothing here reads clinical text.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from dentanote.config import Settings, get_settings
from dentanote.extract import OllamaClient

Status = str  # "ok" | "warn" | "fail"


@dataclass(frozen=True)
class Check:
    """One diagnostic result shown by ``dentanote doctor``."""

    name: str
    status: Status
    detail: str


def _check_python() -> Check:
    version = ".".join(str(part) for part in sys.version_info[:3])
    # pyproject enforces >=3.11 at install time; this is a friendlier runtime echo.
    status: Status = "ok" if sys.version_info[:2] >= (3, 11) else "fail"
    detail = version if status == "ok" else f"versão {version} — DentaNote exige 3.11+"
    return Check("Python", status, detail)


def _check_ollama(client: OllamaClient) -> Check:
    if client.is_alive():
        return Check("Servidor Ollama", "ok", f"respondendo em {client.base_url}")
    return Check(
        "Servidor Ollama",
        "fail",
        f"sem resposta em {client.base_url} — inicie com `ollama serve`",
    )


def _check_model(client: OllamaClient, settings: Settings) -> Check:
    models = client.available_models()
    if not models:
        return Check(
            "Modelo LLM",
            "fail" if client.is_alive() else "warn",
            f"nenhum modelo listado — baixe com `ollama pull {settings.llm_model}`",
        )
    exact = any(
        name.split(":")[0] == settings.llm_model.split(":")[0] and name == settings.llm_model
        for name in models
    )
    family = [name for name in models if name.split(":")[0] == settings.llm_model.split(":")[0]]
    if exact:
        return Check("Modelo LLM", "ok", f"`{settings.llm_model}` instalado")
    if family:
        return Check(
            "Modelo LLM",
            "warn",
            f"`{settings.llm_model}` não encontrado; disponível: {', '.join(family)} "
            f"(ajuste DENTANOTE_LLM_MODEL ou rode `ollama pull {settings.llm_model}`)",
        )
    return Check(
        "Modelo LLM",
        "fail",
        f"`{settings.llm_model}` não está instalado (modelos locais: {', '.join(models)}) "
        f"— baixe com `ollama pull {settings.llm_model}`",
    )


def _check_gpu() -> Check:
    binary = shutil.which("nvidia-smi")
    if not binary:
        return Check("GPU", "warn", "nvidia-smi ausente — o Whisper e o LLM rodarão em CPU")
    try:
        output = subprocess.run(
            [binary, "-L"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return Check("GPU", "warn", "nvidia-smi não pôde ser executado — usando CPU")
    gpus = [line for line in output.stdout.splitlines() if line.strip()]
    if output.returncode == 0 and gpus:
        return Check("GPU", "ok", f"{len(gpus)} GPU(s): {gpus[0].split('(')[0].strip()}")
    return Check("GPU", "warn", "nenhuma GPU detectada — usando CPU")


def _check_whisper_cache(settings: Settings) -> Check:
    cache_root = Path.home() / ".cache" / "huggingface" / "hub"
    matches = (
        list(cache_root.glob(f"*faster-whisper-{settings.whisper_model}*"))
        if (cache_root.exists())
        else []
    )
    if matches:
        return Check("Modelo Whisper", "ok", f"`{settings.whisper_model}` no cache local")
    return Check(
        "Modelo Whisper",
        "warn",
        f"`{settings.whisper_model}` ainda não baixado — será baixado no primeiro "
        "uso (única etapa que precisa de rede; depois, tudo offline)",
    )


def _check_metrics_path(settings: Settings) -> Check:
    path: Path = settings.metrics_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        probe = path.parent / ".dentanote_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return Check("Métricas", "fail", f"não foi possível gravar em {path.parent}: {exc}")
    return Check("Métricas", "ok", f"gravando em {path} (sem dados clínicos)")


def run_checks(
    settings: Settings | None = None,
    client: OllamaClient | None = None,
) -> list[Check]:
    """Run every diagnostic (injectable for tests)."""
    settings = settings or get_settings()
    client = client or OllamaClient(settings)
    return [
        _check_python(),
        _check_ollama(client),
        _check_model(client, settings),
        _check_gpu(),
        _check_whisper_cache(settings),
        _check_metrics_path(settings),
    ]


def summarize(checks: list[Check]) -> Status:
    """Overall status: fail > warn > ok."""
    statuses = {check.status for check in checks}
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"
