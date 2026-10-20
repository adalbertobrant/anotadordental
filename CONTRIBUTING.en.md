# Contributing to DentaNote

> 🇧🇷 [Versão em português](CONTRIBUTING.md).

Thanks for wanting to contribute! The project is small on purpose and invites
contributions of three kinds: **other dental specialties** (more synthetic
scenarios), **other languages** (prompt, transcription and rendering in
ES/EN), and **engineering improvements** (performance, TTS, accessibility).

## Setup

```bash
git clone <repo>
cd anotadordental
uv sync --extra dev          # Python 3.11+; deps pinned in pyproject
ollama pull gemma4:e4b       # local model (once)
uv run dentanote doctor      # diagnoses the environment
```

No `uv`? `python -m venv .venv && pip install -e ".[dev]"` works too.

## Before opening the PR

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src scripts
uv run pytest -q -m "not slow"   # offline: sockets blocked, no real model needed
```

CI (GitHub Actions) runs exactly this on Python 3.11 and 3.12. Optionally,
locally with Ollama running: `uv run pytest -q -m slow`.

## Non-negotiable rules

1. **No real patient data** in code, tests, examples, screenshots or commits.
   See [SECURITY.en.md](SECURITY.en.md).
2. **No network calls at runtime** beyond `localhost:11434` (Ollama). If your
   feature needs the internet, it ships disabled by default and documented.
3. **Output is always a draft**: no "diagnosis" or inference-filled text —
   a gap becomes `null`/empty list/`uncertain_items`.
4. **No PHI in logs/metrics**: timings, counts and sizes only (there is already
   an automated test guaranteeing this — don't break the guard).

## Style

- [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- Code and comments in **English**; UI texts, README and clinical examples in
  **Brazilian Portuguese**.
- `ruff` formats/lints, `mypy` type-checks — no new suppressions without
  justification.
- Every PR ships a test for the new or changed behavior.

## Good starter ideas

- Synthetic transcripts from other specialties (implantology, periodontology,
  orthodontics) with the matching `expected/` — `scripts/evaluate.py` already
  measures the impact.
- Extra TTS voices/languages in `scripts/make_synthetic_audio.py`.
- Interface accessibility (contrast, keyboard navigation, screen readers).
- Following `docs/post_draft.md` and the README roadmap.
