"""Extraction tests with a mocked Ollama client (CI must not need a model)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import pytest
from pydantic import ValidationError

from dentanote.config import Settings
from dentanote.extract import (
    PARTIAL_RESULT_WARNING,
    ExtractionError,
    OllamaClient,
    OllamaReply,
    extract_note,
    parse_json_payload,
    sanitize_payload,
)
from dentanote.prompts import SYSTEM_PROMPT, build_initial_messages
from dentanote.schema import ClinicalNote

VALID_NOTE: dict[str, Any] = {
    "chief_complaint": "dor no dente de trás",
    "history": None,
    "findings": ["cárie oclusal"],
    "teeth": [{"fdi_number": 36, "surfaces": ["O"], "note": None}],
    "procedures": [{"name": "restauração em resina", "tooth_fdi": [36], "details": "classe I"}],
    "materials_anesthesia": ["lidocaína 2%"],
    "medications_prescribed": [],
    "guidance_given": ["evitar mastigar do lado"],
    "follow_up": "retorno em 7 dias",
    "uncertain_items": [],
}


@dataclass
class FakeOllamaClient:
    """Scripted client: returns queued texts, records every message sent."""

    replies: list[str]
    prompt_tokens: int = 100
    completion_tokens: int = 60
    calls: list[list[dict[str, str]]] = field(default_factory=list)

    def chat(self, messages: list[dict[str, str]]) -> OllamaReply:
        self.calls.append(list(messages))
        text = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        return OllamaReply(
            text=text,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            model="fake:gemma",
            latency_s=0.01,
        )


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **overrides)


# --- parse_json_payload -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
        ('Aqui está o JSON:\n{"a": 1}', {"a": 1}),
        ('antes {"a": {"b": 2}} depois', {"a": {"b": 2}}),
        ("[1, 2]", None),
        ("não é json", None),
        ("", None),
        ("{}", {}),
    ],
)
def test_parse_json_payload(raw: str, expected: dict[str, Any] | None) -> None:
    assert parse_json_payload(raw) == expected


# --- sanitize_payload -------------------------------------------------------


def test_sanitize_drops_invalid_fdi_and_reports() -> None:
    payload = {**VALID_NOTE, "teeth": [{"fdi_number": 99, "surfaces": []}]}
    clean, dropped = sanitize_payload(payload)
    assert clean["teeth"] == []
    assert any("99" in item for item in dropped)


def test_sanitize_drops_invalid_surface_only() -> None:
    payload = {
        **VALID_NOTE,
        "teeth": [{"fdi_number": 36, "surfaces": ["O", "QQ"], "note": None}],
    }
    clean, dropped = sanitize_payload(payload)
    assert clean["teeth"][0]["surfaces"] == ["O"]
    assert any("superfície" in item for item in dropped)


def test_sanitize_keeps_valid_procedure_but_filters_teeth() -> None:
    payload = {
        **VALID_NOTE,
        "procedures": [{"name": "exodontia", "tooth_fdi": [18, 100], "details": None}],
    }
    clean, dropped = sanitize_payload(payload)
    assert clean["procedures"][0]["tooth_fdi"] == [18]
    assert any("100" in item for item in dropped)


def test_sanitize_wraps_scalar_findings_to_list() -> None:
    clean, dropped = sanitize_payload({**VALID_NOTE, "findings": "cárie oclusal"})
    assert clean["findings"] == ["cárie oclusal"]
    assert dropped == []


def test_sanitize_leaves_type_errors_for_pydantic_repair() -> None:
    """Missing required names must fail validation so the repair loop kicks in."""
    clean, dropped = sanitize_payload(
        {**VALID_NOTE, "medications_prescribed": [{"dose": "500 mg"}]}
    )
    assert clean["medications_prescribed"] == [{"dose": "500 mg"}]
    assert dropped == []
    with pytest.raises(ValidationError):
        ClinicalNote.model_validate(clean)


# --- extract_note with fake client ------------------------------------------


def test_first_try_success() -> None:
    client = FakeOllamaClient(replies=[json.dumps(VALID_NOTE)])
    result = extract_note("transcrição fictícia", settings(), client=client)
    assert result.valid_first_try is True
    assert result.repair_attempts == 0
    assert result.note.procedures[0].name == "restauração em resina"
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 60
    assert result.warnings == []


def test_repair_loop_uses_validation_error() -> None:
    broken = {**VALID_NOTE, "medications_prescribed": [{"dose": "600 mg"}]}
    client = FakeOllamaClient(replies=[json.dumps(broken), json.dumps(VALID_NOTE)])
    result = extract_note("transcrição fictícia", settings(max_repairs=2), client=client)
    assert result.valid_first_try is False
    assert result.repair_attempts == 1
    assert result.note.teeth[0].fdi_number == 36
    repair_message = client.calls[1][-1]
    assert repair_message["role"] == "user"
    assert "não passou na validação" in repair_message["content"]
    assert "medications_prescribed.0.name" in repair_message["content"]


def test_invalid_json_triggers_repair_prompt() -> None:
    client = FakeOllamaClient(replies=["desculpe, não posso ajudar", json.dumps(VALID_NOTE)])
    result = extract_note("transcrição fictícia", settings(), client=client)
    assert result.repair_attempts == 1
    assert "JSON válido" in client.calls[1][-1]["content"]


def test_exhausted_repairs_return_partial_with_warning() -> None:
    client = FakeOllamaClient(replies=["nada de json"])
    result = extract_note("transcrição fictícia", settings(max_repairs=2), client=client)
    assert result.valid_first_try is False
    assert result.warnings and PARTIAL_RESULT_WARNING in result.warnings[0]
    assert isinstance(result.note, ClinicalNote)
    assert result.note.uncertain_items  # everything uncertain is surfaced


def test_invalid_fdi_is_dropped_without_repair_and_flagged() -> None:
    payload = {**VALID_NOTE, "teeth": [{"fdi_number": 91, "surfaces": []}]}
    client = FakeOllamaClient(replies=[json.dumps(payload)])
    result = extract_note("transcrição fictícia", settings(), client=client)
    assert result.valid_first_try is True  # sanitizer handled it deterministically
    assert result.note.teeth == []
    assert result.note.uncertain_items
    assert any("91" in item for item in result.dropped_items)


def test_prompt_messages_include_rules_and_examples() -> None:
    messages = build_initial_messages("transcrição fictícia")
    assert messages[0]["role"] == "system"
    assert "Use SOMENTE o que está dito" in SYSTEM_PROMPT
    assert "Não faça diagnóstico" in SYSTEM_PROMPT
    assert "uncertain_items" in SYSTEM_PROMPT
    # 1 system + 3*(user+assistant) few-shot + 1 final user
    assert len(messages) == 8
    assert messages[-1]["content"].endswith("transcrição fictícia")
    assistants = [m for m in messages if m["role"] == "assistant"]
    assert len(assistants) == 3
    for message in assistants:
        ClinicalNote.model_validate(json.loads(message["content"]))


def test_extraction_logs_never_contain_the_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_transcript = "Paciente Exemplo 99 com dor no dente 36"
    client = FakeOllamaClient(replies=[json.dumps(VALID_NOTE)])
    with caplog.at_level(logging.DEBUG):
        extract_note(secret_transcript, settings(), client=client)
    joined = " ".join(record.getMessage() for record in caplog.records)
    assert "Paciente Exemplo 99" not in joined
    assert "dor no dente 36" not in joined


@pytest.mark.enable_socket
def test_ollama_client_reports_dead_server() -> None:
    client = OllamaClient(Settings(_env_file=None, ollama_url="http://127.0.0.1:9"))
    assert client.is_alive() is False
    with pytest.raises(ExtractionError):
        client.chat([{"role": "user", "content": "oi"}])


def test_sanitize_then_validate_roundtrip() -> None:
    clean, _ = sanitize_payload(VALID_NOTE)
    note = ClinicalNote.model_validate(clean)
    assert note.model_dump()["teeth"][0]["fdi_number"] == 36
    with pytest.raises(ValidationError):
        ClinicalNote.model_validate({**VALID_NOTE, "diagnosis": "x"})  # type: ignore[call-arg]
