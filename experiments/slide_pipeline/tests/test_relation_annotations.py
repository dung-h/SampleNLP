"""Checks for evidence-backed, experiment-only knowledge relations."""

import pytest

from experiments.slide_pipeline.assistant import SlideAssistant
from experiments.slide_pipeline.knowledge import KnowledgeBase


def test_cfg_reference_has_explicit_team_annotation_and_book_source():
    result = SlideAssistant().ask("Tài liệu nào nói về CFG?")
    assert result["retrieval"]["status"] == "FOUND"
    assert result["retrieval"]["values"] == ["Natural Language Processing with Python"]
    assert set(result["retrieval"]["sources"]) == {
        "annotation:slide_relations:RES05_CFG",
        "resources:RES05",
    }
    assert "chú giải" in result["answer"]
    assert "chưa khẳng định đầy đủ" in result["answer"]


def test_chapter_reference_is_inferred_via_shared_topic_not_assigned_reading():
    result = SlideAssistant().ask("Tài liệu của chương 3 là gì?")
    assert result["retrieval"]["values"] == ["Natural Language Processing with Python"]
    assert set(result["retrieval"]["sources"]) == {
        "annotation:slide_relations:RES05_CFG",
        "resources:RES05",
        "topics:CH03",
    }
    assert "liên quan theo chủ đề" in result["answer"]
    assert "chỉ định" in result["answer"]


def test_week_context_finds_related_resources_without_fabricating_direct_assignment():
    bot = SlideAssistant()
    bot.ask("Tuần 3 học gì?")
    result = bot.ask("Tài liệu của chương này là gì?")
    assert result["intent_entity"]["entities"]["chapter"] == ["CH03"]
    assert result["retrieval"]["values"] == ["Natural Language Processing with Python"]
    assert "liên quan theo chủ đề" in result["answer"]
    assert not any(f.predicate == "CHAPTER_RESOURCE" for f in bot.kb.facts)


def test_lo_chapter_mapping_is_team_inference_with_both_raw_sources():
    result = SlideAssistant().ask("L.O.4.2 liên quan đến nội dung nào?")
    assert result["retrieval"]["values"] == ["CH12"]
    assert set(result["retrieval"]["sources"]) == {
        "annotation:slide_relations:LO4.2_CH12",
        "course_info:CO3085",
        "topics:CH12",
    }
    assert "đối chiếu" in result["answer"]


def test_unknown_relation_still_returns_not_found():
    assert (
        SlideAssistant().ask("Tài liệu của chương 4 là gì?")["retrieval"]["status"]
        == "NOT_FOUND"
    )
    assert (
        SlideAssistant().ask("L.O.2.5 liên quan đến nội dung nào?")["retrieval"][
            "status"
        ]
        == "NOT_FOUND"
    )


def test_custom_data_dir_does_not_silently_import_experiment_annotations(tmp_path):
    import shutil
    from pathlib import Path

    raw = Path(__file__).resolve().parents[3] / "data" / "raw"
    shutil.copytree(raw, tmp_path / "raw")
    kb = KnowledgeBase(tmp_path / "raw")
    assert not any(f.source.startswith("annotation:slide_relations:") for f in kb.facts)


def test_invalid_annotation_rejects_unknown_entity(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text(
        "version: 1\nlo_chapters:\n  - id: bad\n    lo: LO4.2\n    chapter: CH99\n    evidence:\n      explanation: test\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="CH99"):
        KnowledgeBase(relation_path=path)
