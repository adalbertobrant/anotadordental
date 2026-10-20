"""Extraction step: transcript -> validated ``ClinicalNote`` via local Ollama.

Flow (PROMPT.md section 5.3):

1. send the transcript with a strict PT-BR system prompt and few-shot examples;
2. force JSON with Ollama's ``format`` (JSON Schema / constrained decoding);
3. sanitize what we can deterministically (invalid FDI numbers are dropped and
   recorded in ``uncertain_items`` — never silently "fixed");
4. validate with Pydantic; on failure, resend the validation error (up to
   ``settings.max_repairs`` repairs); if it still fails, return a partial
   result with a clear warning instead of raising a raw exception.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from pydantic import ValidationError

from dentanote.config import Settings, get_settings
from dentanote.prompts import INVALID_JSON_PROMPT, REPAIR_PROMPT_TEMPLATE, build_initial_messages
from dentanote.schema import ALLOWED_SURFACES, ClinicalNote, clinical_note_json_schema, is_valid_fdi

logger = logging.getLogger(__name__)

PARTIAL_RESULT_WARNING = (
    "A extração não passou na validação mesmo após as tentativas de reparo. "
    "O resultado abaixo é PARCIAL e precisa de revisão cuidadosa campo a campo."
)


class ExtractionError(RuntimeError):
    """Raised only for infrastructure problems (Ollama down, timeout)."""


@dataclass(frozen=True)
class OllamaReply:
    """One model answer plus token/latency metrics (no transcript content)."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str
    latency_s: float


@dataclass(frozen=True)
class ExtractionResult:
    """Validated note + metrics for this run."""

    note: ClinicalNote
    model: str
    valid_first_try: bool
    repair_attempts: int
    prompt_tokens: int
    completion_tokens: int
    extraction_s: float
    warnings: list[str] = field(default_factory=list)
    dropped_items: list[str] = field(default_factory=list)


class OllamaClient:
    """Minimal HTTP client for a *local* Ollama server (no external calls)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def base_url(self) -> str:
        return self.settings.ollama_url.rstrip("/")

    def is_alive(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/api/version", timeout=3.0)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def available_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return []
        return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]

    def chat(self, messages: list[dict[str, str]]) -> OllamaReply:
        """One non-streaming chat call with schema-constrained output."""
        body: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "stream": False,
            "format": clinical_note_json_schema(),
            "options": {"temperature": self.settings.temperature},
        }
        if self.settings.think is False:
            body["think"] = False  # Gemma 4: avoid thinking bypassing the schema
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/api/chat",
                json=body,
                timeout=self.settings.request_timeout_s,
            )
        except httpx.HTTPError as exc:
            raise ExtractionError(
                f"não foi possível falar com o Ollama em {self.base_url}: {exc}"
            ) from exc
        latency = time.perf_counter() - started
        if response.status_code >= 400:
            detail = response.text[:300]
            raise ExtractionError(f"Ollama retornou HTTP {response.status_code}: {detail}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise ExtractionError("resposta do Ollama não é JSON.") from exc

        text = str(payload.get("message", {}).get("content", ""))
        return OllamaReply(
            text=text,
            prompt_tokens=int(payload.get("prompt_eval_count") or 0),
            completion_tokens=int(payload.get("eval_count") or 0),
            model=str(payload.get("model") or self.settings.llm_model),
            latency_s=latency,
        )


def parse_json_payload(raw: str) -> dict[str, Any] | None:
    """Parse a model answer into a dict, tolerating fences/preambles.

    Constrained decoding should make this a no-op; this is the defensive layer
    documented in ADR-001 (client-side validation is never optional).
    """
    text = raw.strip()
    if not text:
        return None
    if text.startswith("```"):
        body = text[3:]
        newline = body.find("\n")
        body = body[newline + 1 :] if newline != -1 else body
        fence_end = body.rfind("```")
        text = body[:fence_end] if fence_end != -1 else body
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def sanitize_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Deterministic safety pass before Pydantic validation.

    Scope (PROMPT.md section 4): invalid tooth numbers/surfaces are *discarded*
    and reported here — they can never block the whole note, and they are never
    "fixed" by guessing. Everything else (types, missing required names, extra
    keys) is left for Pydantic to reject, which is what drives the repair loop.
    """
    dropped: list[str] = []
    clean: dict[str, Any] = dict(payload)

    list_fields = ("findings", "materials_anesthesia", "guidance_given", "uncertain_items")
    for key in list_fields:
        value = payload.get(key, [])
        if value is None:
            clean[key] = []
        elif isinstance(value, str) or (
            isinstance(value, int | float) and not isinstance(value, bool)
        ):
            clean[key] = [value]  # scalar slip: wrap, Pydantic still checks the type

    for key in ("teeth", "procedures", "medications_prescribed"):
        if payload.get(key) is None:
            clean[key] = []

    raw_teeth = clean.get("teeth")
    if isinstance(raw_teeth, list):
        teeth: list[dict[str, Any]] = []
        for entry in raw_teeth:
            if not isinstance(entry, dict):
                dropped.append(f"item de dente inválido descartado: {entry!r}")
                continue
            number = entry.get("fdi_number")
            if not isinstance(number, int) or isinstance(number, bool) or not is_valid_fdi(number):
                dropped.append(f"número de dente inválido descartado: {number!r}")
                continue
            sanitized = dict(entry)
            surfaces = entry.get("surfaces")
            if isinstance(surfaces, list):
                kept_surfaces: list[Any] = []
                for surface in surfaces:
                    if isinstance(surface, str) and surface.strip().upper() in ALLOWED_SURFACES:
                        kept_surfaces.append(surface)
                    else:
                        dropped.append(
                            f"superfície inválida descartada no dente {number}: {surface!r}"
                        )
                sanitized["surfaces"] = kept_surfaces
            teeth.append(sanitized)
        clean["teeth"] = teeth

    raw_procedures = clean.get("procedures")
    if isinstance(raw_procedures, list):
        procedures: list[dict[str, Any]] = []
        for entry in raw_procedures:
            if not isinstance(entry, dict):
                dropped.append(f"procedimento inválido descartado: {entry!r}")
                continue
            sanitized = dict(entry)
            numbers = entry.get("tooth_fdi")
            if isinstance(numbers, list):
                kept_numbers: list[Any] = []
                for number in numbers:
                    if (
                        isinstance(number, int)
                        and not isinstance(number, bool)
                        and is_valid_fdi(number)
                    ):
                        kept_numbers.append(number)
                    elif isinstance(number, int) and not is_valid_fdi(number):
                        dropped.append(
                            f"número de dente inválido em procedimento descartado: {number!r}"
                        )
                    else:
                        kept_numbers.append(number)  # Pydantic rejects -> repair
                sanitized["tooth_fdi"] = kept_numbers
            procedures.append(sanitized)
        clean["procedures"] = procedures

    return clean, dropped


def _format_validation_errors(exc: ValidationError) -> str:
    lines: list[str] = []
    for error in exc.errors()[:12]:
        location = ".".join(str(part) for part in error["loc"]) or "(raiz)"
        lines.append(f"- {location}: {error['msg']}")
    return "\n".join(lines)


def extract_note(
    transcript: str,
    settings: Settings | None = None,
    client: OllamaClient | None = None,
) -> ExtractionResult:
    """Extract a validated ``ClinicalNote`` from a transcript (with repairs)."""
    settings = settings or get_settings()
    client = client or OllamaClient(settings)
    messages = build_initial_messages(transcript)

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_latency = 0.0
    model = settings.llm_model
    dropped: list[str] = []
    warnings: list[str] = []
    last_errors = "resposta não recebida"
    partial_payload: dict[str, Any] | None = None
    started = time.perf_counter()

    attempts = settings.max_repairs + 1
    for attempt in range(attempts):
        reply = client.chat(messages)
        total_prompt_tokens += reply.prompt_tokens
        total_completion_tokens += reply.completion_tokens
        total_latency += reply.latency_s
        model = reply.model

        parsed = parse_json_payload(reply.text)
        if parsed is None:
            last_errors = "a resposta não continha um objeto JSON válido"
            if attempt + 1 >= attempts:
                break
            messages.append({"role": "assistant", "content": reply.text[:2000]})
            messages.append({"role": "user", "content": INVALID_JSON_PROMPT})
            continue

        clean, attempt_dropped = sanitize_payload(parsed)
        dropped.extend(attempt_dropped)
        partial_payload = clean
        try:
            note = ClinicalNote.model_validate(clean)
        except ValidationError as exc:
            last_errors = _format_validation_errors(exc)
            if attempt + 1 >= attempts:
                break
            messages.append({"role": "assistant", "content": reply.text[:2000]})
            messages.append(
                {"role": "user", "content": REPAIR_PROMPT_TEMPLATE.format(errors=last_errors)}
            )
            continue

        if dropped:
            note.uncertain_items = _merge_uncertain(
                note.uncertain_items, [f"item descartado na validação: {item}" for item in dropped]
            )
        elapsed = time.perf_counter() - started
        logger.info(
            "extraction finished model=%s attempts=%d prompt_tokens=%d completion_tokens=%d "
            "ollama_s=%.2f",
            model,
            attempt,
            total_prompt_tokens,
            total_completion_tokens,
            total_latency,
        )
        return ExtractionResult(
            note=note,
            model=model,
            valid_first_try=attempt == 0,
            repair_attempts=attempt,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            extraction_s=elapsed,
            warnings=[],
            dropped_items=dropped,
        )

    # Failure path: partial, clearly-flagged result — never a raw exception.
    warnings.append(PARTIAL_RESULT_WARNING)
    warnings.append(f"último erro de validação: {last_errors}")
    note = _partial_note(partial_payload, dropped, warnings)
    elapsed = time.perf_counter() - started
    logger.warning(
        "extraction fell back to partial result model=%s attempts=%d prompt_tokens=%d",
        model,
        attempts,
        total_prompt_tokens,
    )
    return ExtractionResult(
        note=note,
        model=model,
        valid_first_try=False,
        repair_attempts=attempts - 1,
        prompt_tokens=total_prompt_tokens,
        completion_tokens=total_completion_tokens,
        extraction_s=elapsed,
        warnings=warnings,
        dropped_items=dropped,
    )


def _merge_uncertain(existing: list[str], extra: list[str]) -> list[str]:
    return list(dict.fromkeys([*existing, *extra]))


def _partial_note(
    payload: dict[str, Any] | None,
    dropped: list[str],
    warnings: list[str],
) -> ClinicalNote:
    """Build the most conservative note possible after a failed validation."""
    if payload is None:
        return ClinicalNote(uncertain_items=_merge_uncertain(dropped, warnings))
    try:
        note = ClinicalNote.model_validate(payload)
    except ValidationError:
        return ClinicalNote(
            uncertain_items=_merge_uncertain(
                [f"item descartado na validação: {item}" for item in dropped], warnings
            )
        )
    note.uncertain_items = _merge_uncertain(
        note.uncertain_items,
        [f"item descartado na validação: {item}" for item in dropped] + warnings,
    )
    return note
