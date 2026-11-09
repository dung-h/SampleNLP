"""Behavioral examples for syntax, composition, grounding and uncertainty."""

import pytest
from nltk import CFG, ChartParser

from experiments.slide_pipeline.assistant import SlideAssistant
from experiments.slide_pipeline.logic import (
    Atom,
    Connective,
    Variable,
    compose_topic_expression,
)
from experiments.slide_pipeline.syntax import ParseError, Parser


@pytest.mark.parametrize(("conjunction", "operator"), [("và", "AND"), ("hoặc", "OR")])
def test_topic_constituent_composes_and_can_bind_different_subjects(
    conjunction, operator
):
    tree = Parser().parse(f"Chương nào nói về CFG {conjunction} PCFG?")
    node = next(tree.subtrees(lambda t: t.label() == "TOPIC_EXPR"))
    meaning = compose_topic_expression(node)
    for subject in (Variable("chapter"), "CH03"):
        assert meaning.apply(subject) == Connective(
            operator,
            (Atom("DISCUSSES", (subject, "CFG")), Atom("DISCUSSES", (subject, "PCFG"))),
        )


def test_tree_lf_grounding_and_evidence_are_distinct():
    result = SlideAssistant().ask("Chương nào nói về CFG và PCFG?")
    assert "TOPIC_EXPR" in result["tree"]
    assert "DISCUSSES(?chapter, CFG)" in result["logical_form"]
    assert "DISCUSSES(?chapter, PCFG)" in result["logical_form"]
    assert "HAS_TOPIC(?chapter, CFG)" in result["query_form"]
    assert "DISCUSSES" not in result["query_form"]
    assert result["retrieval"] == {
        "status": "FOUND",
        "values": ["CH03"],
        "sources": ["topics:CH03"],
    }
    assert any(
        step["constituent"] == "TOPIC_EXPR" for step in result["semantic_composition"]
    )
    assert [step["constituent"] for step in result["semantic_composition"]] == [
        "CHAPTER_WH",
        "TOPIC_VERB",
        "TOPIC",
        "TOPIC",
        "TOPIC_EXPR",
        "CHAPTER_BY_TOPIC",
    ]


def test_topic_constituent_is_reused_in_week_query():
    result = SlideAssistant().ask("CFG học tuần nào?")
    assert "DISCUSSES(?chapter, CFG)" in result["logical_form"]
    assert "TAUGHT_IN(?chapter, ?week)" in result["logical_form"]
    assert "HAS_TOPIC(?chapter, CFG)" in result["query_form"]
    assert "SCHEDULED_IN(?chapter, ?week)" in result["query_form"]
    assert result["retrieval"]["values"] == ["WEEK_03"]
    assert set(result["retrieval"]["sources"]) == {"topics:CH03", "schedule:WEEK_03"}


def test_definite_reference_reports_absence_and_ambiguity_separately():
    bot = SlideAssistant()
    # Use an empty KB to isolate absence regardless of raw-data updates.
    bot.kb.facts = []
    empty = bot.ask("Chương duy nhất nói về CFG học tuần nào?")
    assert empty["retrieval"]["status"] == "UNKNOWN"
    assert "không tìm thấy" in empty["answer"].lower()
    ambiguous = SlideAssistant().ask("Chương duy nhất nói về PCFG học tuần nào?")
    assert ambiguous["retrieval"]["status"] == "UNKNOWN"
    assert "nhiều chương" in ambiguous["answer"].lower()


def test_definite_reference_with_known_chapter_but_no_week():
    bot = SlideAssistant()
    bot.kb.facts = [fact for fact in bot.kb.facts if fact.predicate != "SCHEDULED_IN"]
    result = bot.ask("Chương duy nhất nói về CFG học tuần nào?")
    assert result["retrieval"]["status"] == "UNKNOWN"
    assert "chưa có dữ liệu tuần" in result["answer"].lower()


def test_ambiguous_syntax_is_not_silently_selected():
    parser = Parser()
    parser.parser = ChartParser(CFG.fromstring("S -> A | B\nA -> 'cfg'\nB -> 'cfg'"))
    with pytest.raises(ParseError, match="nhiều cách phân tích"):
        parser.parse("CFG")
