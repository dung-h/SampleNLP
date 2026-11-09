"""Source-grounded end-to-end checks for the isolated experiment."""

from pathlib import Path

import pytest

from experiments.slide_pipeline.assistant import SlideAssistant
from experiments.slide_pipeline.knowledge import Fact, KnowledgeBase
from experiments.slide_pipeline.logic import Atom, Connective, LogicalForm, Variable
from experiments.slide_pipeline.procedure import execute, translate
from experiments.slide_pipeline.syntax import ParseError, Parser
from experiments.slide_pipeline.evaluation import (
    audit_faq,
    audit_sample_intents,
    evaluate,
)
from experiments.slide_pipeline.exporter import export
from experiments.slide_pipeline.generation import generate_sentences


@pytest.fixture
def bot():
    return SlideAssistant()


def test_cfg_has_actual_productions_and_derives_tree():
    parser = Parser()
    assert str(parser.grammar.start()) == "S"
    tree = parser.parse("Chương nào nói về CFG?")
    assert tree.label() == "S"
    assert tree[0].label() == "CHAPTER_BY_TOPIC"
    assert tree.leaves() == ["chương", "nào", "nói", "về", "cfg"]
    assert tree[0][0].label() == "CHAPTER_WH"
    assert tree[0][1].label() == "TOPIC_VERB"


@pytest.mark.parametrize(
    "sentence", ["", "Học gì?", "Chương nào nói về CFG???", "Cho tôi tất cả sách"]
)
def test_unrecognized_sentence_is_not_a_valid_parse(sentence):
    with pytest.raises(ParseError):
        Parser().parse(sentence)


def test_wh_logical_form_procedure_and_result(bot):
    result = bot.ask("Chương nào nói về CFG?")
    assert (
        result["logical_form"]
        == "WH ?chapter: (CHAPTER(?chapter) AND DISCUSSES(?chapter, CFG))"
    )
    assert (
        result["query_form"]
        == "RETRIEVE ?chapter WHERE (CHAPTER(?chapter) AND HAS_TOPIC(?chapter, CFG))"
    )
    assert result["retrieval"] == {
        "status": "FOUND",
        "values": ["CH03"],
        "sources": ["topics:CH03"],
    }


def test_boolean_found_is_grounded(bot):
    result = bot.ask("Chương 3 có CFG không?")
    assert result["logical_form"] == "YES_NO: DISCUSSES(CH03, CFG)"
    assert result["query_form"] == "TEST WHERE HAS_TOPIC(CH03, CFG)"
    assert result["retrieval"] == {
        "status": "FOUND",
        "values": [True],
        "sources": ["topics:CH03"],
    }


def test_missing_keyword_is_unknown_not_false(bot):
    result = bot.ask("Chương 4 có CFG không?")
    assert result["retrieval"] == {"status": "UNKNOWN", "values": [], "sources": []}
    assert "Chưa đủ dữ liệu" in result["answer"]


def test_unknown_chapter_is_not_false(bot):
    result = bot.ask("Chương 99 có CFG không?")
    assert result["retrieval"]["status"] == "UNKNOWN"


def test_explicit_negative_permission_fact_supports_false(bot):
    result = bot.ask("Có được chia sẻ bài làm giữa các nhóm không?")
    assert result["retrieval"] == {
        "status": "FOUND",
        "values": [False],
        "sources": ["regulations:ASSIGNMENT_SHARING"],
    }
    assert result["answer"].startswith("Không.")


def test_and_intersection_and_or_union_with_correct_sources(bot):
    both = bot.ask("Chương nào nói về CFG và PCFG?")
    either = bot.ask("Chương nào nói về CFG hoặc PCFG?")
    assert "AND" in both["logical_form"] and "OR" in either["logical_form"]
    assert both["retrieval"] == {
        "status": "FOUND",
        "values": ["CH03"],
        "sources": ["topics:CH03"],
    }
    assert either["retrieval"] == {
        "status": "FOUND",
        "values": ["CH03", "CH06"],
        "sources": ["topics:CH03", "topics:CH06"],
    }


def test_multiple_constraints_must_share_same_variable():
    x = Variable("x")
    form = LogicalForm("WH", x, Connective("AND", (Atom("A", (x,)), Atom("B", (x,)))))
    kb = type("KB", (), {"facts": [Fact("A", ("1",), "a"), Fact("B", ("2",), "b")]})()
    assert execute(translate(form), kb).status == "NOT_FOUND"


def test_each_quantifier_runs_from_sentence_to_procedural_query(bot):
    result = bot.ask("Mỗi chương nói về CFG học tuần nào?")
    assert "EACH ?chapter" in result["logical_form"]
    assert "DISCUSSES(?chapter, CFG)" in result["logical_form"]
    assert "ITERATE ?chapter ?week" in result["query_form"]
    assert "HAS_TOPIC(?chapter, CFG)" in result["query_form"]
    assert "SCHEDULED_IN(?chapter, ?week)" in result["query_form"]
    assert result["retrieval"]["values"] == ["CH03: WEEK_03"]
    assert set(result["retrieval"]["sources"]) == {"topics:CH03", "schedule:WEEK_03"}


def test_every_and_the_with_missing_and_ambiguous_data(bot):
    yes = bot.ask("Mọi chương nói về CFG đều học tuần 3 không?")
    assert yes["retrieval"]["values"] == [True]
    assert "CHECK_ALL" in yes["query_form"]
    missing = bot.ask("Mọi chương nói về CFG đều học tuần 4 không?")
    assert missing["retrieval"]["status"] == "UNKNOWN"
    unique = bot.ask("Chương duy nhất nói về CFG học tuần nào?")
    assert unique["retrieval"]["values"] == ["WEEK_03"]
    assert "FIND_THE" in unique["query_form"]
    ambiguous = bot.ask("Chương duy nhất nói về PCFG học tuần nào?")
    assert ambiguous["retrieval"]["status"] == "UNKNOWN"


def test_each_does_not_ignore_an_individual_with_missing_body():
    x, y = Variable("x"), Variable("y")
    form = LogicalForm("EACH", y, Atom("TAUGHT_IN", (x, y)), x, Atom("CHAPTER", (x,)))
    kb = type(
        "KB",
        (),
        {
            "facts": [
                Fact("CHAPTER", ("CH01",), "one"),
                Fact("CHAPTER", ("CH02",), "two"),
                Fact("SCHEDULED_IN", ("CH01", "WEEK_01"), "schedule"),
            ]
        },
    )()
    assert execute(translate(form), kb).status == "UNKNOWN"


def test_week_reference_resolves_using_schedule_fact(bot):
    first = bot.ask("Tuần 3 học gì?")
    assert first["retrieval"]["status"] == "FOUND"
    assert first["retrieval"]["sources"] == ["schedule:WEEK_03"]
    assert first["context"]["chapter"] == "CH03"
    second = bot.ask("Chương này nói về gì?")
    assert "REF(chapter)" in second["logical_form"]
    assert "CHAPTER_SUMMARY(CH03, ?content)" in second["resolved_logical_form"]
    assert "context-free grammar" in second["retrieval"]["values"][0]
    assert second["retrieval"]["sources"] == ["topics:CH03"]


def test_missing_context_does_not_guess(bot):
    result = bot.ask("Chương này nói về gì?")
    assert "REF(chapter)" in result["logical_form"]
    assert "retrieval" not in result
    assert "Chưa xác định" in result["answer"]


def test_reset_discards_previous_context(bot):
    bot.ask("Tuần 3 học gì?")
    bot.reset()
    assert "Chưa xác định" in bot.ask("Chương này nói về gì?")["answer"]


def test_missing_week_clears_old_focus(bot):
    bot.ask("Tuần 3 học gì?")
    assert bot.ask("Tuần 99 học gì?")["context"]["chapter"] is None
    assert "Chưa xác định" in bot.ask("Chương này nói về gì?")["answer"]


def test_two_candidate_chapters_do_not_select_one(bot):
    bot.kb.facts.append(Fact("SCHEDULED_IN", ("CH04", "WEEK_03"), "schedule:WEEK_03"))
    assert bot.ask("Tuần 3 học gì?")["context"]["chapter"] is None


def test_loader_records_source_for_raw_and_annotated_facts():
    kb = KnowledgeBase()
    assert Fact("SCHEDULED_IN", ("CH03", "WEEK_03"), "schedule:WEEK_03") in kb.facts
    assert Fact("HAS_KEYWORD", ("CH06", "PCFG"), "topics:CH06") in kb.facts
    assert all(f.source for f in kb.facts)
    assert (
        Fact(
            "RESOURCE_TOPIC",
            ("RES02", "STATISTICAL_NLP"),
            "annotation:resource_topics:RES02",
        )
        in kb.facts
    )


def test_loader_rejects_missing_sources(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        KnowledgeBase(tmp_path)


@pytest.mark.parametrize(
    "question,intent,expected",
    [
        ("Môn NLP có bao nhiêu tín chỉ?", "GET_COURSE_INFO", "3"),
        ("CO3085 có mấy tín chỉ?", "GET_COURSE_INFO", "3"),
        ("Môn NLP có bao nhiêu ECTS?", "GET_COURSE_INFO", "6"),
        (
            "Môn NLP thuộc khoa nào?",
            "GET_COURSE_INFO",
            "Khoa Khoa học và Kỹ thuật Máy tính",
        ),
        ("Chương 4 học vào tuần nào?", "GET_SCHEDULE", "WEEK_04"),
        ("PCFG được học ở đâu?", "GET_TOPIC", "CH06"),
        ("Chương nào nói về semantic grammar?", "GET_TOPIC", "CH10"),
        ("Chương nào học về Features và Augmented Grammar?", "GET_TOPIC", "CH04"),
        (
            "L.O.2.5 là gì?",
            "GET_LO",
            "Kiến thức xác suất để giải quyết nhập nhằng từ ở mức câu.",
        ),
        ("Midterm bao nhiêu phút?", "GET_COURSE_INFO", "60 minutes"),
        ("Final kéo dài bao lâu?", "GET_COURSE_INFO", "90 minutes"),
        ("Phần I của bài tập lớn là gì?", "GET_ASSIGNMENT", "Grammar and Parser"),
        ("Bài tập lớn nhóm mấy người?", "GET_ASSIGNMENT", "3-4 students"),
        ("Có được dùng thư viện ngoài không?", "GET_RULE", True),
    ],
)
def test_required_domains_and_source_grounded_answers(bot, question, intent, expected):
    result = bot.ask(question)
    assert result["intent_entity"]["intent"] == intent
    assert result["retrieval"]["status"] == "FOUND"
    assert expected in result["retrieval"]["values"]
    assert result["retrieval"]["sources"]


@pytest.mark.parametrize(
    "question,intent",
    [
        ("Deadline của bài tập lớn là khi nào?", "GET_DEADLINE"),
        ("Ai dạy môn NLP?", "GET_INSTRUCTOR"),
        ("Tài liệu nào nói về parsing?", "GET_RESOURCE"),
        ("Hạn nộp phần I là khi nào?", "GET_DEADLINE"),
    ],
)
def test_valid_queries_with_missing_data_are_not_fabricated(bot, question, intent):
    result = bot.ask(question)
    assert result["intent_entity"]["intent"] == intent
    assert result["retrieval"] == {"status": "NOT_FOUND", "values": [], "sources": []}


def test_resource_topic_uses_explicit_team_annotation_with_provenance(bot):
    result = bot.ask("Tài liệu tham khảo về statistical NLP là gì?")
    assert result["intent_entity"]["intent"] == "GET_RESOURCE"
    assert result["retrieval"]["status"] == "FOUND"
    assert "annotation:resource_topics:RES02" in result["retrieval"]["sources"]
    assert "resources:RES02" in result["retrieval"]["sources"]


def test_related_content_distinguished_from_lo_description(bot):
    result = bot.ask("L.O.4.2 liên quan đến nội dung nào?")
    assert result["intent_entity"] == {
        "intent": "GET_LO",
        "entities": {"learning_outcome": ["LO4.2"]},
    }
    assert result["retrieval"] == {
        "status": "FOUND",
        "values": ["CH12"],
        "sources": [
            "annotation:slide_relations:LO4.2_CH12",
            "course_info:CO3085",
            "topics:CH12",
        ],
    }


def test_context_pronoun_and_ellipsis(bot):
    bot.ask("Chương 11 có hỏi đáp không?")
    next_turn = bot.ask("Còn chương sau?")
    assert "DISCUSSES(CH12, QUESTION ANSWERING)" in next_turn["resolved_logical_form"]
    assert next_turn["retrieval"]["status"] == "UNKNOWN"


def test_chapter_followup_can_use_topic_mentioned_in_subtopics(bot):
    first = bot.ask("Chương 4 nói về gì?")
    assert first["context"]["chapter"] == "CH04"
    second = bot.ask("Nó có liên quan đến parsing không?")
    assert second["retrieval"] == {
        "status": "FOUND",
        "values": [True],
        "sources": ["topics:CH04"],
    }


def test_question_answering_alias_is_grounded_in_chapter_eleven(bot):
    result = bot.ask("Chương nào học về question answering?")
    assert "CH11" in result["retrieval"]["values"]
    assert "topics:CH11" in result["retrieval"]["sources"]


@pytest.mark.parametrize(
    "question,chapter",
    [
        ("Chương nào học về knowledge representation?", "CH11"),
        ("Chương nào học về local discourse context?", "CH12"),
    ],
)
def test_additional_faq_topics_use_grounded_aliases(bot, question, chapter):
    assert chapter in bot.ask(question)["retrieval"]["values"]


def test_conditional_llm_regulation_does_not_imply_unconditional_permission(bot):
    result = bot.ask("Bài tập lớn có thể sử dụng LLM hoặc RAG không?")
    assert result["intent_entity"]["intent"] == "GET_RULE"
    assert result["retrieval"]["status"] == "UNKNOWN"
    assert result["supporting_evidence"][0]["source"] == "regulations:LLM_RAG"
    assert "mở rộng" in result["answer"]


def test_not_found_policy_is_read_from_regulation(bot):
    result = bot.ask("Nếu hệ thống không tìm thấy câu trả lời thì phải làm gì?")
    assert result["retrieval"]["status"] == "FOUND"
    assert result["retrieval"]["sources"] == ["regulations:OUT_OF_SCOPE"]


def test_example_week_five_references_actual_schedule_chapter_not_week_number(bot):
    first = bot.ask("Tuần 5 học những gì?")
    assert first["context"]["chapter"] == "CH04"
    second = bot.ask("Tài liệu của phần này ở đâu?")
    assert second["intent_entity"]["entities"]["chapter"] == ["CH04"]
    assert second["retrieval"]["status"] == "NOT_FOUND"


def test_assignment_part_reference_is_grounded_in_part_title(bot):
    first = bot.ask("Bài tập lớn có phần parser không?")
    assert first["context"]["assignment_part"] == "BTL_PART_1"
    second = bot.ask("Phần này cần xuất file gì?")
    assert "PART_OUTPUT(BTL_PART_1, ?output)" in second["query_form"]
    assert "output/grammar.txt" in second["retrieval"]["values"]


def test_new_out_of_scope_query_cannot_reuse_old_pronoun_context(bot):
    bot.ask("Chương 4 nói về gì?")
    bot.ask("Hôm nay trời có mưa không?")
    assert (
        bot.ask("Nó có liên quan đến parsing không?")["intent_entity"]["intent"]
        == "UNKNOWN"
    )


def test_generator_uses_cfg_and_respects_limit():
    sentences = generate_sentences(120)
    assert len(sentences) == 120
    assert len(set(sentences)) == len(sentences)
    parser = Parser()
    assert all(parser.parse(sentence).label() == "S" for sentence in sentences)
    with pytest.raises(ValueError):
        generate_sentences(10001)


def test_evaluation_reports_observed_checks_and_unknowns():
    result = evaluate()
    assert result["total"] == 46
    assert result["passed"] + result["failed"] == result["total"]
    assert result["pass_rate"] == result["passed"] / result["total"]
    assert any(item["id"] == "E24" and item["passed"] for item in result["cases"])
    audit = audit_sample_intents()
    assert audit["total"] == 28
    assert audit["passed"] + audit["failed"] == 28
    assert audit_faq()["total"] == 15


def test_export_artifacts_are_isolated_and_have_expected_formats(tmp_path):
    result = export(tmp_path, sample_limit=30)
    assert result["samples"] == 30
    for name in (
        "grammar.txt",
        "samples.txt",
        "parse-results.txt",
        "semantic.txt",
        "intent-entity.txt",
        "query.txt",
        "answer.txt",
        "retrieval.txt",
        "dialogue.txt",
        "evaluation.txt",
        "evaluation-results.json",
        "sample-intent-audit.json",
        "faq-audit.json",
    ):
        assert (tmp_path / name).is_file()
    assert (
        len((tmp_path / "samples.txt").read_text(encoding="utf-8").splitlines()) == 30
    )
    assert "()" in (tmp_path / "parse-results.txt").read_text(encoding="utf-8")
    assert "resolved_logical_form" in (tmp_path / "semantic.txt").read_text(
        encoding="utf-8"
    )
    assert "supporting_evidence" in (tmp_path / "retrieval.txt").read_text(
        encoding="utf-8"
    )
    assert "không suy rộng" in (tmp_path / "evaluation.txt").read_text(encoding="utf-8")
