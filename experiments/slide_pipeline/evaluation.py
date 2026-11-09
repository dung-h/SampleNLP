"""Evaluate explicitly stated criteria; not an independent accuracy claim."""

import json
from pathlib import Path
import re

from .assistant import SlideAssistant


DEFAULT_CASES = Path(__file__).with_name("evaluation_cases.json")
SAMPLE_QUERIES = (
    Path(__file__).resolve().parents[2] / "data" / "raw" / "sample_queries.txt"
)
FAQ = Path(__file__).resolve().parents[2] / "data" / "raw" / "faq.txt"


def audit_faq(path: Path = FAQ) -> dict:
    """Report grammar recognition only; FAQ question/answer is not graded here."""
    text = Path(path).read_text(encoding="utf-8")
    cases = []
    for item_id, question in re.findall(
        r"^Q(\d+):\s*\nquestion:\s*(.+)$", text, re.MULTILINE
    ):
        output = SlideAssistant().ask(question.strip())
        cases.append(
            {
                "id": f"Q{item_id}",
                "question": question.strip(),
                "recognized": "tree" in output,
                "intent": output.get("intent_entity", {}).get("intent"),
                "retrieval_status": output.get("retrieval", {}).get("status"),
                "error": output.get("error"),
            }
        )
    recognized = sum(case["recognized"] for case in cases)
    found = sum(case["retrieval_status"] == "FOUND" for case in cases)
    return {
        "total": len(cases),
        "recognized": recognized,
        "unrecognized": len(cases) - recognized,
        "found": found,
        "cases": cases,
    }


def audit_sample_intents(path: Path = SAMPLE_QUERIES) -> dict:
    """Compare Q001–Q028 intent labels only; context cases need sessions."""
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        match = re.match(r"^(Q\d+)\s*\|\s*(.*?)\s*\|\s*([A-Z_]+)\s*\|", line)
        if not match or int(match.group(1)[1:]) > 28:
            continue
        item_id, sentence, expected = match.groups()
        output = SlideAssistant().ask(sentence)
        actual = output.get("intent_entity", {}).get("intent")
        cases.append(
            {
                "id": item_id,
                "question": sentence,
                "expected_intent": expected,
                "actual_intent": actual,
                "passed": actual == expected,
                "error": output.get("error"),
            }
        )
    passed = sum(case["passed"] for case in cases)
    return {
        "total": len(cases),
        "passed": passed,
        "failed": len(cases) - passed,
        "cases": cases,
    }


def evaluate(cases_path: Path = DEFAULT_CASES) -> dict:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Tập đánh giá phải là danh sách không rỗng.")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Mã case đánh giá bị trùng.")
    results = []
    for case in cases:
        bot = SlideAssistant()
        outputs = [bot.ask(turn) for turn in case["turns"]]
        actual = outputs[-1]
        expected = case["expected"]
        retrieval = actual.get("retrieval", {})
        checks = {
            "intent": actual.get("intent_entity", {}).get("intent")
            == expected["intent"],
            "status": retrieval.get("status", "NO_RETRIEVAL") == expected["status"],
        }
        for entity, values in expected.get("entities", {}).items():
            checks[f"entity:{entity}"] = (
                actual.get("intent_entity", {}).get("entities", {}).get(entity)
                == values
            )
        for value in expected.get("values_include", []):
            checks[f"value:{value}"] = value in retrieval.get("values", [])
        for value in expected.get("values_exclude", []):
            checks[f"absent:{value}"] = value not in retrieval.get("values", [])
        if "values_exact" in expected:
            checks["values_exact"] = retrieval.get("values") == expected["values_exact"]
        for source in expected.get("sources_include", []):
            checks[f"source:{source}"] = source in retrieval.get("sources", [])
        for source in expected.get("evidence_sources_include", []):
            checks[f"evidence:{source}"] = any(
                item.get("source") == source
                for item in actual.get("supporting_evidence", [])
            )
        for text in expected.get("answer_contains", []):
            checks[f"answer:{text}"] = (
                text.casefold() in actual.get("answer", "").casefold()
            )
        if retrieval.get("status") == "FOUND":
            answer = actual.get("answer", "").casefold()
            checks["sources_present"] = bool(retrieval.get("sources"))
            checks["values_in_answer"] = all(
                ("có" if value else "không") in answer
                if isinstance(value, bool)
                else str(value).casefold() in answer
                for value in retrieval.get("values", [])
            )
        elif retrieval.get("status") in {"NOT_FOUND", "UNKNOWN"}:
            # Sources may document partial evidence without asserting an answer.
            checks["no_unsupported_values"] = not retrieval.get("values")
        results.append(
            {
                "id": case["id"],
                "turns": case["turns"],
                "passed": all(checks.values()),
                "checks": checks,
                "actual": actual,
                "basis": case["basis"],
                "failure_analysis": case.get("failure_analysis"),
            }
        )
    passed = sum(item["passed"] for item in results)
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results),
        "cases": results,
    }
