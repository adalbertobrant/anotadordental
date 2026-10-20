#!/usr/bin/env python3
"""Evaluate DentaNote over the synthetic corpus and (optionally) compare models.

Examples:

    uv run python scripts/evaluate.py                       # default model
    uv run python scripts/evaluate.py --models gemma4:e4b gemma3:4b
    uv run python scripts/evaluate.py --mock                # harness smoke test
    uv run python scripts/evaluate.py --out docs/results.md

``--mock`` uses the expected JSON as the "model" answer: it validates the
harness itself (and is what CI uses), never the model. Real runs talk only to
the local Ollama server — no external API is involved.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

from dentanote.config import Settings
from dentanote.evaluation import ModelReport, evaluate_case, report_markdown
from dentanote.extract import OllamaClient, OllamaReply
from dentanote.pipeline import run_from_text
from dentanote.schema import ClinicalNote

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = ROOT / "data" / "synthetic" / "transcripts"
EXPECTED_DIR = ROOT / "data" / "synthetic" / "expected"
DEFAULT_OUT = ROOT / "docs" / "results.md"


class EchoClient:
    """Mock client returning the expected extraction (harness validation only)."""

    def __init__(self, expected_json: str) -> None:
        self.expected_json = expected_json
        self.calls = 0

    def chat(self, messages: list[dict[str, str]]) -> OllamaReply:
        self.calls += 1
        return OllamaReply(
            text=self.expected_json,
            prompt_tokens=100,
            completion_tokens=100,
            model="mock:expected",
            latency_s=0.0,
        )


def load_corpus(limit: int | None = None) -> list[tuple[str, str, ClinicalNote]]:
    """Return ``(slug, transcript, expected_note)`` triples sorted by slug."""
    cases: list[tuple[str, str, ClinicalNote]] = []
    for transcript_path in sorted(TRANSCRIPTS_DIR.glob("*.txt")):
        expected_path = EXPECTED_DIR / f"{transcript_path.stem}.json"
        if not expected_path.exists():
            raise SystemExit(f"missing expected file for {transcript_path.name}: {expected_path}")
        note = ClinicalNote.model_validate(json.loads(expected_path.read_text(encoding="utf-8")))
        transcript = transcript_path.read_text(encoding="utf-8").strip()
        cases.append((transcript_path.stem, transcript, note))
        if limit and len(cases) >= limit:
            break
    if not cases:
        raise SystemExit(f"no transcripts found in {TRANSCRIPTS_DIR}")
    return cases


def evaluate_model(
    model: str,
    corpus: list[tuple[str, str, ClinicalNote]],
    *,
    mock: bool,
) -> ModelReport:
    settings = Settings(llm_model=model)
    cases = []
    for index, (slug, transcript, expected) in enumerate(corpus, start=1):
        client: OllamaClient | EchoClient
        client = (
            EchoClient(json.dumps(expected.model_dump(mode="json"), ensure_ascii=False))
            if mock
            else OllamaClient(settings)
        )
        started = time.perf_counter()
        result = run_from_text(transcript, settings, client=client, record=False)  # type: ignore[arg-type]
        case = evaluate_case(
            slug,
            result.note,
            expected,
            valid_first_try=result.metrics.valid_first_try,
            repair_attempts=result.metrics.repair_attempts,
            extraction_s=result.metrics.extraction_s,
            total_s=result.metrics.total_s,
            prompt_tokens=result.metrics.prompt_tokens,
            completion_tokens=result.metrics.completion_tokens,
            warnings=len(result.warnings),
        )
        cases.append(case)
        print(
            f"[{model}] {index}/{len(corpus)} {slug}: "
            f"first_try={'yes' if case.valid_first_try else 'NO'} "
            f"repairs={case.repair_attempts} "
            f"F1 teeth={case.scores['teeth_fdi'].f1:.2f} "
            f"procedures={case.scores['procedures'].f1:.2f} "
            f"medications={case.scores['medications'].f1:.2f} "
            f"fp={case.hallucinated_items} ({time.perf_counter() - started:.1f}s)",
            file=sys.stderr,
        )
    return ModelReport(model=model, cases=cases)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=None,
        help="Ollama models to evaluate (default: DENTANOTE_LLM_MODEL / gemma4:e4b).",
    )
    parser.add_argument("--limit", type=int, default=None, help="Evaluate only N transcripts.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use the expected JSON as the answer (validates the harness, not the model).",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Markdown output path.")
    parser.add_argument("--no-write", action="store_true", help="Print only, do not write files.")
    args = parser.parse_args()

    settings = Settings()
    models = args.models or [settings.llm_model]
    corpus = load_corpus(args.limit)

    print(
        f"Evaluating {len(corpus)} transcripts x {len(models)} model(s)"
        + (" [MOCK]" if args.mock else ""),
        file=sys.stderr,
    )
    reports = [evaluate_model(model, corpus, mock=args.mock) for model in models]
    memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

    markdown = report_markdown(reports, memory_mb=memory_mb)
    print(markdown)

    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"\nWrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
