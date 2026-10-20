# Instructions for GitHub Copilot

DentaNote is a **100% local pipeline for dental clinical notes**: audio (or
text) goes in, a **revisable draft** comes out. Whisper transcribes, Gemma via
local Ollama extracts structured JSON, a deterministic template renders the
note. Use these rules when generating, completing or reviewing code in this
repository.

## Non-negotiable rules

1. **Never real patient data.** No real names, records, audio or clinical data
   in code, tests, fixtures, docs, screenshots or commits. Synthetic data
   lives in `data/synthetic/` and its fictional patients are named
   `Paciente Exemplo NN` / `Sample Patient NN`.
2. **No network calls at runtime** beyond `http://localhost:11434` (Ollama).
   Tests must pass with sockets blocked (`pytest-socket`); anything that needs
   the internet ships disabled by default and documented.
3. **Output is always a draft.** Never infer or generate diagnoses. Missing or
   ambiguous information becomes `null`, an empty list, or an entry in
   `uncertain_items` — it is never guessed.
4. **No PHI in logs or metrics.** `metrics.jsonl` (ADR-006) records timings,
   token counts and sizes only; a guard test enforces this — don't weaken it.

## Architecture decisions to respect (ADRs in `docs/AGILE.md`)

- **ADR-001**: structured output uses Ollama's `format` (JSON Schema) with
  `think=false`, and Pydantic validation on the client is mandatory — the
  schema alone is not trusted.
- **ADR-002**: the final rendering step is a deterministic template in
  `src/dentanote/render.py`. **Never replace it with an LLM call.**
- **ADR-003**: invalid or ambiguous FDI tooth numbers are discarded into
  `uncertain_items` (`src/dentanote/schema.py` sanitizers), never "corrected".
  Valid FDI ranges: 11–48 (permanent), 51–85 (deciduous). Surfaces are
  uppercase: `M D O V L P I`.
- **ADR-004**: validation repair loop is capped at 2 attempts, then a partial
  result with a clear warning — no raw exceptions surfaced to the user.
- **ADR-005**: default model is `gemma4:e4b` (compare alternatives via
  `scripts/evaluate.py`).

## Languages

- **Code, comments, docstrings, commit messages: English.**
- **UI strings, clinical texts and `README.md`: Brazilian Portuguese** (the
  app has a PT/EN toggle; keep both entries of the `STRINGS` table in
  `src/dentanote/app.py` in sync when you add a key).
- Docs are bilingual: a PT-BR original with an English sibling (`*.en.md`)
  linked from each other.

## Workflow

- [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Dependencies are **pinned with `==`** in `pyproject.toml` (Python 3.11+,
  managed with `uv`). If a transitive dependency needs a forced version, use
  `[tool.uv] override-dependencies` with a comment explaining why.
- Run before every commit (CI runs the same gate on 3.11 and 3.12):

  ```bash
  uv run ruff format .
  uv run ruff check .
  uv run mypy src scripts
  uv run pytest -q -m "not slow"
  ```

- Every behavior change ships a test. Tests requiring a live Ollama/Whisper
  are marked `@pytest.mark.slow`.
- When reviewing: flag violations of the four rules above before style issues,
  and never suggest adding an external service, telemetry, or an LLM call in
  the rendering path.
