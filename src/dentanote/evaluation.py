"""Corpus evaluation: precision/recall/F1, hallucination and uncertainty use.

The rules are deliberately simple and deterministic so the numbers in
``docs/results.md`` can be reproduced by anyone with the same models:

* item sets are compared as normalized strings (accents/case/punctuation
  stripped) for procedures, medications and findings; tooth numbers compare as
  FDI integers;
* ``precision < 1`` means **hallucination** (items extracted that the expected
  extraction does not contain);
* ``uncertain_items`` is scored as a *usage* metric: when the expected result
  flagged something as uncertain, the model must flag something too.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

from dentanote.schema import ClinicalNote

_ACCENT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

# Fields scored per case (tooth numbers, procedures and medications are the
# load-bearing ones for a dental note).
SCORED_FIELDS = ("teeth_fdi", "procedures", "medications")


def normalize_item(text: str) -> str:
    """Lowercase, strip accents/punctuation and collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _SPACE_RE.sub(" ", _ACCENT_RE.sub(" ", without_accents)).strip()


def _tokens(text: str) -> set[str]:
    return set(normalize_item(text).split())


def items_match(predicted: str, expected: str) -> bool:
    """Tolerant item comparison for free-text fields.

    Two items match when they are equal, when one contains the other
    ("profilaxia" vs "profilaxia com raspagem supragengival") or when they
    share most tokens (Jaccard >= 0.5). Tooth numbers only ever match exactly,
    because their token set has a single element.
    """
    left, right = _tokens(predicted), _tokens(expected)
    if not left or not right:
        return False
    if left == right or left <= right or right <= left:
        return True
    return len(left & right) / len(left | right) >= 0.5


def item_sets(note: ClinicalNote) -> dict[str, set[str]]:
    """Comparable item sets extracted from one note."""
    teeth = {str(tooth.fdi_number) for tooth in note.teeth}
    teeth |= {str(number) for procedure in note.procedures for number in procedure.tooth_fdi}
    return {
        "teeth_fdi": teeth,
        "procedures": {normalize_item(p.name) for p in note.procedures if p.name.strip()},
        "medications": {
            normalize_item(m.name) for m in note.medications_prescribed if m.name.strip()
        },
        "findings": {normalize_item(f) for f in note.findings if f.strip()},
        "guidance": {normalize_item(g) for g in note.guidance_given if g.strip()},
    }


@dataclass(frozen=True)
class FieldScore:
    """Precision/recall/F1 for one field of one case (macro-aggregated later)."""

    field: str
    tp: int
    fp: int
    fn: int

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) else 1.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) else 1.0

    @property
    def f1(self) -> float:
        if self.precision + self.recall == 0:
            return 0.0
        return 2 * self.precision * self.recall / (self.precision + self.recall)


def score_field(field_name: str, predicted: set[str], expected: set[str]) -> FieldScore:
    """One-to-one greedy matching between predicted and expected items."""
    remaining = sorted(expected, key=len)
    tp = 0
    for candidate in sorted(predicted, key=len, reverse=True):
        for index, target in enumerate(remaining):
            if items_match(candidate, target):
                remaining.pop(index)
                tp += 1
                break
    fp = len(predicted) - tp
    fn = len(expected) - tp
    return FieldScore(field=field_name, tp=tp, fp=fp, fn=fn)


@dataclass(frozen=True)
class CaseResult:
    """Evaluation of a single transcript."""

    slug: str
    scores: dict[str, FieldScore]
    valid_first_try: bool
    repair_attempts: int
    extraction_s: float
    total_s: float
    prompt_tokens: int
    completion_tokens: int
    uncertain_expected: int
    uncertain_predicted: int
    uncertain_hit: bool
    warnings: int
    extra_uncertain: list[str] = field(default_factory=list)

    @property
    def hallucinated_items(self) -> int:
        return sum(score.fp for score in self.scores.values())

    @property
    def missed_items(self) -> int:
        return sum(score.fn for score in self.scores.values())


def evaluate_case(
    slug: str,
    predicted: ClinicalNote,
    expected: ClinicalNote,
    *,
    valid_first_try: bool,
    repair_attempts: int,
    extraction_s: float,
    total_s: float,
    prompt_tokens: int,
    completion_tokens: int,
    warnings: int = 0,
) -> CaseResult:
    """Compare one prediction against its expected extraction."""
    predicted_sets = item_sets(predicted)
    expected_sets = item_sets(expected)
    scores = {
        name: score_field(name, predicted_sets[name], expected_sets[name]) for name in SCORED_FIELDS
    }

    expected_uncertain = len(expected.uncertain_items)
    predicted_uncertain = len(predicted.uncertain_items)
    hit = expected_uncertain == 0 or predicted_uncertain > 0

    expected_norm = {normalize_item(item) for item in expected.uncertain_items}
    extra = [
        item
        for item in predicted.uncertain_items
        if normalize_item(item) not in expected_norm and expected_uncertain == 0
    ]

    return CaseResult(
        slug=slug,
        scores=scores,
        valid_first_try=valid_first_try,
        repair_attempts=repair_attempts,
        extraction_s=extraction_s,
        total_s=total_s,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        uncertain_expected=expected_uncertain,
        uncertain_predicted=predicted_uncertain,
        uncertain_hit=hit,
        warnings=warnings,
        extra_uncertain=extra,
    )


@dataclass(frozen=True)
class ModelReport:
    """Aggregated results for one model over the corpus."""

    model: str
    cases: list[CaseResult]

    # --- quality -----------------------------------------------------------
    @property
    def valid_first_try_rate(self) -> float:
        return _rate([case.valid_first_try for case in self.cases])

    @property
    def mean_repairs(self) -> float:
        return statistics.fmean(case.repair_attempts for case in self.cases) if self.cases else 0.0

    @property
    def uncertain_usage_rate(self) -> float:
        """Cases where uncertainty was expected and actually flagged."""
        relevant = [case for case in self.cases if case.uncertain_expected > 0]
        if not relevant:
            return 1.0
        return _rate([case.uncertain_hit for case in relevant])

    @property
    def hallucination_rate(self) -> float:
        """Share of extracted items that do not appear in the expected result."""
        tp = sum(score.tp for case in self.cases for score in case.scores.values())
        fp = sum(score.fp for case in self.cases for score in case.scores.values())
        return fp / (tp + fp) if (tp + fp) else 0.0

    def macro(self, field_name: str, metric: str) -> float:
        values = [getattr(case.scores[field_name], metric) for case in self.cases]
        return statistics.fmean(values) if values else 0.0

    # --- performance -------------------------------------------------------
    @property
    def mean_extraction_s(self) -> float:
        return statistics.fmean(case.extraction_s for case in self.cases) if self.cases else 0.0

    @property
    def p95_extraction_s(self) -> float:
        return _p95([case.extraction_s for case in self.cases])

    @property
    def p95_total_s(self) -> float:
        return _p95([case.total_s for case in self.cases])

    @property
    def mean_tokens_per_s(self) -> float:
        rates = [
            case.completion_tokens / case.extraction_s
            for case in self.cases
            if case.extraction_s > 0
        ]
        return statistics.fmean(rates) if rates else 0.0

    @property
    def total_tokens(self) -> int:
        return sum(case.prompt_tokens + case.completion_tokens for case in self.cases)


def _rate(flags: list[bool]) -> float:
    return sum(1 for flag in flags if flag) / len(flags) if flags else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
    return ordered[index]


def report_markdown(reports: list[ModelReport], *, memory_mb: float | None = None) -> str:
    """Render the comparative Markdown table written to ``docs/results.md``."""
    lines = [
        "# Resultados da avaliação (DentaNote)",
        "",
        "Gerado por `scripts/evaluate.py` sobre as 12 transcrições sintéticas de "
        "`data/synthetic/transcripts`, comparando com `data/synthetic/expected/`.",
        "",
        "## Qualidade",
        "",
        "| Modelo | JSON válido 1ª tentativa | Precisão (F1) dentes FDI | "
        "F1 procedimentos | F1 medicamentos | Taxa de alucinação | "
        "Uso de `uncertain_items` | Reparos (média) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        lines.append(
            f"| `{report.model}` | {report.valid_first_try_rate:.0%} | "
            f"{report.macro('teeth_fdi', 'f1'):.2f} | "
            f"{report.macro('procedures', 'f1'):.2f} | "
            f"{report.macro('medications', 'f1'):.2f} | "
            f"{report.hallucination_rate:.1%} | "
            f"{report.uncertain_usage_rate:.0%} | "
            f"{report.mean_repairs:.2f} |"
        )

    lines += [
        "",
        "## Desempenho",
        "",
        "| Modelo | Latência média (extração) | p95 (extração) | p95 (total) | "
        "Tokens/s | Tokens totais |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for report in reports:
        lines.append(
            f"| `{report.model}` | {report.mean_extraction_s:.2f} s | "
            f"{report.p95_extraction_s:.2f} s | {report.p95_total_s:.2f} s | "
            f"{report.mean_tokens_per_s:.1f} | {report.total_tokens} |"
        )

    if memory_mb is not None:
        lines += [
            "",
            f"Memória máxima do processo (RSS): **{memory_mb:.0f} MB** (avaliação completa).",
        ]

    lines += [
        "",
        "### Como ler",
        "",
        "- **Taxa de alucinação** = itens extraídos que não existem no resultado "
        "esperado (1 - precisão). Quanto mais perto de 0%, melhor.",
        "- **Uso de `uncertain_items`** = casos em que o esperado marcava incerteza "
        "e o modelo também marcou (deveria ser 100%).",
        "- Os campos são comparados por conjuntos normalizados (acentos/caixa "
        "removidos); dentes, pela notação FDI.",
        "- Resultados com dados 100% sintéticos — nenhum paciente real foi usado.",
        "",
    ]
    return "\n".join(lines)
