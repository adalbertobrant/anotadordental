"""Deterministic renderer: ``ClinicalNote`` -> clinical evolution text (PT-BR).

ADR-002: this step never calls an LLM. It only re-serializes fields that were
already validated, so nothing can be invented at the last mile. Missing
sections are omitted instead of being filled with generic prose.
"""

from __future__ import annotations

from dentanote.schema import ClinicalNote, Medication, Procedure, ToothRef

DRAFT_HEADER = (
    "EVOLUÇÃO CLÍNICA — RASCUNHO gerado por IA local. Revise antes de salvar no prontuário."
)
UNCERTAIN_BLOCK_TITLE = "⚠ Conferir antes de salvar"
EMPTY_NOTICE = "Nenhuma informação clínica foi extraída desta transcrição."


def _format_tooth(tooth: ToothRef) -> str:
    text = str(tooth.fdi_number)
    if tooth.surfaces:
        text += f" ({', '.join(tooth.surfaces)})"
    if tooth.note:
        text += f" — {tooth.note}"
    return text


def _format_procedure(procedure: Procedure) -> str:
    text = procedure.name
    if procedure.tooth_fdi:
        teeth = ", ".join(str(number) for number in procedure.tooth_fdi)
        text += f" — dente(s) {teeth}"
    if procedure.details:
        text += f" ({procedure.details})"
    return text


def _format_medication(medication: Medication) -> str:
    parts = [medication.name]
    if medication.dose:
        parts.append(medication.dose)
    text = ", ".join(parts)
    if medication.frequency:
        text += f" — {medication.frequency}"
    if medication.duration:
        text += (
            f" — por {medication.duration}"
            if not medication.duration.lower().startswith(("por", "durante"))
            else f" — {medication.duration}"
        )
    return text


def _section(title: str, items: list[str]) -> list[str]:
    """Render a titled section; omit it entirely when there is nothing to say."""
    if not items:
        return []
    return [f"**{title}**", *[f"- {item}" for item in items], ""]


def render_note(note: ClinicalNote) -> str:
    """Render the validated note as a review-ready draft (never as a diagnosis)."""
    complaint = note.chief_complaint or ""
    history = note.history or ""
    follow_up = note.follow_up or ""

    body: list[str] = []
    body += _section("Queixa principal", [complaint] if complaint else [])
    body += _section("Histórico", [history] if history else [])
    body += _section("Achados", list(note.findings))
    body += _section("Dentes", [_format_tooth(tooth) for tooth in note.teeth])
    body += _section("Procedimentos", [_format_procedure(p) for p in note.procedures])
    body += _section("Materiais e anestésicos", list(note.materials_anesthesia))
    body += _section("Prescrições", [_format_medication(m) for m in note.medications_prescribed])
    body += _section("Orientações", list(note.guidance_given))
    body += _section("Retorno", [follow_up] if follow_up else [])

    has_content = any(
        [
            complaint,
            history,
            follow_up,
            note.findings,
            note.teeth,
            note.procedures,
            note.materials_anesthesia,
            note.medications_prescribed,
            note.guidance_given,
        ]
    )
    if not has_content:
        body += [EMPTY_NOTICE, ""]

    sections = [DRAFT_HEADER, ""]
    sections += body

    if note.uncertain_items:
        sections += [
            UNCERTAIN_BLOCK_TITLE,
            *[f"- {item}" for item in note.uncertain_items],
            "",
        ]

    text = "\n".join(sections).rstrip("\n")
    return text + "\n"
