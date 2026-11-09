"""Run from the repository root with Windows Python."""

import argparse
import json
import sys

from .assistant import SlideAssistant


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="CFG -> logical form -> procedural QA")
    parser.add_argument(
        "--question",
        action="append",
        help="Câu hỏi; có thể truyền nhiều lần cho cùng hội thoại.",
    )
    parser.add_argument(
        "--demo", action="store_true", help="Chạy bốn kịch bản độc lập."
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Xuất bộ tệp bài tập trong thư mục thử nghiệm.",
    )
    args = parser.parse_args()
    if sum(bool(value) for value in (args.demo, args.question, args.export)) != 1:
        parser.error("Chọn một trong --demo, --export hoặc --question.")
    if args.export:
        from .exporter import export

        print(json.dumps(export(), ensure_ascii=False, indent=2))
        return
    if args.demo:
        scenarios = [
            ["Chương nào nói về CFG?"],
            ["Chương 3 có CFG không?"],
            ["Chương nào nói về CFG và PCFG?"],
            ["Tuần 3 học gì?", "Chương này nói về gì?"],
        ]
    elif args.question:
        scenarios = [args.question]
    for i, questions in enumerate(scenarios, 1):
        assistant = SlideAssistant()
        for question in questions:
            print(
                json.dumps(
                    {"scenario": i, **assistant.ask(question)},
                    ensure_ascii=False,
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
