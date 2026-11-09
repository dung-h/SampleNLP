"""Load a small set of source-backed facts for the isolated experiment."""

from dataclasses import dataclass
from pathlib import Path
import re
import yaml


ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Fact:
    predicate: str
    args: tuple[str, ...]
    source: str


class KnowledgeBase:
    def __init__(self, data_dir: Path | None = None, relation_path: Path | None = None):
        use_default_relations = data_dir is None
        self.data_dir = (
            Path(data_dir) if data_dir is not None else ROOT / "data" / "raw"
        )
        self.facts: list[Fact] = []
        self._load_chapters()
        self._load_weeks()
        self._load_course()
        self._load_assignment()
        self._load_regulations()
        self._load_resources()
        if relation_path is None and use_default_relations:
            relation_path = Path(__file__).parent / "annotations" / "relations.yaml"
        if relation_path is not None:
            self._load_relations(Path(relation_path))

    def _load_relations(self, path: Path):
        annotations = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if annotations.get("version") != 1:
            raise ValueError("Phiên bản chú giải quan hệ không được hỗ trợ.")
        seen = set()
        for key, predicate, fields, checks in (
            (
                "resource_topics",
                "RESOURCE_TOPIC",
                ("resource", "topic"),
                ("RESOURCE_TITLE", None),
            ),
            (
                "lo_chapters",
                "LO_CHAPTER",
                ("lo", "chapter"),
                ("LO_DESCRIPTION", "CHAPTER"),
            ),
        ):
            for record in annotations.get(key, []):
                record_id = record.get("id")
                evidence = record.get("evidence")
                args = tuple(record.get(field) for field in fields)
                if not isinstance(record_id, str) or not record_id or record_id in seen:
                    raise ValueError("Mã chú giải quan hệ thiếu hoặc trùng.")
                if (
                    not all(isinstance(arg, str) and arg for arg in args)
                    or not isinstance(evidence, dict)
                    or not evidence.get("explanation")
                ):
                    raise ValueError(
                        f"Chú giải {record_id} thiếu đối tượng hoặc căn cứ."
                    )
                for value, expected_predicate in zip(args, checks):
                    if expected_predicate and not any(
                        f.predicate == expected_predicate and f.args[0] == value
                        for f in self.facts
                    ):
                        raise ValueError(
                            f"Chú giải {record_id} tham chiếu đối tượng không có trong KB: {value}."
                        )
                seen.add(record_id)
                self.facts.append(
                    Fact(predicate, args, f"annotation:slide_relations:{record_id}")
                )

    def _load_chapters(self):
        text = (self.data_dir / "topics.txt").read_text(encoding="utf-8")
        headers = list(re.finditer(r"^CHAPTER\s+(\d+):[^\n]*$", text, re.MULTILINE))
        if not headers:
            raise ValueError("Không tìm thấy bản ghi chương trong topics.txt.")
        for i, header in enumerate(headers):
            block = text[
                header.end() : headers[i + 1].start()
                if i + 1 < len(headers)
                else len(text)
            ]
            id_match = re.search(r"^chapter_id:\s*(CH\d+)\s*$", block, re.MULTILINE)
            keywords = re.search(r"^keywords:\s*(.+)$", block, re.MULTILINE)
            if not id_match or not keywords:
                raise ValueError(f"Chương {header.group(1)} thiếu mã hoặc từ khóa.")
            chapter = id_match.group(1)
            if chapter != f"CH{int(header.group(1)):02d}":
                raise ValueError(f"Mã chương không khớp tiêu đề: {chapter}.")
            source = f"topics:{chapter}"
            self.facts.append(Fact("CHAPTER", (chapter,), source))
            for keyword in keywords.group(1).split(","):
                value = keyword.strip()
                if value:
                    self.facts.append(
                        Fact("HAS_KEYWORD", (chapter, value.upper()), source)
                    )
                    normalized = (
                        "QUESTION ANSWERING" if value.upper() == "QA" else value.upper()
                    )
                    self.facts.append(Fact("HAS_TOPIC", (chapter, normalized), source))
            summary = re.search(
                r"^summary:\s*\n(.*?)(?=^subtopics:|\Z)",
                block,
                re.MULTILINE | re.DOTALL,
            )
            if summary and summary.group(1).strip():
                self.facts.append(
                    Fact(
                        "CHAPTER_SUMMARY",
                        (chapter, " ".join(summary.group(1).split())),
                        source,
                    )
                )
            subtopics = re.search(
                r"^subtopics:\s*\n(.*)", block, re.MULTILINE | re.DOTALL
            )
            if subtopics:
                for line in subtopics.group(1).splitlines():
                    if re.match(r"^\d+\.\d+", line.strip()):
                        self.facts.append(
                            Fact("CHAPTER_SUBTOPIC", (chapter, line.strip()), source)
                        )
                        for topic in (
                            "CFG",
                            "PCFG",
                            "PARSING",
                            "REFERENCE",
                            "SEMANTIC GRAMMAR",
                            "QUESTION ANSWERING",
                            "SELECTIONAL RESTRICTION",
                        ):
                            if re.search(
                                r"(?<!\w)" + re.escape(topic) + r"(?!\w)",
                                line,
                                re.IGNORECASE,
                            ):
                                fact = Fact("HAS_TOPIC", (chapter, topic), source)
                                if fact not in self.facts:
                                    self.facts.append(fact)

    def _load_weeks(self):
        text = (self.data_dir / "schedule.txt").read_text(encoding="utf-8")
        headers = list(re.finditer(r"^WEEK\s+(\d+)\s*$", text, re.MULTILINE))
        if not headers:
            raise ValueError("Không tìm thấy bản ghi tuần trong schedule.txt.")
        for i, header in enumerate(headers):
            block = text[
                header.end() : headers[i + 1].start()
                if i + 1 < len(headers)
                else len(text)
            ]
            week = f"WEEK_{int(header.group(1)):02d}"
            source = f"schedule:{week}"
            chapter = re.search(
                r"^chapter:\s*Chapter\s+(\d+)\s*$", block, re.MULTILINE | re.IGNORECASE
            )
            if chapter:
                self.facts.append(
                    Fact(
                        "SCHEDULED_IN", (f"CH{int(chapter.group(1)):02d}", week), source
                    )
                )
            topics = re.search(r"^topics:\s*\n((?:- [^\n]+\n?)+)", block, re.MULTILINE)
            if topics:
                for line in topics.group(1).splitlines():
                    self.facts.append(
                        Fact("WEEK_TOPIC", (week, line[2:].strip()), source)
                    )

    def chapter_for_week(self, week: str) -> list[str]:
        return list(
            dict.fromkeys(
                f.args[0]
                for f in self.facts
                if f.predicate == "SCHEDULED_IN" and f.args[1] == week
            )
        )

    def _load_course(self):
        text = (self.data_dir / "course_info.txt").read_text(encoding="utf-8")
        source = "course_info:CO3085"
        for key in (
            "credits",
            "ects",
            "department",
            "semester",
            "course_type",
            "format",
            "total_course_hours",
            "lecture_hours",
            "major_assignment_hours",
            "self_study_hours",
        ):
            value = re.search(rf"^{key}:\s*(.+)$", text, re.MULTILINE)
            if value:
                self.facts.append(
                    Fact(
                        "COURSE_PROPERTY",
                        ("CO3085", key, value.group(1).strip()),
                        source,
                    )
                )
        parts = re.search(
            r"^main_parts:\s*\n(.*?)(?=\n\s*\n)", text, re.MULTILINE | re.DOTALL
        )
        if parts:
            for line in parts.group(1).splitlines():
                if line.strip():
                    self.facts.append(
                        Fact("COURSE_PART", ("CO3085", line.strip()), source)
                    )
        outcomes = re.search(
            r"^detailed_learning_outcomes:\s*\n(.*?)(?=\n\s*\n)",
            text,
            re.MULTILINE | re.DOTALL,
        )
        if outcomes:
            for item in re.finditer(
                r"^(LO\d+\.\d+)\s*-\s*(.*?)(?=^LO\d+\.\d+\s*-|\Z)",
                outcomes.group(1),
                re.MULTILINE | re.DOTALL,
            ):
                self.facts.append(
                    Fact(
                        "LO_DESCRIPTION",
                        (item.group(1), " ".join(item.group(2).split())),
                        source,
                    )
                )
        exams = re.search(r"^exam_format:\s*\n(.*)", text, re.MULTILINE | re.DOTALL)
        if exams:
            for name, minutes in re.findall(
                r"^(midterm|final):[^\n]*?(\d+)\s+minutes",
                exams.group(1),
                re.MULTILINE | re.IGNORECASE,
            ):
                self.facts.append(
                    Fact("EXAM_DURATION", (name.upper(), f"{minutes} minutes"), source)
                )

    def _load_assignment(self):
        text = (self.data_dir / "assignments.txt").read_text(encoding="utf-8")
        source = "assignments:BTL01"
        team = re.search(r"^team_size:\s*(.+)$", text, re.MULTILINE)
        if team:
            self.facts.append(
                Fact(
                    "ASSIGNMENT_PROPERTY",
                    ("BTL01", "team_size", team.group(1).strip()),
                    source,
                )
            )
        goal = re.search(r"^goal:\s*\n(.*?)(?=\n\s*\n)", text, re.MULTILINE | re.DOTALL)
        if goal:
            self.facts.append(
                Fact(
                    "ASSIGNMENT_PROPERTY",
                    ("BTL01", "goal", " ".join(goal.group(1).split())),
                    source,
                )
            )
        headers = list(
            re.finditer(r"^PART\s+(IV|III|II|I)\s*-\s*(.+)$", text, re.MULTILINE)
        )
        numbers = {"I": 1, "II": 2, "III": 3, "IV": 4}
        for i, header in enumerate(headers):
            block = text[
                header.end() : headers[i + 1].start()
                if i + 1 < len(headers)
                else len(text)
            ]
            part = f"BTL_PART_{numbers[header.group(1)]}"
            part_source = f"assignments:{part}"
            self.facts.append(
                Fact("PART_TITLE", (part, header.group(2).strip()), part_source)
            )
            req = re.search(
                r"^(requirements|minimum_requirements|optional_or_extension):\s*\n((?:- [^\n]+\n?)+)",
                block,
                re.MULTILINE,
            )
            if req:
                for line in req.group(2).splitlines():
                    value = line[2:].strip()
                    if req.group(1) == "optional_or_extension":
                        self.facts.append(
                            Fact("PART_OPTIONAL", (part, value), part_source)
                        )
                        self.facts.append(
                            Fact(
                                "PART_REQUIREMENT",
                                (part, f"Tùy chọn/mở rộng: {value}"),
                                part_source,
                            )
                        )
                    else:
                        self.facts.append(
                            Fact("PART_REQUIREMENT", (part, value), part_source)
                        )
                        self.facts.append(
                            Fact(
                                "ASSIGNMENT_REQUIREMENT", ("BTL01", value), part_source
                            )
                        )
            outputs = re.search(
                r"^suggested_outputs:\s*\n((?:output/[^\n]+\n?)+)", block, re.MULTILINE
            )
            if outputs:
                for line in outputs.group(1).splitlines():
                    self.facts.append(
                        Fact("PART_OUTPUT", (part, line.strip()), part_source)
                    )
            if "parser" in header.group(2).casefold():
                self.facts.append(
                    Fact("PART_COMPONENT", (part, "PARSING"), part_source)
                )
                self.facts.append(
                    Fact("HAS_COMPONENT", ("BTL01", "PARSING"), part_source)
                )
            if re.search(r"\bQA\b", header.group(2)):
                self.facts.append(
                    Fact("PART_COMPONENT", (part, "QUESTION_ANSWERING"), part_source)
                )
                self.facts.append(
                    Fact("HAS_COMPONENT", ("BTL01", "QUESTION_ANSWERING"), part_source)
                )

    def _load_regulations(self):
        text = (self.data_dir / "regulations.txt").read_text(encoding="utf-8")
        for match in re.finditer(
            r"^([A-Za-z_]+):\s*\n(.*?)(?=\n\s*\n|\Z)", text, re.MULTILINE | re.DOTALL
        ):
            key, value = match.group(1).upper(), " ".join(match.group(2).split())
            source = f"regulations:{key}"
            self.facts.append(Fact("RULE_TEXT", (key, value), source))
            if key == "EXTERNAL_LIBRARIES" and value.startswith("Được phép"):
                self.facts.append(Fact("PERMITTED", (key,), source))
            if key == "ASSIGNMENT_SHARING" and value.startswith("Không được"):
                self.facts.append(Fact("NOT_PERMITTED", (key,), source))

    def _load_resources(self):
        text = (self.data_dir / "resources.txt").read_text(encoding="utf-8")
        headers = list(
            re.finditer(r"^(?:TEXTBOOK|REFERENCE)\s+\d+\s*$", text, re.MULTILINE)
        )
        for i, header in enumerate(headers, 1):
            block = text[
                header.end() : headers[i].start() if i < len(headers) else len(text)
            ]
            title = re.search(r"^title:\s*(.+)$", block, re.MULTILINE)
            if title:
                resource = f"RES{i:02d}"
                self.facts.append(
                    Fact(
                        "RESOURCE_TITLE",
                        (resource, title.group(1).strip()),
                        f"resources:{resource}",
                    )
                )
        annotation_path = self.data_dir.parent / "annotations" / "resource_topics.yaml"
        if annotation_path.exists():
            annotations = (
                yaml.safe_load(annotation_path.read_text(encoding="utf-8")) or {}
            )
            for resource, record in annotations.get("resource_topics", {}).items():
                for topic in record.get("topics", []):
                    self.facts.append(
                        Fact(
                            "RESOURCE_TOPIC",
                            (resource, topic),
                            f"annotation:resource_topics:{resource}",
                        )
                    )
