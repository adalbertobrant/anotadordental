"""Schema tests: FDI validation, surfaces, defaults and JSON Schema export."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from dentanote.schema import (
    ClinicalNote,
    Medication,
    Procedure,
    ToothRef,
    clinical_note_json_schema,
    fdi_from_words,
    is_valid_fdi,
)


@pytest.mark.parametrize("number", [11, 18, 21, 28, 31, 38, 41, 48, 51, 55, 61, 65, 71, 75, 81, 85])
def test_valid_fdi_numbers_accepted(number: int) -> None:
    assert is_valid_fdi(number)
    assert ToothRef(fdi_number=number).fdi_number == number


@pytest.mark.parametrize("number", [0, 1, 10, 19, 49, 50, 56, 86, 90, 99, -36])
def test_invalid_fdi_numbers_rejected(number: int) -> None:
    assert not is_valid_fdi(number)
    with pytest.raises(ValidationError, match="invalid FDI tooth number"):
        ToothRef(fdi_number=number)


def test_surfaces_are_normalized_and_deduped() -> None:
    tooth = ToothRef(fdi_number=36, surfaces=["o", " M ", "O", "m"])
    assert tooth.surfaces == ["O", "M"]


def test_invalid_surface_rejected() -> None:
    with pytest.raises(ValidationError, match="invalid surface"):
        ToothRef(fdi_number=36, surfaces=["X"])


def test_procedure_rejects_invalid_tooth_and_dedupes() -> None:
    procedure = Procedure(name="restauração", tooth_fdi=[36, 36, 46])
    assert procedure.tooth_fdi == [36, 46]
    with pytest.raises(ValidationError, match="invalid FDI tooth number"):
        Procedure(name="restauração", tooth_fdi=[99])


def test_medication_posology_is_optional() -> None:
    med = Medication(name="amoxicilina")
    assert (med.dose, med.frequency, med.duration) == (None, None, None)


def test_empty_note_has_empty_lists_and_uncertain_items() -> None:
    note = ClinicalNote()
    assert note.chief_complaint is None
    assert note.findings == []
    assert note.teeth == []
    assert note.procedures == []
    assert note.uncertain_items == []  # safety valve always present
    assert note.follow_up is None


def test_note_dedupes_findings_and_teeth() -> None:
    note = ClinicalNote(
        findings=["cárie", "cárie", " fratura "],
        teeth=[{"fdi_number": 36}, {"fdi_number": 36}, {"fdi_number": 46}],
        uncertain_items=["x", "x"],
    )
    assert note.findings == ["cárie", "fratura"]
    assert [t.fdi_number for t in note.teeth] == [36, 46]
    assert note.uncertain_items == ["x"]


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        ClinicalNote(diagnosis="periodontite")  # type: ignore[call-arg]


def test_json_schema_contains_all_clinical_fields() -> None:
    schema = clinical_note_json_schema()
    properties = schema["properties"]
    for field in (
        "chief_complaint",
        "history",
        "findings",
        "teeth",
        "procedures",
        "materials_anesthesia",
        "medications_prescribed",
        "guidance_given",
        "follow_up",
        "uncertain_items",
    ):
        assert field in properties
    assert schema["additionalProperties"] is False
    assert "$defs" in schema or "definitions" in schema


@pytest.mark.parametrize(
    ("spoken", "expected"),
    [
        ("dente 36", 36),
        ("primeiro molar inferior esquerdo", 36),
        ("segundo pré-molar superior direito", 15),
        ("canino superior esquerdo", 23),
        ("siso inferior direito", 48),
        ("dente 55", 55),  # deciduous
        ("dente 49", None),  # invalid FDI
        ("nada mencionado", None),  # ambiguous / absent
        ("molar do lado esquerdo", None),  # missing jaw -> ambiguous
    ],
)
def test_fdi_from_words(spoken: str, expected: int | None) -> None:
    assert fdi_from_words(spoken) == expected


def test_note_roundtrips_to_dict_and_back(full_note: ClinicalNote) -> None:
    payload = full_note.model_dump(mode="json")
    assert ClinicalNote.model_validate(payload) == full_note
