#!/usr/bin/env python3
"""Evaluate DentaNote over the synthetic corpus and (optionally) compare models.

Examples:

    uv run python scripts/evaluate.py                       # default model
    uv run python scripts/evaluate.py --models gemma4:e4b --models gemma3:4b
    uv run python scripts/evaluate.py --mock                # harness smoke test
    uv run python scripts/evaluate.py --out docs/results.md

``--mock`` uses the expected JSON as the "model" answer: it validates the
harness itself (and is what CI uses), never the model. Real runs talk only to
the local Ollama server — no external API is involved.

The same logic ships as the ``dentanote eval`` command; this script exists so
the evaluation can be run without installing the console entry point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dentanote.config import Settings
from dentanote.evaluation import report_markdown, run_evaluation

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "docs" / "results.md"


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
    print(
        f"Evaluating {len(models)} model(s) over the synthetic corpus"
        + (" [MOCK]" if args.mock else ""),
        file=sys.stderr,
    )
    reports, memory_mb = run_evaluation(models, limit=args.limit, mock=args.mock)
    markdown = report_markdown(reports, memory_mb=memory_mb)
    print(markdown)

    if not args.no_write:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown, encoding="utf-8")
        print(f"\nWrote {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
