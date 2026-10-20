"""Dataset integrity tests: the synthetic corpus must stay synthetic and valid."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from dentanote.schema import ClinicalNote, is_valid_fdi

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS = sorted((ROOT / "data" / "synthetic" / "transcripts").glob("*.txt"))
EXPECTED = ROOT / "data" / "synthetic" / "expected"

REQUIRED_SCENARIOS = {
    "restauracao_classe_I",
    "restauracao_classe_II",
    "endodontia",
    "exodontia_simples",
    "profilaxia_raspagem",
    "urgencia_dor",
    "prescricao_analgesico",
    "prescricao_antibiotico",
    "retorno",
    "informacao_ambigua",
    "dente_falado_de_formas",
    "dente_deciduo",
}


def test_twelve_transcripts_covering_required_scenarios() -> None:
    stems = {path.stem for path in TRANSCRIPTS}
    assert len(TRANSCRIPTS) >= 12
    assert stems >= REQUIRED_SCENARIOS


def test_every_transcript_has_a_valid_expected_note() -> None:
    for path in TRANSCRIPTS:
        expected_path = EXPECTED / f"{path.stem}.json"
        assert expected_path.exists(), f"missing expected file for {path.stem}"
        note = ClinicalNote.model_validate(json.loads(expected_path.read_text(encoding="utf-8")))
        for tooth in note.teeth:
            assert is_valid_fdi(tooth.fdi_number)
        for procedure in note.procedures:
            for number in procedure.tooth_fdi:
                assert is_valid_fdi(number)


def test_corpus_contains_only_synthetic_names() -> None:
    allowed = {f"paciente exemplo {i:02d}" for i in range(1, 13)}
    for path in TRANSCRIPTS:
        words = {
            word.strip(".,;:!?()\"'").lower() for word in path.read_text(encoding="utf-8").split()
        }
        names = {word for word in words if word == "paciente"}
        assert names, f"{path.name} should identify a synthetic patient"
        text = path.read_text(encoding="utf-8").lower()
        for index in range(1, 13):
            candidate = f"paciente exemplo {index:02d}"
            if candidate in text:
                assert candidate in allowed


def test_no_paciente_real_style_names_in_corpus() -> None:
    """Guard against real patient data sneaking into the repo."""
    banned = ("dn.", "dr.", "paciente real", "cpf", "prontuário real")
    for path in TRANSCRIPTS:
        text = path.read_text(encoding="utf-8").lower()
        for token in banned:
            assert token not in text, f"{path.name} contains banned token {token!r}"


def test_expected_files_stay_fictional() -> None:
    pattern = re.compile(r"\b(cpf|rg|telefone|endereco|data de nascimento)\b")
    for path in EXPECTED.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        match = pattern.search(text)
        assert match is None, f"{path.name} contains possible personal data {match.group(0)!r}"


@pytest.mark.parametrize("path", TRANSCRIPTS, ids=lambda p: p.stem)
def test_transcripts_are_long_enough(path: Path) -> None:
    words = path.read_text(encoding="utf-8").split()
    assert 40 <= len(words) <= 200, f"{path.name} has {len(words)} words"


def test_ambiguous_scenarios_flag_uncertainty() -> None:
    for slug in ("informacao_ambigua", "dente_falado_de_formas"):
        note = ClinicalNote.model_validate(
            json.loads((EXPECTED / f"{slug}.json").read_text(encoding="utf-8"))
        )
        assert note.uncertain_items, f"{slug} must demonstrate uncertain_items"
