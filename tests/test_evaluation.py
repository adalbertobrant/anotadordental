"""Evaluation metric tests (no model required)."""

from __future__ import annotations

from dentanote.evaluation import (
    ModelReport,
    evaluate_case,
    items_match,
    normalize_item,
    report_markdown,
    score_field,
)
from dentanote.schema import ClinicalNote


def note(**kwargs: object) -> ClinicalNote:
    return ClinicalNote.model_validate(kwargs)


def test_normalize_item_strips_accents_case_and_punctuation() -> None:
    assert normalize_item("Restauração em Resina!") == "restauracao em resina"
    assert normalize_item("  Ibuprofeno,  600mg ") == "ibuprofeno 600mg"


def test_score_field_perfect_match() -> None:
    score = score_field("teeth_fdi", {"36", "46"}, {"36", "46"})
    assert (score.precision, score.recall, score.f1) == (1.0, 1.0, 1.0)


def test_items_match_allows_paraphrase_but_not_hallucination() -> None:
    assert items_match("restauração", "restauração em resina")  # containment
    assert items_match("Restauração classe II em resina", "restauração em resina")
    assert items_match("alívio", "alívio de dor e curativo")
    assert items_match("36", "36")
    assert not items_match("36", "37")  # tooth numbers only match exactly
    assert not items_match("exodontia simples", "restauração em resina")
    assert not items_match("ibuprofeno", "amoxicilina")
    assert not items_match("", "")


def test_score_field_matching_is_one_to_one() -> None:
    """Two predicted items cannot both claim the same expected item."""
    score = score_field(
        "procedures",
        {"profilaxia", "raspagem supragengival"},
        {"profilaxia com raspagem supragengival"},
    )
    assert score.tp == 1
    assert score.fp == 1
    assert score.fn == 0


def test_score_field_hallucination_lowers_precision() -> None:
    score = score_field("teeth_fdi", {"36", "99"}, {"36"})
    assert score.precision == 0.5
    assert score.recall == 1.0
    assert score.f1 == 2 / 3


def test_score_field_miss_lowers_recall() -> None:
    score = score_field("procedures", {"restauracao"}, {"restauracao", "exodontia"})
    assert score.precision == 1.0
    assert score.recall == 0.5


def test_score_field_both_empty_is_perfect_abstention() -> None:
    score = score_field("medications", set(), set())
    assert (score.precision, score.recall, score.f1) == (1.0, 1.0, 1.0)


def test_evaluate_case_hallucination_and_uncertain_usage() -> None:
    predicted = note(
        procedures=[{"name": "restauração em resina", "tooth_fdi": [36]}],
        medications_prescribed=[{"name": "amoxicilina"}],  # not in expected -> hallucination
        uncertain_items=["algo estranho"],
    )
    expected = note(
        procedures=[{"name": "restauração em resina", "tooth_fdi": [36]}],
        uncertain_items=["trecho não entendido"],
    )
    case = evaluate_case(
        "caso",
        predicted,
        expected,
        valid_first_try=True,
        repair_attempts=0,
        extraction_s=1.0,
        total_s=1.2,
        prompt_tokens=10,
        completion_tokens=5,
    )
    assert case.scores["procedures"].f1 == 1.0
    assert case.scores["medications"].fp == 1
    assert case.hallucinated_items == 1
    assert case.uncertain_hit is True
    assert case.extra_uncertain == []  # expected had uncertain items too


def test_evaluate_case_flags_missing_uncertain() -> None:
    predicted = note(findings=["x"])
    expected = note(uncertain_items=["não entendi"])
    case = evaluate_case(
        "caso",
        predicted,
        expected,
        valid_first_try=False,
        repair_attempts=2,
        extraction_s=1.0,
        total_s=1.0,
        prompt_tokens=1,
        completion_tokens=1,
    )
    assert case.uncertain_hit is False
    assert case.valid_first_try is False


def test_teeth_set_merges_procedure_teeth() -> None:
    predicted = note(procedures=[{"name": "exodontia", "tooth_fdi": [18]}])
    expected = note(teeth=[{"fdi_number": 18, "surfaces": []}])
    case = evaluate_case(
        "caso",
        predicted,
        expected,
        valid_first_try=True,
        repair_attempts=0,
        extraction_s=1.0,
        total_s=1.0,
        prompt_tokens=1,
        completion_tokens=1,
    )
    assert case.scores["teeth_fdi"].f1 == 1.0


def _perfect_case(slug: str):
    expected = note(findings=["cárie"], teeth=[{"fdi_number": 36, "surfaces": []}])
    return evaluate_case(
        slug,
        expected,
        expected,
        valid_first_try=True,
        repair_attempts=0,
        extraction_s=2.0,
        total_s=2.5,
        prompt_tokens=1000,
        completion_tokens=200,
    )


def test_model_report_aggregations() -> None:
    report = ModelReport(model="fake:model", cases=[_perfect_case("a"), _perfect_case("b")])
    assert report.valid_first_try_rate == 1.0
    assert report.hallucination_rate == 0.0
    assert report.uncertain_usage_rate == 1.0  # nothing expected to be uncertain
    assert report.macro("teeth_fdi", "f1") == 1.0
    assert report.mean_extraction_s == 2.0
    assert report.p95_extraction_s == 2.0
    assert report.mean_tokens_per_s == 100.0
    assert report.total_tokens == 2400


def test_model_report_reports_hallucination_rate() -> None:
    predicted = note(procedures=[{"name": "invented procedure", "tooth_fdi": [46]}])
    expected = note(procedures=[{"name": "exodontia", "tooth_fdi": [46]}])
    case = evaluate_case(
        "x",
        predicted,
        expected,
        valid_first_try=False,
        repair_attempts=1,
        extraction_s=3.0,
        total_s=3.5,
        prompt_tokens=10,
        completion_tokens=10,
        warnings=1,
    )
    report = ModelReport(model="fake", cases=[case])
    assert report.hallucination_rate == 0.5  # one TP (tooth) + one FP (name)


def test_report_markdown_contains_tables_and_models() -> None:
    report = ModelReport(model="gemma4:e4b", cases=[_perfect_case("a")])
    markdown = report_markdown([report], memory_mb=512.0)
    assert "| `gemma4:e4b` |" in markdown
    assert "100%" in markdown
    assert "512 MB" in markdown
    assert "Taxa de alucinação" in markdown
