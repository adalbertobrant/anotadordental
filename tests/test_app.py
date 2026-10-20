"""Interface tests using Streamlit's AppTest (no server, no model, no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dentanote import doctor as doctor_module
from dentanote import pipeline as pipeline_module
from dentanote.config import Settings
from dentanote.doctor import Check
from dentanote.extract import OllamaClient, OllamaReply
from dentanote.pipeline import run_from_text as real_run_from_text

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "dentanote" / "app.py"

VALID_NOTE = {
    "chief_complaint": "dor no dente 36",
    "history": None,
    "findings": ["cárie oclusal"],
    "teeth": [{"fdi_number": 36, "surfaces": ["O"], "note": None}],
    "procedures": [{"name": "restauração em resina", "tooth_fdi": [36], "details": "classe I"}],
    "materials_anesthesia": ["mepivacaína"],
    "medications_prescribed": [],
    "guidance_given": ["evitar mastigar do lado"],
    "follow_up": "retorno em 7 dias",
    "uncertain_items": ["trecho não inteligível aos 12 s"],
}


class FakeClient:
    def chat(self, messages: list[dict[str, str]]) -> OllamaReply:
        import json

        return OllamaReply(
            text=json.dumps(VALID_NOTE),
            prompt_tokens=100,
            completion_tokens=60,
            model="fake:gemma",
            latency_s=0.01,
        )


@pytest.fixture(autouse=True)
def fake_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # type: ignore[no-untyped-def]
    """Route the app through a mocked extraction (CI must not need Ollama)."""

    def wrapper(transcript: str, settings: Settings | None = None, **kwargs: object):  # type: ignore[no-untyped-def]
        settings = Settings(metrics_path=tmp_path / "metrics.jsonl")
        return real_run_from_text(transcript, settings, client=FakeClient(), record=False)

    monkeypatch.setattr(pipeline_module, "run_from_text", wrapper)
    monkeypatch.setattr(pipeline_module, "run_from_audio", wrapper)
    # The header status probe talks to the local server; keep tests offline.
    monkeypatch.setattr(OllamaClient, "is_alive", lambda self: True)
    monkeypatch.setattr(
        doctor_module,
        "run_checks",
        lambda settings=None, client=None: [
            Check("Servidor Ollama", "ok", "mockado no teste (sem rede)")
        ],
    )
    return wrapper


def _app() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=60)


def test_app_boots_without_exceptions() -> None:
    app = _app()
    app.run()
    assert not app.exception
    assert app.tabs and len(app.tabs) == 5


def test_draft_banner_is_always_visible() -> None:
    app = _app()
    app.run()
    warnings = [element.value for element in app.warning]
    assert any("Rascunho gerado por IA local" in value for value in warnings), warnings


def test_demo_button_generates_draft_in_one_click() -> None:
    app = _app()
    app.run()
    button = next(b for b in app.button if "exemplo sintético" in b.label)
    button.click().run()
    assert not app.exception
    assert app.session_state["has_result"] is True
    assert app.session_state["note"].teeth[0].fdi_number == 36
    draft_values = [area.value for area in app.text_area]
    assert any("EVOLUÇÃO CLÍNICA — RASCUNHO" in value for value in draft_values)


def test_structured_data_tab_exposes_editable_fields() -> None:
    app = _app()
    app.run()
    next(b for b in app.button if "exemplo sintético" in b.label).click().run()
    keys = {area.key for area in app.text_area if area.key}
    assert {"edit_findings", "edit_uncertain_items", "edit_teeth", "edit_procedures"} <= keys
    inputs = {field.key for field in app.text_input if field.key}
    assert {"edit_chief_complaint", "edit_history", "edit_follow_up"} <= inputs


def test_manual_edit_feeds_the_final_text() -> None:
    app = _app()
    app.run()
    next(b for b in app.button if "exemplo sintético" in b.label).click().run()

    chief = next(f for f in app.text_input if f.key == "edit_chief_complaint")
    chief.input("queixa revisada pelo dentista").run()

    apply_button = next(b for b in app.button if "Aplicar alterações" in b.label)
    apply_button.click().run()
    assert not app.exception
    draft_values = [area.value for area in app.text_area]
    assert any("queixa revisada pelo dentista" in value for value in draft_values)


def test_reextract_from_edited_transcript_does_not_crash() -> None:
    """The re-extract button lives *below* the editor widget.

    Writing `transcript_editor` there raises StreamlitAPIException ("cannot be
    modified after the widget ... is instantiated") — the editor must simply
    keep the text that was just extracted.
    """
    app = _app()
    app.run()
    next(b for b in app.button if "exemplo sintético" in b.label).click().run()
    assert not app.exception

    editor = next(a for a in app.text_area if a.key == "transcript_editor")
    editor.set_value("transcrição editada pelo dentista").run()
    assert not app.exception

    next(b for b in app.button if "Re-extrair" in b.label).click().run()
    assert not app.exception
    assert app.session_state["transcript"] == "transcrição editada pelo dentista"
    assert app.session_state["note"].chief_complaint == "dor no dente 36"
    editor = next(a for a in app.text_area if a.key == "transcript_editor")
    assert editor.value == "transcrição editada pelo dentista"


def test_metrics_tab_shows_only_sizes_and_timings() -> None:
    app = _app()
    app.run()
    next(b for b in app.button if "exemplo sintético" in b.label).click().run()
    metrics = app.session_state["metrics"]
    assert set(metrics) >= {"total_s", "extraction_s", "prompt_tokens", "llm_model"}
    assert "transcript" not in metrics
    assert "note" not in metrics


def test_language_toggle_switches_ui_to_english() -> None:
    app = _app()
    app.run()
    lang = next(radio for radio in app.radio if radio.label == "Idioma / Language")
    lang.set_value("EN").run()
    assert not app.exception
    assert app.session_state["lang"] == "EN"
    assert [tab.label for tab in app.tabs] == [
        "1️⃣ Input",
        "2️⃣ Transcript",
        "3️⃣ Structured data",
        "4️⃣ Clinical note",
        "5️⃣ Metrics",
    ]
    banners = [element.value for element in app.warning]
    assert any("AI-generated clinical note draft" in value for value in banners), banners


def test_language_defaults_to_portuguese() -> None:
    app = _app()
    app.run()
    lang = next(radio for radio in app.radio if radio.label == "Idioma / Language")
    assert lang.value == "PT"
    assert app.tabs[0].label == "1️⃣ Entrada"
