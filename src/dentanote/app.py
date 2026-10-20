"""DentaNote Streamlit interface (all local, no external CDN).

Tabs follow the workflow: input -> editable transcript -> editable structured
data -> final draft (copy) -> run metrics. The professional is the authority:
any manual edit feeds the final text, and the draft banner is always visible.
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

st.markdown('<p class="dentanote-title">🦷 DentaNote</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="dentanote-sub">Evolução clínica odontológica gerada 100% localmente — '
    "o áudio e o texto nunca saem deste computador.</p>",
    unsafe_allow_html=True,
)

online_dot = "🟢" if status["ollama_alive"] else "🔴"
online_cls = "dentanote-ok" if status["ollama_alive"] else "dentanote-bad"
online_text = "local/online" if status["ollama_alive"] else "Ollama indisponível"
st.markdown(
    f'<p class="{online_cls}">{online_dot} {online_text} · LLM: <code>{status["llm_model"]}</code>'
    f" · Whisper: <code>{status['whisper_model']}</code> · v{__version__}</p>",
    unsafe_allow_html=True,
)
st.warning(settings.draft_banner)

tab_input, tab_transcript, tab_data, tab_draft, tab_metrics = st.tabs(
    ["1️⃣ Entrada", "2️⃣ Transcrição", "3️⃣ Dados estruturados", "4️⃣ Evolução clínica", "5️⃣ Métricas"]
)

# ------------------------------------------------------------------- 1. input
with tab_input:
    st.subheader("Fonte da consulta")
    sample = _sample_transcript()
    if sample and st.button("✨ Carregar exemplo sintético (demo em 1 clique)", type="primary"):
        with st.spinner("Extraindo com o modelo local..."):
            _run_and_store("exemplo", text=sample)
        st.success("Exemplo carregado. Veja as abas 2 a 5.")

    source = st.radio(
        "Como você quer entrar com a consulta?",
        ["Texto colado", "Arquivo de áudio", "Gravar agora"],
        horizontal=True,
    )

    if source == "Texto colado":
        pasted = st.text_area(
            "Cole a transcrição (ou digite um resumo ditado)",
            height=220,
            placeholder="Paciente Exemplo 01, retorno. Refere dor no dente ...",
        )
        if st.button("Gerar rascunho", type="primary", disabled=not pasted.strip()):
            with st.spinner("Extraindo dados clínicos com o modelo local..."):
                _run_and_store("texto", text=pasted)
            st.success("Rascunho gerado — revise nas próximas abas.")

    elif source == "Arquivo de áudio":
        uploaded = st.file_uploader("wav, mp3, m4a, ogg ou webm", type=list(SUPPORTED_UPLOAD))
        if uploaded is not None and st.button("Transcrever e gerar rascunho", type="primary"):
            suffix = Path(uploaded.name).suffix or ".wav"
            path = _save_upload(uploaded.getvalue(), suffix)
            with st.spinner("Transcrevendo com Whisper (isso pode demorar no primeiro uso)..."):
                _run_and_store("arquivo", audio_path=path)
            path.unlink(missing_ok=True)
            st.success("Rascunho gerado — revise nas próximas abas.")

    else:
        audio_bytes = st.audio_input("Grave o resumo da consulta")
        if audio_bytes and st.button("Transcrever gravação e gerar rascunho", type="primary"):
            path = _save_upload(audio_bytes, ".wav")
            with st.spinner("Transcrevendo a gravação..."):
                _run_and_store("gravacao", audio_path=path)
            path.unlink(missing_ok=True)
            st.success("Rascunho gerado — revise nas próximas abas.")

# --------------------------------------------------------------- 2. transcript
with tab_transcript:
    if not st.session_state.get("has_result"):
        st.info("Gere um rascunho na aba **Entrada** (ou carregue o exemplo sintético).")
    else:
        st.subheader("Transcrição (editável)")
        st.caption(
            "Corrija erros de reconhecimento antes de extrair de novo — o texto é a fonte de verdade."
        )
        st.text_area(
            "Transcrição",
            key="transcript_editor",
            height=300,
        )
        col_a, col_b = st.columns([1, 3])
        with col_a:
            if st.button("🔁 Re-extrair com esta transcrição"):
                edited = st.session_state.get("transcript_editor", "").strip()
                if edited:
                    with st.spinner("Extraindo com o modelo local..."):
                        _run_and_store("transcrição editada", text=edited)
                    st.success("Extração atualizada.")

# ----------------------------------------------------------------- 3. structs
with tab_data:
    if not st.session_state.get("has_result"):
        st.info("Gere um rascunho na aba **Entrada**.")
    else:
        st.subheader("Dados estruturados (editáveis)")
        st.caption("Você é a autoridade final: qualquer edição aqui muda o texto da aba Evolução.")

        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Queixa principal", key="edit_chief_complaint")
            st.text_input("Histórico", key="edit_history")
            st.text_input("Retorno", key="edit_follow_up")
            st.text_area("Achados (1 por linha)", key="edit_findings", height=110)
            st.text_area(
                "Materiais e anestésicos (1 por linha)", key="edit_materials_anesthesia", height=90
            )
        with col2:
            st.text_area("Orientações (1 por linha)", key="edit_guidance_given", height=110)
            st.text_area(
                "⚠ Conferir antes de salvar (1 por linha)",
                key="edit_uncertain_items",
                height=90,
            )
            st.text_area("Dentes (JSON)", key="edit_teeth", height=110)
            st.text_area("Procedimentos (JSON)", key="edit_procedures", height=110)
            st.text_area("Medicamentos (JSON)", key="edit_medications_prescribed", height=110)

        if st.button("💾 Aplicar alterações ao rascunho"):
            try:
                edited_note = _read_note_from_widgets()
            except (ValueError, json.JSONDecodeError) as exc:
                st.error(f"Não consegui aplicar as alterações: {exc}")
            else:
                st.session_state["note"] = edited_note
                st.session_state["warnings"] = []
                st.success("Rascunho atualizado com suas alterações (aba Evolução).")

# -------------------------------------------------------------------- 4. draft
with tab_draft:
    if not st.session_state.get("has_result"):
        st.info("Gere um rascunho na aba **Entrada**.")
    else:
        note: ClinicalNote = st.session_state.get("note") or ClinicalNote()
        rendered = render_note(note)

        for warning in st.session_state.get("warnings", []):
            st.warning(warning)

        if note.uncertain_items:
            st.markdown(
                '<div class="dentanote-uncertain"><b>⚠ Conferir antes de salvar:</b><br>'
                + "<br>".join(f"• {item}" for item in note.uncertain_items)
                + "</div>",
                unsafe_allow_html=True,
            )

        # No widget key: the draft view must refresh from the template on every
        # rerun (edits belong to the structured/transcript tabs, ADR-002).
        st.text_area("Rascunho de evolução clínica", value=rendered, height=420)

        col_copy, col_download = st.columns([1, 1])
        with col_copy:
            st.code(rendered, language=None)  # Streamlit's built-in copy button
        with col_download:
            st.download_button(
                "⬇️ Baixar rascunho (.txt)",
                data=rendered,
                file_name="dentanote_rascunho.txt",
                mime="text/plain",
            )
        st.caption(
            "Copie (ícone no canto superior direito do bloco acima) e cole no prontuário "
            "**após revisar**. O texto é montado por template determinístico — nada é "
            "inventado nesta etapa."
        )

# ----------------------------------------------------------------- 5. metrics
with tab_metrics:
    metrics = st.session_state.get("metrics")
    if not metrics:
        st.info("Gere um rascunho na aba **Entrada**.")
    else:
        st.subheader("Métricas da execução")
        st.caption("Somente tempos, contagens e tamanhos — nenhum dado clínico é registrado.")
        st.json(metrics)
        st.markdown(
            f"**Modelo LLM:** `{metrics.get('llm_model')}` · "
            f"**Whisper:** `{metrics.get('whisper_model')}` · "
            f"**Tentativas de reparo:** {metrics.get('repair_attempts')} · "
            f"**Itens a conferir:** {metrics.get('uncertain_count')}"
        )
        st.caption(f"Arquivo de métricas: `{settings.metrics_path}` (JSONL local, sem PHI).")

st.caption(
    "DentaNote é uma ferramenta de apoio: o profissional revisa e assume a evolução. "
    "Não faz diagnóstico nem sugere conduta. Dados 100% sintéticos nas demostrações."
)
