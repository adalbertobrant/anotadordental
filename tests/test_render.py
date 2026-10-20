"""Renderer tests: deterministic, omission-based, never invents content."""

from __future__ import annotations

import pytest

from dentanote.render import (
    DRAFT_HEADER,
    EMPTY_NOTICE,
    UNCERTAIN_BLOCK_TITLE,
    render_note,
)
from dentanote.schema import ClinicalNote


def test_full_note_renders_every_present_section(full_note: ClinicalNote) -> None:
    text = render_note(full_note)
    assert text.startswith(DRAFT_HEADER)
    assert "**Queixa principal**" in text
    assert "**Histórico**" in text
    assert "**Achados**" in text
    assert "**Dentes**" in text
    assert "- 36 (O, M)" in text
    assert "- 46 (O) — dente de ponte" in text
    assert "**Procedimentos**" in text
    assert "- restauração em resina — dente(s) 36 (classe I)" in text
    assert "**Materiais e anestésicos**" in text
    assert "**Prescrições**" in text
    assert "- ibuprofeno, 600 mg — de 6 em 6 h — por 3 dias" in text
    assert "**Orientações**" in text
    assert "**Retorno**" in text
    assert UNCERTAIN_BLOCK_TITLE in text
    assert "- trecho não inteligível aos 12 s" in text


def test_absent_sections_are_omitted_not_filled() -> None:
    note = ClinicalNote(findings=["fratura lineares na oclusal do 26"])
    text = render_note(note)
    assert "**Achados**" in text
    for absent in ("**Queixa principal**", "**Histórico**", "**Retorno**", "**Dentes**"):
        assert absent not in text
    assert "não informado" not in text
    assert "sem dados" not in text.lower()


def test_empty_note_is_explicit_and_has_no_fake_sections() -> None:
    text = render_note(ClinicalNote())
    assert EMPTY_NOTICE in text
    assert "**" not in text.replace(DRAFT_HEADER, "")
    assert UNCERTAIN_BLOCK_TITLE not in text


def test_uncertain_block_appears_only_when_needed() -> None:
    without = render_note(ClinicalNote(findings=["x"]))
    with_uncertain = render_note(ClinicalNote(findings=["x"], uncertain_items=["y"]))
    assert UNCERTAIN_BLOCK_TITLE not in without
    assert UNCERTAIN_BLOCK_TITLE in with_uncertain


def test_render_is_deterministic(full_note: ClinicalNote) -> None:
    assert render_note(full_note) == render_note(full_note)


def test_render_does_not_mention_fields_absent_from_the_note(
    full_note: ClinicalNote,
) -> None:
    full_note.procedures = []
    full_note.medications_prescribed = []
    text = render_note(full_note)
    assert "**Procedimentos**" not in text
    assert "**Prescrições**" not in text
    assert "restauração em resina" not in text
    assert "ibuprofeno" not in text


@pytest.mark.parametrize("note", [ClinicalNote(), ClinicalNote(follow_up="retorno em 30 dias")])
def test_render_always_labels_output_as_draft(note: ClinicalNote) -> None:
    assert "RASCUNHO" in render_note(note)


def test_medication_formatting_without_posology() -> None:
    from dentanote.schema import Medication

    note = ClinicalNote(medications_prescribed=[Medication(name="amoxicilina")])
    assert "- amoxicilina" in render_note(note)
