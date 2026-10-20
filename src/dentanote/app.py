"""DentaNote Streamlit interface (all local, no external CDN).

Tabs follow the workflow: input -> editable transcript -> editable structured
data -> final draft (copy) -> run metrics. The professional is the authority:
any manual edit feeds the final text, and the draft banner is always visible.

The UI language toggles PT/EN in the header (default PT-BR). The rendered note
itself stays in PT-BR clinical format either way: it is the artifact meant for
the Brazilian record, not UI text.
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st

from dentanote import __version__
from dentanote.config import Settings, get_settings
from dentanote.doctor import run_checks, summarize
from dentanote.extract import ExtractionError, OllamaClient
from dentanote.pipeline import PipelineResult, run_from_audio, run_from_text
from dentanote.render import render_note
from dentanote.schema import ClinicalNote
from dentanote.transcribe import TranscriptionError

st.set_page_config(
    page_title="DentaNote",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SUPPORTED_UPLOAD = ("wav", "mp3", "m4a", "ogg", "webm")

LIST_FIELDS = ("findings", "materials_anesthesia", "guidance_given", "uncertain_items")
TEXT_FIELDS = ("chief_complaint", "history", "follow_up")
JSON_FIELDS = ("teeth", "procedures", "medications_prescribed")

# UI strings. The PT banner comes from settings (configurable); everything else
# lives here so both languages stay in sync in one place.
STRINGS: dict[str, dict[str, str]] = {
    "pt": {
        "subtitle": "Evolução clínica odontológica gerada 100% localmente — "
        "o áudio e o texto nunca saem deste computador.",
        "offline": "Ollama indisponível",
        "tab_input": "1️⃣ Entrada",
        "tab_transcript": "2️⃣ Transcrição",
        "tab_data": "3️⃣ Dados estruturados",
        "tab_draft": "4️⃣ Evolução clínica",
        "tab_metrics": "5️⃣ Métricas",
        "source_header": "Fonte da consulta",
        "load_sample": "✨ Carregar exemplo sintético (demo em 1 clique)",
        "load_spinner": "Extraindo com o modelo local...",
        "load_success": "Exemplo carregado. Veja as abas 2 a 5.",
        "how_to_input": "Como você quer entrar com a consulta?",
        "opt_paste": "Texto colado",
        "opt_audio": "Arquivo de áudio",
        "opt_record": "Gravar agora",
        "paste_label": "Cole a transcrição (ou digite um resumo ditado)",
        "paste_placeholder": "Paciente Exemplo 01, retorno. Refere dor no dente ...",
        "generate": "Gerar rascunho",
        "extract_spinner": "Extraindo dados clínicos com o modelo local...",
        "audio_spinner": "Transcrevendo com Whisper (isso pode demorar no primeiro uso)...",
        "record_spinner": "Transcrevendo a gravação...",
        "done": "Rascunho gerado — revise nas próximas abas.",
        "audio_uploader": "wav, mp3, m4a, ogg ou webm",
        "transcribe": "Transcrever e gerar rascunho",
        "record_label": "Grave o resumo da consulta",
        "record_transcribe": "Transcrever gravação e gerar rascunho",
        "empty_input": "Gere um rascunho na aba **Entrada** (ou carregue o exemplo sintético).",
        "empty_generic": "Gere um rascunho na aba **Entrada**.",
        "transcript_sub": "Transcrição (editável)",
        "transcript_caption": "Corrija erros de reconhecimento antes de extrair de novo — "
        "o texto é a fonte de verdade.",
        "transcript_label": "Transcrição",
        "reextract": "🔁 Re-extrair com esta transcrição",
        "reextract_spinner": "Extraindo com o modelo local...",
        "reextract_success": "Extração atualizada.",
        "data_sub": "Dados estruturados (editáveis)",
        "data_caption": "Você é a autoridade final: qualquer edição aqui muda o texto da aba Evolução.",
        "chief": "Queixa principal",
        "history": "Histórico",
        "follow_up": "Retorno",
        "findings": "Achados (1 por linha)",
        "materials": "Materiais e anestésicos (1 por linha)",
        "guidance": "Orientações (1 por linha)",
        "uncertain_area": "⚠ Conferir antes de salvar (1 por linha)",
        "teeth_json": "Dentes (JSON)",
        "procedures_json": "Procedimentos (JSON)",
        "meds_json": "Medicamentos (JSON)",
        "apply": "💾 Aplicar alterações ao rascunho",
        "apply_error": "Não consegui aplicar as alterações: {error}",
        "apply_success": "Rascunho atualizado com suas alterações (aba Evolução).",
        "uncertain_box": "⚠ Conferir antes de salvar:",
        "draft_label": "Rascunho de evolução clínica",
        "download": "⬇️ Baixar rascunho (.txt)",
        "download_name": "dentanote_rascunho.txt",
        "draft_caption": "Copie (ícone no canto superior direito do bloco acima) e cole no "
        "prontuário **após revisar**. O texto é montado por template determinístico — "
        "nada é inventado nesta etapa.",
        "metrics_sub": "Métricas da execução",
        "metrics_caption": "Somente tempos, contagens e tamanhos — nenhum dado clínico é registrado.",
        "metrics_llm": "**Modelo LLM:**",
        "metrics_whisper": "**Whisper:**",
        "metrics_repairs": "**Tentativas de reparo:**",
        "metrics_uncertain": "**Itens a conferir:**",
        "metrics_file": "Arquivo de métricas: `{path}` (JSONL local, sem PHI).",
        "footer": "DentaNote é uma ferramenta de apoio: o profissional revisa e assume "
        "a evolução. Não faz diagnóstico nem sugere conduta. Dados 100% sintéticos "
        "nas demostrações.",
    },
    "en": {
        "subtitle": "Dental clinical notes generated 100% locally — audio and text "
        "never leave this computer.",
        "offline": "Ollama unavailable",
        "tab_input": "1️⃣ Input",
        "tab_transcript": "2️⃣ Transcript",
        "tab_data": "3️⃣ Structured data",
        "tab_draft": "4️⃣ Clinical note",
        "tab_metrics": "5️⃣ Metrics",
        "source_header": "Appointment source",
        "load_sample": "✨ Load synthetic sample (1-click demo)",
        "load_spinner": "Extracting with the local model...",
        "load_success": "Sample loaded. See tabs 2 to 5.",
        "how_to_input": "How do you want to enter the appointment?",
        "opt_paste": "Pasted text",
        "opt_audio": "Audio file",
        "opt_record": "Record now",
        "paste_label": "Paste the transcript (or type a dictated summary)",
        "paste_placeholder": "Sample Patient 01, recall. Reports pain in tooth ...",
        "generate": "Generate draft",
        "extract_spinner": "Extracting clinical data with the local model...",
        "audio_spinner": "Transcribing with Whisper (this may take a while on first use)...",
        "record_spinner": "Transcribing the recording...",
        "done": "Draft generated — review it in the next tabs.",
        "audio_uploader": "wav, mp3, m4a, ogg or webm",
        "transcribe": "Transcribe and generate draft",
        "record_label": "Record the appointment summary",
        "record_transcribe": "Transcribe recording and generate draft",
        "empty_input": "Generate a draft in the **Input** tab (or load the synthetic sample).",
        "empty_generic": "Generate a draft in the **Input** tab.",
        "transcript_sub": "Transcript (editable)",
        "transcript_caption": "Fix recognition errors before extracting again — the text is "
        "the source of truth.",
        "transcript_label": "Transcript",
        "reextract": "🔁 Re-extract with this transcript",
        "reextract_spinner": "Extracting with the local model...",
        "reextract_success": "Extraction updated.",
        "data_sub": "Structured data (editable)",
        "data_caption": "You are the final authority: any edit here changes the Clinical note tab.",
        "chief": "Chief complaint",
        "history": "History",
        "follow_up": "Follow-up",
        "findings": "Findings (one per line)",
        "materials": "Materials and anesthetics (one per line)",
        "guidance": "Guidance given (one per line)",
        "uncertain_area": "⚠ Review before saving (one per line)",
        "teeth_json": "Teeth (JSON)",
        "procedures_json": "Procedures (JSON)",
        "meds_json": "Medications (JSON)",
        "apply": "💾 Apply changes to the draft",
        "apply_error": "Could not apply the changes: {error}",
        "apply_success": "Draft updated with your changes (Clinical note tab).",
        "uncertain_box": "⚠ Review before saving:",
        "draft_label": "Clinical note draft",
        "download": "⬇️ Download draft (.txt)",
        "download_name": "dentanote_draft.txt",
        "draft_caption": "Copy (icon at the top right of the block above) and paste into the "
        "record **after reviewing**. The text is assembled by a deterministic template — "
        "nothing is invented at this step. The note itself is rendered in PT-BR clinical "
        "format, the standard for Brazilian records.",
        "metrics_sub": "Run metrics",
        "metrics_caption": "Timings, counts and sizes only — no clinical data is recorded.",
        "metrics_llm": "**LLM model:**",
        "metrics_whisper": "**Whisper:**",
        "metrics_repairs": "**Repair attempts:**",
        "metrics_uncertain": "**Items to review:**",
        "metrics_file": "Metrics file: `{path}` (local JSONL, no PHI).",
        "footer": "DentaNote is a support tool: the professional reviews and owns the note. "
        "It makes no diagnosis and suggests no treatment. 100% synthetic data in the demos.",
    },
}


def _repo_root() -> Path | None:
    """Locate ``data/synthetic`` (works from the repo and from an install)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "data" / "synthetic" / "transcripts").is_dir():
            return parent
    return None


def _sample_transcript() -> str | None:
    root = _repo_root()
    if root is None:
        return None
    sample = root / "data" / "synthetic" / "transcripts" / "restauracao_classe_I.txt"
    return sample.read_text(encoding="utf-8") if sample.exists() else None


@st.cache_data(ttl=60, show_spinner=False)
def _status(ollama_url: str, llm_model: str, whisper_model: str) -> dict[str, Any]:
    """Local status probe (cached so the UI does not spam the local server)."""
    client = OllamaClient(Settings(ollama_url=ollama_url))
    return {
        "ollama_alive": client.is_alive(),
        "llm_model": llm_model,
        "whisper_model": whisper_model,
        "doctor": summarize(run_checks(Settings(ollama_url=ollama_url))),
    }


def _set_note_widgets(note: ClinicalNote) -> None:
    """Point every editor widget at the current note (called before widgets)."""
    payload = note.model_dump(mode="json")
    for field in TEXT_FIELDS:
        st.session_state[f"edit_{field}"] = payload.get(field) or ""
    for field in LIST_FIELDS:
        st.session_state[f"edit_{field}"] = "\n".join(payload.get(field) or [])
    for field in JSON_FIELDS:
        st.session_state[f"edit_{field}"] = json.dumps(
            payload.get(field), ensure_ascii=False, indent=2
        )


def _store_result(result: PipelineResult) -> None:
    st.session_state["transcript"] = result.transcript
    st.session_state["transcript_editor"] = result.transcript
    st.session_state["note"] = result.note
    st.session_state["warnings"] = result.warnings
    st.session_state["metrics"] = result.metrics.to_record()
    st.session_state["has_result"] = True
    _set_note_widgets(result.note)


def _read_note_from_widgets() -> ClinicalNote:
    payload: dict[str, Any] = {}
    for field in TEXT_FIELDS:
        value = st.session_state.get(f"edit_{field}", "").strip()
        payload[field] = value or None
    for field in LIST_FIELDS:
        raw = st.session_state.get(f"edit_{field}", "")
        payload[field] = [line.strip() for line in raw.splitlines() if line.strip()]
    for field in JSON_FIELDS:
        raw = st.session_state.get(f"edit_{field}", "[]").strip()
        payload[field] = json.loads(raw) if raw else []
    return ClinicalNote.model_validate(payload)


def _run_and_store(source: str, *, audio_path: Path | None = None, text: str | None = None) -> None:
    settings = get_settings()
    try:
        if audio_path is not None:
            result = run_from_audio(audio_path, settings)
        else:
            result = run_from_text(text or "", settings)
    except (ExtractionError, TranscriptionError) as exc:
        st.error(str(exc))
        return
    _store_result(result)
    st.session_state["last_source"] = source


def _save_upload(data: bytes | io.BytesIO, suffix: str) -> Path:
    """Persist an upload or a recorded blob (Streamlit hands back either)."""
    payload = data.getvalue() if isinstance(data, io.BytesIO) else data
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(payload)
        return Path(tmp.name)


# ---------------------------------------------------------------- page chrome
settings = get_settings()
status = _status(settings.ollama_url, settings.llm_model, settings.whisper_model)

st.markdown(
    """
    <style>
      .block-container { padding-top: 1.2rem; }
      div[data-testid="stBanner"] { margin-bottom: 0.4rem; }
      .dentanote-title { font-size: 1.6rem; font-weight: 700; margin-bottom: 0; }
      .dentanote-sub { color: #5b6470; font-size: 0.9rem; margin-top: 0; }
      .dentanote-ok { color: #1a7f37; font-weight: 600; }
      .dentanote-bad { color: #b42318; font-weight: 600; }
      .dentanote-uncertain {
        border-left: 4px solid #f59e0b; background: #fff7ed;
        padding: 0.6rem 0.9rem; border-radius: 4px; margin: 0.5rem 0;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# Language toggle first: every string below reads the chosen language.
st.radio(
    "Idioma / Language",
    ("PT", "EN"),
    horizontal=True,
    key="lang",
    label_visibility="collapsed",
)
T = STRINGS[st.session_state.get("lang", "PT").lower()]

title_col, _pad = st.columns([5, 1])
with title_col:
    st.markdown('<p class="dentanote-title">🦷 DentaNote</p>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="dentanote-sub">{T["subtitle"]}</p>',
        unsafe_allow_html=True,
    )

online_dot = "🟢" if status["ollama_alive"] else "🔴"
online_cls = "dentanote-ok" if status["ollama_alive"] else "dentanote-bad"
online_text = "local/online" if status["ollama_alive"] else T["offline"]
st.markdown(
    f'<p class="{online_cls}">{online_dot} {online_text} · LLM: <code>{status["llm_model"]}</code>'
    f" · Whisper: <code>{status['whisper_model']}</code> · v{__version__}</p>",
    unsafe_allow_html=True,
)
if st.session_state.get("lang", "PT") == "EN":
    st.warning(
        "AI-generated clinical note draft. Review before saving to the record. "
        "No data leaves this computer."
    )
else:
    st.warning(settings.draft_banner)

tab_input, tab_transcript, tab_data, tab_draft, tab_metrics = st.tabs(
    [T["tab_input"], T["tab_transcript"], T["tab_data"], T["tab_draft"], T["tab_metrics"]]
)

# ------------------------------------------------------------------- 1. input
with tab_input:
    st.subheader(T["source_header"])
    sample = _sample_transcript()
    if sample and st.button(T["load_sample"], type="primary"):
        with st.spinner(T["load_spinner"]):
            _run_and_store("exemplo", text=sample)
        st.success(T["load_success"])

    source = st.radio(
        T["how_to_input"],
        [T["opt_paste"], T["opt_audio"], T["opt_record"]],
        horizontal=True,
    )

    if source == T["opt_paste"]:
        pasted = st.text_area(
            T["paste_label"],
            height=220,
            placeholder=T["paste_placeholder"],
        )
        if st.button(T["generate"], type="primary", disabled=not pasted.strip()):
            with st.spinner(T["extract_spinner"]):
                _run_and_store("texto", text=pasted)
            st.success(T["done"])

    elif source == T["opt_audio"]:
        uploaded = st.file_uploader(T["audio_uploader"], type=list(SUPPORTED_UPLOAD))
        if uploaded is not None and st.button(T["transcribe"], type="primary"):
            suffix = Path(uploaded.name).suffix or ".wav"
            path = _save_upload(uploaded.getvalue(), suffix)
            with st.spinner(T["audio_spinner"]):
                _run_and_store("arquivo", audio_path=path)
            path.unlink(missing_ok=True)
            st.success(T["done"])

    else:
        audio_bytes = st.audio_input(T["record_label"])
        if audio_bytes and st.button(T["record_transcribe"], type="primary"):
            path = _save_upload(audio_bytes, ".wav")
            with st.spinner(T["record_spinner"]):
                _run_and_store("gravacao", audio_path=path)
            path.unlink(missing_ok=True)
            st.success(T["done"])

# --------------------------------------------------------------- 2. transcript
with tab_transcript:
    if not st.session_state.get("has_result"):
        st.info(T["empty_input"])
    else:
        st.subheader(T["transcript_sub"])
        st.caption(T["transcript_caption"])
        st.text_area(
            T["transcript_label"],
            key="transcript_editor",
            height=300,
        )
        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button(T["reextract"]):
                edited = st.session_state.get("transcript_editor", "").strip()
                if edited:
                    with st.spinner(T["reextract_spinner"]):
                        _run_and_store("transcrição editada", text=edited)
                    st.success(T["reextract_success"])

# ----------------------------------------------------------------- 3. structs
with tab_data:
    if not st.session_state.get("has_result"):
        st.info(T["empty_generic"])
    else:
        st.subheader(T["data_sub"])
        st.caption(T["data_caption"])

        col1, col2 = st.columns(2)
        with col1:
            st.text_input(T["chief"], key="edit_chief_complaint")
            st.text_input(T["history"], key="edit_history")
            st.text_input(T["follow_up"], key="edit_follow_up")
            st.text_area(T["findings"], key="edit_findings", height=110)
            st.text_area(T["materials"], key="edit_materials_anesthesia", height=90)
        with col2:
            st.text_area(T["guidance"], key="edit_guidance_given", height=110)
            st.text_area(
                T["uncertain_area"],
                key="edit_uncertain_items",
                height=90,
            )
            st.text_area(T["teeth_json"], key="edit_teeth", height=110)
            st.text_area(T["procedures_json"], key="edit_procedures", height=110)
            st.text_area(T["meds_json"], key="edit_medications_prescribed", height=110)

        if st.button(T["apply"]):
            try:
                edited_note = _read_note_from_widgets()
            except (ValueError, json.JSONDecodeError) as exc:
                st.error(T["apply_error"].format(error=exc))
            else:
                st.session_state["note"] = edited_note
                st.session_state["warnings"] = []
                st.success(T["apply_success"])

# -------------------------------------------------------------------- 4. draft
with tab_draft:
    if not st.session_state.get("has_result"):
        st.info(T["empty_generic"])
    else:
        note: ClinicalNote = st.session_state.get("note") or ClinicalNote()
        rendered = render_note(note)

        for warning in st.session_state.get("warnings", []):
            st.warning(warning)

        if note.uncertain_items:
            st.markdown(
                f'<div class="dentanote-uncertain"><b>{T["uncertain_box"]}</b><br>'
                + "<br>".join(f"• {item}" for item in note.uncertain_items)
                + "</div>",
                unsafe_allow_html=True,
            )

        # No widget key: the draft view must refresh from the template on every
        # rerun (edits belong to the structured/transcript tabs, ADR-002).
        st.text_area(T["draft_label"], value=rendered, height=420)

        col_copy, col_download = st.columns([1, 1])
        with col_copy:
            st.code(rendered, language=None)  # Streamlit's built-in copy button
        with col_download:
            st.download_button(
                T["download"],
                data=rendered,
                file_name=T["download_name"],
                mime="text/plain",
            )
        st.caption(T["draft_caption"])

# ----------------------------------------------------------------- 5. metrics
with tab_metrics:
    metrics = st.session_state.get("metrics")
    if not metrics:
        st.info(T["empty_generic"])
    else:
        st.subheader(T["metrics_sub"])
        st.caption(T["metrics_caption"])
        st.json(metrics)
        st.markdown(
            f"{T['metrics_llm']} `{metrics.get('llm_model')}` · "
            f"{T['metrics_whisper']} `{metrics.get('whisper_model')}` · "
            f"{T['metrics_repairs']} {metrics.get('repair_attempts')} · "
            f"{T['metrics_uncertain']} {metrics.get('uncertain_count')}"
        )
        st.caption(T["metrics_file"].format(path=settings.metrics_path))

st.caption(T["footer"])
