"""Pydantic models for the extracted clinical note (DentaNote schema).

Design rules (see PROMPT.md section 4):

* every clinical field is optional — "not mentioned" is ``None``/empty list,
  never an inferred value;
* tooth numbers use the **FDI notation** (11-48 permanent, 51-85 deciduous) and
  are validated here;
* ``uncertain_items`` is the safety valve: anything ambiguous or invalid is
  listed there for the professional to review instead of being silently fixed.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# --- FDI helpers -----------------------------------------------------------

PERMANENT_QUADRANTS = (1, 2, 3, 4)
DECIDUOUS_QUADRANTS = (5, 6, 7, 8)

# Anatomical surfaces: Mesial, Distal, Occlusal/Incisal edge (O), Vestibular,
# Lingual/Palatal, Protal (distal surface of the most posterior tooth),
# Incisal.
ALLOWED_SURFACES = frozenset({"M", "D", "O", "V", "L", "P", "I"})

# Tooth names as spoken in a Brazilian dental office -> position in quadrant.
TOOTH_POSITION_BY_NAME: dict[str, int] = {
    "incisivo central": 1,
    "incisivo lateral": 2,
    "canino": 3,
    "pre-molar 1": 4,
    "primeiro pre-molar": 4,
    "pre-molar 2": 5,
    "segundo pre-molar": 5,
    "molar 1": 6,
    "primeiro molar": 6,
    "molar 2": 7,
    "segundo molar": 7,
    "molar 3": 8,
    "terceiro molar": 8,
    "siso": 8,
}

# "superior/inferior" + "direito/esquerdo" -> FDI quadrant.
QUADRANT_BY_JAW_SIDE: dict[tuple[str, str], int] = {
    ("superior", "direito"): 1,
    ("superior", "esquerdo"): 2,
    ("inferior", "esquerdo"): 3,
    ("inferior", "direito"): 4,
}

_DIGITS_NUMBER = re.compile(r"\b(\d{2})\b")
_QUADRANT_WORDS = re.compile(
    r"\b(superior|inferior)\b.*?\b(direit[oa]|esquerd[oa])\b"
    r"|\b(direit[oa]|esquerd[oa])\b.*?\b(superior|inferior)\b",
    re.IGNORECASE,
)
_ACCENT_MAP = str.maketrans("áàâãéêíóôõúüç", "aaaaeeiooouuc")


def normalize_text(text: str) -> str:
    """Lowercase and strip accents so spoken variants map to one key."""
    return text.lower().translate(_ACCENT_MAP).strip()


def is_valid_fdi(number: int) -> bool:
    """True when ``number`` is a legal FDI number (permanent or deciduous)."""
    if number < 11:
        return False
    quadrant, position = divmod(number, 10)
    if quadrant in PERMANENT_QUADRANTS:
        return 1 <= position <= 8
    if quadrant in DECIDUOUS_QUADRANTS:
        return 1 <= position <= 5
    return False


def fdi_from_quadrant_and_position(quadrant: int, position: int) -> int:
    """Build an FDI number (e.g. quadrant 3, position 6 -> 36)."""
    return quadrant * 10 + position


def fdi_from_words(text: str) -> int | None:
    """Best-effort FDI conversion from a spoken description.

    Handles "primeiro molar inferior esquerdo" -> 36, "superior direito" with
    "canino" -> 13, and raw two-digit numbers ("36" -> 36). Returns ``None``
    when the description is incomplete or ambiguous; the caller must then push
    the original snippet into ``uncertain_items``.
    """
    cleaned = normalize_text(text)

    words_position: int | None = None
    for name, position in TOOTH_POSITION_BY_NAME.items():
        if name in cleaned:
            words_position = position
            break

    words_quadrant: int | None = None
    match = _QUADRANT_WORDS.search(cleaned)
    if match:
        jaw = (match.group(1) or match.group(4) or "").lower()
        side_raw = (match.group(2) or match.group(3) or "").lower()
        side = "direito" if side_raw.startswith("direit") else "esquerdo"
        words_quadrant = QUADRANT_BY_JAW_SIDE.get((jaw, side))

    if words_position is not None and words_quadrant is not None:
        return fdi_from_quadrant_and_position(words_quadrant, words_position)

    for raw in _DIGITS_NUMBER.findall(cleaned):
        candidate = int(raw)
        if is_valid_fdi(candidate):
            return candidate
        # Spoken as a single digit quadrant-style number, e.g. "dente 6".
        if len(raw) == 2 and raw[1] == "0":
            continue
    return None


# --- schema models ---------------------------------------------------------


class ToothRef(BaseModel):
    """A tooth involved in the appointment, in FDI notation."""

    model_config = ConfigDict(extra="forbid")

    fdi_number: int
    surfaces: list[str] = Field(default_factory=list)
    note: str | None = None

    @field_validator("fdi_number")
    @classmethod
    def _check_fdi(cls, value: int) -> int:
        if not is_valid_fdi(value):
            raise ValueError(
                f"invalid FDI tooth number {value}: must be 11-48 (permanent) or 51-85 (deciduous)"
            )
        return value

    @field_validator("surfaces")
    @classmethod
    def _check_surfaces(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for raw in value:
            surface = raw.strip().upper()
            if surface not in ALLOWED_SURFACES:
                raise ValueError(
                    f"invalid surface {raw!r}: allowed surfaces are {sorted(ALLOWED_SURFACES)}"
                )
            if surface not in cleaned:
                cleaned.append(surface)
        return cleaned


class Procedure(BaseModel):
    """A procedure performed during the appointment."""

    model_config = ConfigDict(extra="forbid")

    name: str
    tooth_fdi: list[int] = Field(default_factory=list)
    details: str | None = None

    @field_validator("tooth_fdi")
    @classmethod
    def _check_teeth(cls, value: list[int]) -> list[int]:
        for number in value:
            if not is_valid_fdi(number):
                raise ValueError(
                    f"invalid FDI tooth number {number}: must be 11-48 (permanent) "
                    "or 51-85 (deciduous)"
                )
        return list(dict.fromkeys(value))


class Medication(BaseModel):
    """A medication prescribed or mentioned, with optional posology."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dose: str | None = None
    frequency: str | None = None
    duration: str | None = None


class ClinicalNote(BaseModel):
    """Structured extraction of one dental appointment.

    Every field is optional. Missing information stays ``None``/empty: the
    system never fills a gap by inference.
    """

    model_config = ConfigDict(extra="forbid")

    chief_complaint: str | None = None
    history: str | None = None
    findings: list[str] = Field(default_factory=list)
    teeth: list[ToothRef] = Field(default_factory=list)
    procedures: list[Procedure] = Field(default_factory=list)
    materials_anesthesia: list[str] = Field(default_factory=list)
    medications_prescribed: list[Medication] = Field(default_factory=list)
    guidance_given: list[str] = Field(default_factory=list)
    follow_up: str | None = None
    uncertain_items: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _dedupe_lists(self) -> ClinicalNote:
        """Keep list fields unique and stable-ordered (defensive, not creative)."""
        self.findings = _dedupe(self.findings)
        self.materials_anesthesia = _dedupe(self.materials_anesthesia)
        self.guidance_given = _dedupe(self.guidance_given)
        self.uncertain_items = _dedupe(self.uncertain_items)
        seen_teeth: set[int] = set()
        unique_teeth: list[ToothRef] = []
        for tooth in self.teeth:
            if tooth.fdi_number not in seen_teeth:
                seen_teeth.add(tooth.fdi_number)
                unique_teeth.append(tooth)
        self.teeth = unique_teeth
        return self


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def clinical_note_json_schema() -> dict[str, Any]:
    """JSON Schema handed to Ollama's ``format`` parameter (constrained decoding)."""
    schema = ClinicalNote.model_json_schema()
    schema["additionalProperties"] = False
    return schema
