"""Integration with the real local Ollama server (excluded from CI).

These tests are marked ``slow``: they need a running Ollama server with the
configured model, so CI runs ``pytest -m "not slow"`` and this module skips
automatically when no local server answers. Everything else in the suite is
fully offline (``--disable-socket``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dentanote.config import Settings
from dentanote.extract import OllamaClient
from dentanote.pipeline import run_from_text

CASE = (
    "Paciente Exemplo 01, retorno. Refere sensibilidade fria no dente 36, "
    "restaurado na semana passada. Sem dor espontânea. Mantida a orientação "
    "de escovação e uso de fio dental."
)


@pytest.mark.slow
@pytest.mark.enable_socket
def test_real_extraction_returns_draft_with_expected_tooth(tmp_path: Path) -> None:
    settings = Settings(metrics_path=tmp_path / "metrics.jsonl")
    if not OllamaClient(settings).is_alive():
        pytest.skip("Ollama local indisponível — este teste roda só com o servidor ativo")

    result = run_from_text(CASE, settings, record=False)

    # The draft banner must always be present.
    assert "RASCUNHO" in result.rendered
    # The transcript names exactly one tooth; the model must normalize it to FDI.
    assert any(tooth.fdi_number == 36 for tooth in result.note.teeth)
    # Output is a validated note, and nothing reached metrics.jsonl (record=False).
    assert result.metrics.llm_model
    assert not settings.metrics_path.exists()
