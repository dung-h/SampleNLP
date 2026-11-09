"""Orchestrate the independent CFG -> LF -> procedural QA experiment."""

from dataclasses import dataclass

from .knowledge import KnowledgeBase
from .logic import (
    Atom,
    LogicalForm,
    SemanticError,
    interpret,
    render_logical_form,
    render_expression,
)
from .procedure import UnresolvedReference, execute, resolve, translate
from .syntax import ParseError, Parser


@dataclass
class Context:
    chapter: str | None = None
    assignment_part: str | None = None
    focus: str | None = None
    previous: LogicalForm | None = None


class SlideAssistant:
    def __init__(self, kb=None):
        self.parser = Parser()
        self.kb = kb if kb is not None else KnowledgeBase()
        self.context = Context()

    def reset(self):
        self.context = Context()

    def ask(self, sentence: str) -> dict:
        result = {"input": sentence}
        try:
            tree = self.parser.parse(sentence)
            trace = []
            form = interpret(tree, trace)
            result["tree"] = tree.pformat(margin=90)
            result["logical_form"] = render_logical_form(form)
            result["semantic_composition"] = trace
            resolved = resolve(
                form,
                self.context.chapter,
                self.context.assignment_part,
                self.context.previous,
                self.context.focus,
            )
            result["resolved_logical_form"] = render_logical_form(resolved)
            result["intent_entity"] = self._intent_entity(tree, resolved)
            procedure = translate(resolved)
            result["query_form"] = self._render_query(procedure)
            retrieval = execute(procedure, self.kb)
            result["retrieval"] = {
                "status": retrieval.status,
                "values": retrieval.values,
                "sources": retrieval.sources,
            }
            result.update(self._answer_details(procedure, retrieval))
            if retrieval.status == "FOUND" and tree[0].label() == "RESOURCE_TOPIC":
                result["answer"] = (
                    "Tài liệu tìm được có nội dung liên quan đến chủ đề theo chú giải "
                    "(chưa khẳng định đầy đủ): "
                    + "; ".join(retrieval.values)
                    + ". Nguồn: "
                    + ", ".join(retrieval.sources)
                )
            if retrieval.status == "FOUND" and tree[0].label() == "RESOURCE_CHAPTER":
                result["answer"] = (
                    "Tài liệu liên quan theo chủ đề: "
                    + "; ".join(retrieval.values)
                    + ". Đây không phải danh sách tài liệu giảng viên chỉ định. Nguồn: "
                    + ", ".join(retrieval.sources)
                )
            if retrieval.status == "FOUND" and tree[0].label() == "LO_RELATED":
                result["answer"] = (
                    "Chương liên quan theo đối chiếu thử nghiệm: "
                    + "; ".join(retrieval.values)
                    + ". Nguồn: "
                    + ", ".join(retrieval.sources)
                )
            self._update_context(tree[0].label(), resolved, retrieval)
            result["context"] = self._context()
        except (ParseError, SemanticError, UnresolvedReference) as exc:
            if isinstance(exc, ParseError):
                self.reset()
            result["error"] = str(exc)
            result["answer"] = str(exc)
            result["intent_entity"] = {"intent": "UNKNOWN", "entities": {}}
            result["context"] = self._context()
        return result

    @staticmethod
    def _render_query(procedure):
        variable = f" ?{procedure.variable.name}" if procedure.variable else ""
        if procedure.restriction is not None:
            return (
                f"{procedure.operation} ?{procedure.scope_variable.name}{variable} "
                f"RESTRICT {render_expression(procedure.restriction)} "
                f"BODY {render_expression(procedure.expression)}"
            )
        return f"{procedure.operation}{variable} WHERE {render_expression(procedure.expression)}"

    def _answer_details(self, procedure, retrieval):
        answer = self._answer(procedure.operation, retrieval)
        if procedure.operation == "COUNT" and retrieval.status == "FOUND":
            answer = f"Môn học có {retrieval.values[0]} phần. Nguồn: " + ", ".join(
                retrieval.sources
            )
        if procedure.operation == "FIND_THE" and retrieval.status == "UNKNOWN":
            messages = {
                "NO_REFERENT": "Không tìm thấy chương phù hợp trong KB.",
                "AMBIGUOUS_REFERENT": "Có nhiều chương phù hợp trong KB, chưa xác định được chương duy nhất.",
                "MISSING_BODY": "Đã tìm thấy một chương phù hợp nhưng chưa có dữ liệu tuần học tương ứng.",
            }
            answer = messages.get(
                retrieval.reason, "Chưa đủ dữ liệu để xác định kết quả."
            )
        if procedure.operation == "CHECK_ALL" and retrieval.status == "FOUND":
            answer = (
                "Có, với các chương thuộc phạm vi tìm được trong KB. Nguồn: "
                + ", ".join(retrieval.sources)
            )
        details = {"answer": answer}
        if (
            retrieval.status == "UNKNOWN"
            and isinstance(procedure.expression, Atom)
            and procedure.expression.predicate == "PERMITTED"
        ):
            rule_id = procedure.expression.args[0]
            rules = [
                fact
                for fact in self.kb.facts
                if fact.predicate == "RULE_TEXT" and fact.args[0] == rule_id
            ]
            if rules:
                details["supporting_evidence"] = [
                    {"text": fact.args[1], "source": fact.source} for fact in rules
                ]
                evidence = "; ".join(
                    f"{fact.args[1]} (nguồn: {fact.source})" for fact in rules
                )
                details["answer"] += " Quy định liên quan: " + evidence
        return details

    def _update_context(self, label, form, retrieval):
        if label == "CHAPTER_BY_TOPIC":
            chapters = retrieval.values if retrieval.status == "FOUND" else []
            self.context.chapter = chapters[0] if len(chapters) == 1 else None
            self.context.focus = "chapter" if self.context.chapter else None
        elif (
            isinstance(form.expression, Atom)
            and form.expression.predicate == "WEEK_TOPIC"
        ):
            self.context.chapter = None
            self.context.focus = "week"
            if retrieval.status == "FOUND":
                chapters = self.kb.chapter_for_week(form.expression.args[0])
                if len(chapters) == 1:
                    self.context.chapter = chapters[0]
        elif isinstance(form.expression, Atom):
            self._update_context_for_atom(form.expression, retrieval)
        self.context.previous = form

    def _update_context_for_atom(self, atom, retrieval):
        if atom.predicate in {
            "HAS_KEYWORD",
            "HAS_TOPIC",
            "DISCUSSES",
            "CHAPTER_SUMMARY",
            "CHAPTER_SUBTOPIC",
        }:
            chapter = atom.args[0]
            if any(
                f.predicate == "CHAPTER" and f.args == (chapter,) for f in self.kb.facts
            ):
                self.context.chapter = chapter
                self.context.focus = "chapter"
            else:
                self.context.chapter = None
                self.context.focus = None
        elif atom.predicate == "HAS_COMPONENT":
            self.context.assignment_part = None
            self.context.focus = "assignment"
            if retrieval.status == "FOUND" and retrieval.values == [True]:
                parts = sorted(
                    {
                        f.args[0]
                        for f in self.kb.facts
                        if f.predicate == "PART_COMPONENT" and f.args[1] == atom.args[1]
                    }
                )
                if len(parts) == 1:
                    self.context.assignment_part = parts[0]
                    self.context.focus = "assignment_part"
        elif atom.predicate in {"PART_TITLE", "PART_REQUIREMENT", "PART_OUTPUT"}:
            self.context.assignment_part = atom.args[0]
            self.context.focus = "assignment_part"
        elif atom.predicate in {"COURSE_PROPERTY", "COURSE_PART", "INSTRUCTOR_NAME"}:
            self.context.focus = "course"

    def _context(self):
        return {
            "chapter": self.context.chapter,
            "assignment_part": self.context.assignment_part,
            "focus": self.context.focus,
        }

    @staticmethod
    def _intent_entity(tree, form):
        label = tree[0].label()
        intents = {
            "CHAPTER_BY_TOPIC": "GET_TOPIC",
            "CHAPTER_BOOLEAN": "GET_TOPIC",
            "CHAPTER_TOPICS": "GET_TOPIC",
            "CHAPTER_COMMON_TOPICS": "GET_TOPIC",
            "CHAPTER_ELLIPSIS": "GET_TOPIC",
            "WEEK_CONTENT": "GET_SCHEDULE",
            "WEEK_OF_CHAPTER": "GET_SCHEDULE",
            "WEEK_OF_TOPIC": "GET_SCHEDULE",
            "COURSE_ATTRIBUTE": "GET_COURSE_INFO",
            "COURSE_PARTS": "GET_COURSE_INFO",
            "EXAM_DURATION": "GET_COURSE_INFO",
            "INSTRUCTOR": "GET_INSTRUCTOR",
            "LO_DESCRIPTION": "GET_LO",
            "LO_RELATED": "GET_LO",
            "ASSIGNMENT_GOAL": "GET_ASSIGNMENT",
            "ASSIGNMENT_REQUIREMENTS": "GET_ASSIGNMENT",
            "ASSIGNMENT_LIST": "GET_ASSIGNMENT",
            "ASSIGNMENT_PART": "GET_ASSIGNMENT",
            "ASSIGNMENT_TEAM": "GET_ASSIGNMENT",
            "ASSIGNMENT_COMPONENT": "GET_ASSIGNMENT",
            "ASSIGNMENT_OUTPUTS": "GET_ASSIGNMENT",
            "DEADLINE": "GET_DEADLINE",
            "RESOURCE_TOPIC": "GET_RESOURCE",
            "RESOURCE_CHAPTER": "GET_RESOURCE",
            "REGULATION": "GET_RULE",
            "PERMISSION": "GET_RULE",
            "SYSTEM_NOT_FOUND_RULE": "GET_RULE",
            "EACH_CHAPTER_WEEK": "GET_SCHEDULE",
            "EVERY_CHAPTER_WEEK": "GET_SCHEDULE",
            "THE_CHAPTER_WEEK": "GET_SCHEDULE",
        }
        entities = {}

        def visit(expr):
            if not isinstance(expr, Atom):
                for child in expr.children:
                    visit(child)
                return
            if expr.predicate in {
                "HAS_KEYWORD",
                "HAS_TOPIC",
                "DISCUSSES",
                "CHAPTER_SUMMARY",
                "CHAPTER_SUBTOPIC",
                "SCHEDULED_IN",
                "TAUGHT_IN",
                "CHAPTER_RESOURCE",
            }:
                chapter = expr.args[0]
                if isinstance(chapter, str) and chapter.startswith("CH"):
                    entities.setdefault("chapter", []).append(chapter)
            if expr.predicate in {
                "HAS_KEYWORD",
                "HAS_TOPIC",
                "DISCUSSES",
            } and isinstance(expr.args[1], str):
                entities.setdefault("topic", []).append(expr.args[1])
            if expr.predicate == "WEEK_TOPIC":
                entities.setdefault("week", []).append(expr.args[0])
            if expr.predicate in {
                "PART_TITLE",
                "PART_REQUIREMENT",
                "PART_OUTPUT",
                "PART_DEADLINE",
            }:
                entities.setdefault("assignment_part", []).append(expr.args[0])
            if expr.predicate in {"COURSE_PROPERTY", "COURSE_PART", "INSTRUCTOR_NAME"}:
                entities.setdefault("course", []).append(expr.args[0])
            if expr.predicate == "EXAM_DURATION":
                entities.setdefault("exam", []).append(expr.args[0])
            if expr.predicate in {"LO_DESCRIPTION", "LO_RELATED_CONTENT", "LO_CHAPTER"}:
                entities.setdefault("learning_outcome", []).append(expr.args[0])
            if expr.predicate in {
                "ASSIGNMENT_PROPERTY",
                "ASSIGNMENT_REQUIREMENT",
                "ASSIGNMENT_DEADLINE",
                "HAS_COMPONENT",
            }:
                entities.setdefault("assignment", []).append(expr.args[0])
            if expr.predicate == "HAS_COMPONENT":
                entities.setdefault("topic", []).append(expr.args[1])
            if expr.predicate in {"RULE_TEXT", "PERMITTED"}:
                entities.setdefault("regulation", []).append(expr.args[0])
            if expr.predicate == "RESOURCE_TOPIC" and isinstance(expr.args[1], str):
                entities.setdefault("topic", []).append(expr.args[1])

        visit(form.expression)
        if form.restriction is not None:
            visit(form.restriction)
        return {
            "intent": intents[label],
            "entities": {
                key: list(dict.fromkeys(values)) for key, values in entities.items()
            },
        }

    @staticmethod
    def _answer(operation, retrieval):
        if retrieval.status == "UNKNOWN":
            return "Chưa đủ dữ liệu để kết luận có hay không."
        if retrieval.status == "NOT_FOUND":
            return "Không tìm thấy kết quả trong dữ liệu thử nghiệm."
        if operation in {"TEST", "CHECK_ALL"}:
            prefix = "Có" if retrieval.values == [True] else "Không"
            return prefix + ". Nguồn: " + ", ".join(retrieval.sources)
        return (
            "Kết quả: "
            + "; ".join(retrieval.values)
            + ". Nguồn: "
            + ", ".join(retrieval.sources)
        )
