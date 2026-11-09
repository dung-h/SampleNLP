"""Regression tests for issues discovered during the slide-pipeline audit."""

from experiments.slide_pipeline.assistant import SlideAssistant
from experiments.slide_pipeline.knowledge import KnowledgeBase
from experiments.slide_pipeline.evaluation import evaluate
from pathlib import Path


def test_trace_does_not_invent_a_constituent():
    result = SlideAssistant().ask("CFG được học ở đâu?")
    assert "(CHAPTER_WH " not in result["tree"]
    assert all(
        step["constituent"] != "CHAPTER_WH" for step in result["semantic_composition"]
    )


def test_count_is_represented_and_answered_as_count():
    result = SlideAssistant().ask("Môn NLP có mấy phần?")
    assert result["logical_form"].startswith("COUNT ")
    assert result["query_form"].startswith("COUNT ")
    assert result["retrieval"]["values"] == ["3"]
    assert "3 phần" in result["answer"]


def test_optional_requirements_do_not_become_mandatory():
    kb = KnowledgeBase()
    assert any(
        f.predicate == "PART_OPTIONAL" and f.args[0] == "BTL_PART_3" for f in kb.facts
    )
    assert not any(
        f.predicate == "ASSIGNMENT_REQUIREMENT" and f.source == "assignments:BTL_PART_3"
        for f in kb.facts
    )
    answer = SlideAssistant(kb).ask("Bài tập lớn có những yêu cầu gì?")
    assert "lưu discourse entities đơn giản" not in answer["retrieval"]["values"]
    optional = SlideAssistant(kb).ask("Phần III của bài tập lớn yêu cầu gì?")
    assert optional["retrieval"]["status"] == "FOUND"
    assert all(
        value.startswith("Tùy chọn/mở rộng:")
        for value in optional["retrieval"]["values"]
    )


def test_unknown_assignment_inventory_is_not_replaced_by_requirements():
    result = SlideAssistant().ask("Tôi cần hoàn thành những bài tập nào?")
    assert result["intent_entity"]["intent"] == "GET_ASSIGNMENT"
    assert result["retrieval"]["status"] == "NOT_FOUND"


def test_unique_retrieved_chapter_updates_context_but_multiple_clear_it():
    bot = SlideAssistant()
    assert bot.ask("CFG được học ở đâu?")["context"]["chapter"] == "CH03"
    assert bot.ask("Chương này nói về gì?")["retrieval"]["status"] == "FOUND"
    many = bot.ask("PCFG được học ở đâu?")
    assert many["context"]["chapter"] is None
    assert "error" in bot.ask("Chương này nói về gì?")


def test_unknown_with_partial_sources_is_not_misgraded():
    cases = evaluate(Path(__file__).resolve().parents[1] / "audit_cases.json")["cases"]
    case = next(item for item in cases if item["id"] == "A12")
    assert case["passed"]
    assert case["actual"]["retrieval"]["status"] == "UNKNOWN"
    assert case["actual"]["retrieval"]["sources"]
