"""Shared fixtures for DentaNote tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dentanote.schema import ClinicalNote


@pytest.fixture
def minimal_note() -> ClinicalNote:
    """An empty note: nothing was mentioned, nothing is invented."""
    return ClinicalNote()


@pytest.fixture
def full_note() -> ClinicalNote:
    """A fully populated, synthetic note (fictional patient)."""
    return ClinicalNote(
        chief_complaint="dor no dente do fundo há três dias",
        history="paciente hipertenso em uso de losartana",
        findings=["cárie oclusal profunda", "restauração solta"],
        teeth=[
            {"fdi_number": 36, "surfaces": ["O", "M"], "note": None},
            {"fdi_number": 46, "surfaces": ["O"], "note": "dente de ponte"},
        ],
        procedures=[
            {"name": "restauração em resina", "tooth_fdi": [36], "details": "classe I"},
        ],
        materials_anesthesia=["mepivacaína 3%"],
        medications_prescribed=[
            {
                "name": "ibuprofeno",
                "dose": "600 mg",
                "frequency": "de 6 em 6 h",
                "duration": "3 dias",
            }
        ],
        guidance_given=["evitar mastigar do lado tratado"],
        follow_up="retorno em 7 dias",
        uncertain_items=["trecho não inteligível aos 12 s"],
    )


@pytest.fixture
def sample_transcript() -> str:
    """Synthetic transcript used across tests (fictional patient)."""
    return (
        "Paciente Exemplo 01, retorno. Refere dor no dente do fundo do lado "
        "esquerdo há três dias. Exame: cárie oclusal no dente trinta e seis. "
        "Feito isolamento absoluto e restauração em resina classe I. "
        "Orientado a evitar mastigar do lado. Retorno em sete dias se houver dor."
    )


@pytest.fixture
def metrics_path(tmp_path: Path) -> Path:
    """Isolated metrics file per test (never touches the repo root)."""
    return tmp_path / "metrics.jsonl"


def load_expected(name: str) -> dict:
    """Load an expected JSON from ``data/synthetic/expected``."""
    path = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "expected" / name
    return json.loads(path.read_text(encoding="utf-8"))
