"""Offline guarantees: the pipeline must work with no network at all.

These tests run with ``--disable-socket`` (see ``pyproject.toml``): any attempt
to open a socket — to a cloud API or anywhere else — fails immediately. Only
localhost is ever needed (the local Ollama server), and even that is mocked
here so CI needs no model.
"""

from __future__ import annotations

import socket
from pathlib import Path

import httpx
import pytest
from pytest_socket import SocketBlockedError

from dentanote.config import Settings
from dentanote.extract import ExtractionError, OllamaClient, extract_note
from dentanote.pipeline import run_from_text
from dentanote.render import render_note

VALID_NOTE = {
    "chief_complaint": "dor",
    "history": None,
    "findings": [],
    "teeth": [{"fdi_number": 36, "surfaces": [], "note": None}],
    "procedures": [],
    "materials_anesthesia": [],
    "medications_prescribed": [],
    "guidance_given": [],
    "follow_up": None,
    "uncertain_items": [],
}


class FakeClient:
    def chat(self, messages: list[dict[str, str]]):  # type: ignore[no-untyped-def]
        from dentanote.extract import OllamaReply

        return OllamaReply(
            text='{"teeth":[{"fdi_number":36,"surfaces":[]}]}',
            prompt_tokens=1,
            completion_tokens=1,
            model="fake",
            latency_s=0.0,
        )


def test_any_outbound_socket_is_blocked() -> None:
    with pytest.raises((OSError, socket.gaierror, SocketBlockedError, httpx.HTTPError)):
        socket.create_connection(("93.184.216.34", 80), timeout=1.0)  # public IP (example.com)


def test_pipeline_completes_with_sockets_disabled(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, metrics_path=tmp_path / "metrics.jsonl")
    result = run_from_text("Paciente Exemplo 01: dor no dente 36.", settings, client=FakeClient())
    assert result.note.teeth[0].fdi_number == 36
    assert "RASCUNHO" in render_note(result.note)


def test_external_api_urls_are_never_used(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every HTTP call must target localhost (the local Ollama server)."""
    seen: list[str] = []

    def guard_post(url: object, **kwargs: object) -> httpx.Response:  # type: ignore[no-untyped-def]
        seen.append(str(url))
        raise httpx.ConnectError("blocked by test")

    monkeypatch.setattr(httpx, "post", guard_post)
    client = OllamaClient(Settings())
    with pytest.raises(ExtractionError):
        client.chat([{"role": "user", "content": "x"}])
    assert seen
    assert all(url.startswith(("http://localhost", "http://127.0.0.1")) for url in seen), seen


def test_extract_with_mocked_client_never_touches_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("network call attempted during extraction")

    monkeypatch.setattr(httpx, "post", explode)
    monkeypatch.setattr(httpx, "get", explode)
    result = extract_note("transcrição fictícia", Settings(_env_file=None), client=FakeClient())
    assert result.note.teeth
