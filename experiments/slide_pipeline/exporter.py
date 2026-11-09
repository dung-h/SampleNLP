"""Export assignment artifacts exclusively to the independent experiment."""

import json
from pathlib import Path

from .assistant import SlideAssistant
from .evaluation import audit_faq, audit_sample_intents, evaluate
from .generation import generate_sentences


ROOT = Path(__file__).parent
DEFAULT_INPUT = ROOT / "input" / "sentences.txt"
DEFAULT_OUTPUT = ROOT / "output"


def _lines(path: Path):
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def export(
    output_dir: Path = DEFAULT_OUTPUT,
    input_file: Path = DEFAULT_INPUT,
    sample_limit: int = 500,
):
    output_dir = Path(output_dir)
    questions = _lines(Path(input_file))
    if not questions:
        raise ValueError("Tệp câu hỏi đầu vào không được rỗng.")
    # Each independent sentence gets a separate session.
    answers = [SlideAssistant().ask(question) for question in questions]
    dialogues = [
        ["Tuần 3 học gì?", "Chương này nói về gì?"],
        ["Bài tập lớn có phần parser không?", "Phần này cần xuất file gì?"],
        ["Chương 11 có hỏi đáp không?", "Còn chương sau?"],
    ]
    dialogue_results = []
    for turns in dialogues:
        bot = SlideAssistant()
        dialogue_results.append([bot.ask(turn) for turn in turns])
    samples = generate_sentences(sample_limit)
    evaluation = evaluate()
    audit = evaluate(ROOT / "audit_cases.json")
    sample_audit = audit_sample_intents()
    faq_audit = audit_faq()
    output_dir.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        (output_dir / name).write_text(value, encoding="utf-8")

    write("grammar.txt", (ROOT / "grammar.cfg").read_text(encoding="utf-8"))
    write("samples.txt", "\n".join(samples) + "\n")
    write(
        "parse-results.txt",
        "\n\n".join(item.get("tree", "()") for item in answers) + "\n",
    )
    for filename, key in [
        ("semantic.txt", "logical_form"),
        ("intent-entity.txt", "intent_entity"),
        ("query.txt", "query_form"),
        ("retrieval.txt", "retrieval"),
        ("answer.txt", "answer"),
    ]:
        records = []
        for item in answers:
            record = {
                "input": item["input"],
                key: item.get(key),
                "error": item.get("error"),
            }
            if filename == "semantic.txt":
                record["resolved_logical_form"] = item.get("resolved_logical_form")
                record["semantic_composition"] = item.get("semantic_composition", [])
            if filename == "retrieval.txt":
                record["supporting_evidence"] = item.get("supporting_evidence", [])
            records.append(record)
        write(
            filename,
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
            + "\n",
        )
    write(
        "dialogue.txt",
        "\n\n".join(
            json.dumps(dialogue, ensure_ascii=False, indent=2)
            for dialogue in dialogue_results
        )
        + "\n",
    )
    write(
        "evaluation-results.json",
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n",
    )
    write("audit-results.json", json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    write(
        "sample-intent-audit.json",
        json.dumps(sample_audit, ensure_ascii=False, indent=2) + "\n",
    )
    write("faq-audit.json", json.dumps(faq_audit, ensure_ascii=False, indent=2) + "\n")
    summary = [
        "ĐÁNH GIÁ BẢN THỬ NGHIỆM - CÁC CASE ĐƯỢC DÙNG TRONG PHÁT TRIỂN",
        f"Số case: {evaluation['total']}",
        f"Đáp ứng toàn bộ tiêu chí khai báo: {evaluation['passed']}",
        f"Chưa đáp ứng: {evaluation['failed']}",
        f"Tỷ lệ đáp ứng tiêu chí: {evaluation['pass_rate']:.1%}",
        "Mỗi case kiểm tra intent, trạng thái, các giá trị/nguồn khai báo và hiển thị kết quả.",
        "Đây không phải tập độc lập; không suy rộng thành độ chính xác tổng quát.",
        f"So nhãn intent Q001–Q028 của dữ liệu mẫu: {sample_audit['passed']}/{sample_audit['total']} (không kiểm tra đáp án).",
        f"Văn phạm nhận diện {faq_audit['recognized']}/{faq_audit['total']} câu FAQ (chỉ nhận diện, không chấm câu trả lời).",
        f"Trong FAQ, {faq_audit['found']} câu có retrieval FOUND; các câu khác cần xem kết quả cụ thể.",
        "",
        "Các case chưa đáp ứng:",
    ]
    for case in evaluation["cases"]:
        if not case["passed"]:
            failed = ", ".join(
                key for key, passed in case["checks"].items() if not passed
            )
            summary.append(
                f"{case['id']}: {' → '.join(case['turns'])} | sai: {failed} | thực tế: {case['actual'].get('error', case['actual'].get('retrieval'))}"
            )
    summary.extend(
        [
            "",
            "BỘ KHẢO SÁT BỔ SUNG (cùng nhóm phát triển, không phải tập độc lập):",
            f"Số case: {audit['total']}; đáp ứng tiêu chí: {audit['passed']}; chưa đáp ứng: {audit['failed']}",
            "Các case chưa đáp ứng:",
        ]
    )
    for case in audit["cases"]:
        if not case["passed"]:
            failed = ", ".join(
                key for key, passed in case["checks"].items() if not passed
            )
            summary.append(
                f"{case['id']}: {' → '.join(case['turns'])} | sai: {failed} | thực tế: {case['actual'].get('error', case['actual'].get('retrieval'))}"
            )
            if case.get("failure_analysis"):
                summary.append("  Phân tích: " + case["failure_analysis"])
    summary.extend(["", "Câu mẫu chưa nhận diện đúng intent:"])
    for case in sample_audit["cases"]:
        if not case["passed"]:
            summary.append(
                f"{case['id']}: {case['question']} | mong đợi: {case['expected_intent']} | thực tế: {case['actual_intent']}"
            )
    summary.extend(["", "Câu FAQ chưa được văn phạm nhận diện:"])
    summary.extend(
        f"{case['id']}: {case['question']}"
        for case in faq_audit["cases"]
        if not case["recognized"]
    )
    summary.extend(["", "Câu FAQ không có retrieval FOUND (không tự kết luận là lỗi):"])
    summary.extend(
        f"{case['id']}: {case['question']} | {case['retrieval_status']}"
        for case in faq_audit["cases"]
        if case["retrieval_status"] != "FOUND"
    )
    write("evaluation.txt", "\n".join(summary) + "\n")
    return {
        "output_dir": str(output_dir),
        "questions": len(questions),
        "samples": len(samples),
        "evaluation_total": evaluation["total"],
        "evaluation_passed": evaluation["passed"],
        "evaluation_failed": evaluation["failed"],
        "sample_intent_passed": sample_audit["passed"],
        "audit_total": audit["total"],
        "audit_passed": audit["passed"],
        "audit_failed": audit["failed"],
        "sample_intent_total": sample_audit["total"],
        "faq_recognized": faq_audit["recognized"],
        "faq_total": faq_audit["total"],
    }
