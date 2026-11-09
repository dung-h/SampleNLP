"""A small, typed logical-form language, not general first-order logic."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Variable:
    name: str


@dataclass(frozen=True)
class Reference:
    kind: str


@dataclass(frozen=True)
class Atom:
    predicate: str
    args: tuple


@dataclass(frozen=True)
class Connective:
    operator: str
    children: tuple


@dataclass(frozen=True)
class LogicalForm:
    query_kind: str  # WH, YES_NO, COUNT, EACH, EVERY, THE, or ELLIPSIS
    variable: Variable | None
    expression: Atom | Connective
    scope_variable: Variable | None = None
    restriction: Atom | Connective | None = None


class SemanticError(ValueError):
    pass


@dataclass(frozen=True)
class TopicMeaning:
    """Meaning of a topic constituent before its chapter argument is known."""

    topics: tuple[str, ...]
    operator: str | None = None

    def apply(self, chapter):
        atoms = tuple(Atom("DISCUSSES", (chapter, topic)) for topic in self.topics)
        return atoms[0] if len(atoms) == 1 else Connective(self.operator, atoms)


def compose_topic_expression(node, trace=None):
    """Compose TOPIC and CONJUNCTION children into a reusable predicate."""
    if node.label() == "TOPIC":
        value = _topic(node)
        if trace is not None:
            trace.append({"constituent": "TOPIC", "meaning": value})
        return TopicMeaning((value,))
    if node.label() != "TOPIC_EXPR":
        raise SemanticError(f"Không phải thành phần chủ đề: {node.label()}.")
    children = [
        compose_topic_expression(child, trace)
        for child in node
        if hasattr(child, "label") and child.label() == "TOPIC"
    ]
    if len(children) == 1:
        meaning = children[0]
    elif len(children) == 2:
        conjunction = next(
            child
            for child in node
            if hasattr(child, "label") and child.label() == "CONJUNCTION"
        )
        operator = {"và": "AND", "hoặc": "OR"}.get(conjunction.leaves()[0])
        if operator is None:
            raise SemanticError("Liên từ chủ đề không được hỗ trợ.")
        meaning = TopicMeaning(
            tuple(topic for child in children for topic in child.topics), operator
        )
    else:
        raise SemanticError("Số lượng chủ đề không được hỗ trợ.")
    if trace is not None:
        trace.append(
            {
                "constituent": "TOPIC_EXPR",
                "meaning": render_expression(meaning.apply(Variable("chapter"))),
            }
        )
    return meaning


def _chapter(node):
    words = node.leaves()
    if words == ["nó"]:
        return Reference("pronoun")
    if words[1] == "này":
        return Reference("chapter")
    return f"CH{int(words[1]):02d}"


def _part(node):
    value = node.leaves()[1]
    if value == "này":
        return Reference("assignment_part")
    number = {"i": 1, "ii": 2, "iii": 3, "iv": 4}.get(value)
    return f"BTL_PART_{number if number else int(value)}"


def _topic(node):
    name = " ".join(node.leaves()).upper()
    return {
        "HỎI ĐÁP": "QUESTION ANSWERING",
        "PARSER": "PARSING",
        "FEATURES": "FEATURE",
        "LOCAL DISCOURSE CONTEXT": "DISCOURSE CONTEXT",
    }.get(name, name)


def _wh(name, predicate, *args):
    variable = Variable(name)
    return LogicalForm("WH", variable, Atom(predicate, (*args, variable)))


def _topic_condition(node, chapter, trace=None):
    expr = next(node.subtrees(lambda item: item.label() == "TOPIC_EXPR"))
    return compose_topic_expression(expr, trace).apply(chapter)


def _interpret_chapter_and_schedule(node, trace=None) -> LogicalForm | None:
    """Interpret the chapter/topic and schedule productions, if applicable."""
    label = node.label()
    if label in {"EACH_CHAPTER_WEEK", "EVERY_CHAPTER_WEEK", "THE_CHAPTER_WEEK"}:
        chapter = Variable("chapter")
        topic = compose_topic_expression(
            next(node.subtrees(lambda item: item.label() == "TOPIC")), trace
        )
        restriction = Connective(
            "AND", (Atom("CHAPTER", (chapter,)), topic.apply(chapter))
        )
        if label == "EVERY_CHAPTER_WEEK":
            number = next(
                node.subtrees(lambda item: item.label() == "NUMBER")
            ).leaves()[0]
            return LogicalForm(
                "EVERY",
                None,
                Atom("TAUGHT_IN", (chapter, f"WEEK_{int(number):02d}")),
                chapter,
                restriction,
            )
        week = Variable("week")
        return LogicalForm(
            "EACH" if label == "EACH_CHAPTER_WEEK" else "THE",
            week,
            Atom("TAUGHT_IN", (chapter, week)),
            chapter,
            restriction,
        )
    if label == "CHAPTER_BY_TOPIC":
        x = Variable("chapter")
        if trace is not None and any(
            child.label() == "CHAPTER_WH" for child in node if hasattr(child, "label")
        ):
            trace.append(
                {
                    "constituent": "CHAPTER_WH",
                    "meaning": "WH ?chapter: CHAPTER(?chapter)",
                }
            )
        if trace is not None:
            if any(
                child.label() == "TOPIC_VERB"
                for child in node
                if hasattr(child, "label")
            ):
                trace.append(
                    {
                        "constituent": "TOPIC_VERB",
                        "meaning": "DISCUSSES(chapter, topic)",
                    }
                )
        relation = _topic_condition(node, x, trace)
        form = LogicalForm(
            "WH", x, Connective("AND", (Atom("CHAPTER", (x,)), relation))
        )
        if trace is not None:
            trace.append({"constituent": label, "meaning": render_logical_form(form)})
        return form
    if label == "CHAPTER_BOOLEAN":
        topic = next(node.subtrees(lambda item: item.label() == "TOPIC"))
        return LogicalForm(
            "YES_NO",
            None,
            compose_topic_expression(topic, trace).apply(_chapter(node[0])),
        )
    if label == "WEEK_CONTENT":
        x = Variable("content")
        week = f"WEEK_{int(node[1].leaves()[0]):02d}"
        return LogicalForm("WH", x, Atom("WEEK_TOPIC", (week, x)))
    if label == "CHAPTER_TOPICS":
        predicate = (
            "CHAPTER_SUBTOPIC"
            if "phương" in node.leaves() or "chủ" in node.leaves()
            else "CHAPTER_SUMMARY"
        )
        return _wh("content", predicate, _chapter(node[0]))
    if label == "CHAPTER_COMMON_TOPICS":
        topic = Variable("topic")
        return LogicalForm(
            "WH",
            topic,
            Connective(
                "AND",
                (
                    Atom("HAS_TOPIC", (_chapter(node[0]), topic)),
                    Atom("HAS_TOPIC", (_chapter(node[2]), topic)),
                ),
            ),
        )
    if label == "WEEK_OF_CHAPTER":
        week = Variable("week")
        chapters = [
            _chapter(child)
            for child in node[0]
            if hasattr(child, "label") and child.label() == "CHAPTER_REF"
        ]
        atoms = tuple(Atom("SCHEDULED_IN", (chapter, week)) for chapter in chapters)
        expression = atoms[0] if len(atoms) == 1 else Connective("OR", atoms)
        return LogicalForm("WH", week, expression)
    if label == "WEEK_OF_TOPIC":
        week, chapter = Variable("week"), Variable("chapter")
        return LogicalForm(
            "WH",
            week,
            Connective(
                "AND",
                (
                    _topic_condition(node, chapter, trace),
                    Atom("TAUGHT_IN", (chapter, week)),
                ),
            ),
        )
    return None


def interpret(tree, trace=None) -> LogicalForm:
    """Build meaning from the recognized production and its constituents."""
    node = tree[0]
    chapter_form = _interpret_chapter_and_schedule(node, trace)
    if chapter_form is not None:
        return chapter_form
    label = node.label()
    if label == "COURSE_ATTRIBUTE":
        words = node.leaves()
        attribute = (
            "ects"
            if "ects" in words
            else "department"
            if "khoa" in words
            else "self_study_hours"
            if "tự" in words
            else "credits"
        )
        return _wh("value", "COURSE_PROPERTY", "CO3085", attribute)
    if label == "COURSE_PARTS":
        if "mấy" in node.leaves():
            part = Variable("part")
            return LogicalForm("COUNT", part, Atom("COURSE_PART", ("CO3085", part)))
        return _wh("part", "COURSE_PART", "CO3085")
    if label == "EXAM_DURATION":
        return _wh("duration", "EXAM_DURATION", node[0].leaves()[0].upper())
    if label == "INSTRUCTOR":
        return _wh("instructor", "INSTRUCTOR_NAME", "CO3085")
    if label in {"LO_DESCRIPTION", "LO_RELATED"}:
        value = node[0].leaves()[0].replace(".", "")
        match = re.search(r"(\d+)\.(\d+)", node[0].leaves()[0])
        lo = f"LO{match.group(1)}.{match.group(2)}" if match else value.upper()
        if label == "LO_DESCRIPTION":
            return _wh("description", "LO_DESCRIPTION", lo)
        chapter, description = Variable("chapter"), Variable("description")
        return LogicalForm(
            "WH",
            chapter,
            Connective(
                "AND",
                (
                    Atom("LO_DESCRIPTION", (lo, description)),
                    Atom("LO_CHAPTER", (lo, chapter)),
                    Atom("CHAPTER", (chapter,)),
                ),
            ),
        )
    if label == "ASSIGNMENT_GOAL":
        return _wh("goal", "ASSIGNMENT_PROPERTY", "BTL01", "goal")
    if label == "ASSIGNMENT_REQUIREMENTS":
        return _wh("requirement", "ASSIGNMENT_REQUIREMENT", "BTL01")
    if label == "ASSIGNMENT_LIST":
        return _wh("assignment", "ASSIGNMENT_INVENTORY", "CO3085")
    if label == "ASSIGNMENT_PART":
        predicate = "PART_REQUIREMENT" if "yêu" in node.leaves() else "PART_TITLE"
        return _wh("value", predicate, _part(node[0]))
    if label == "ASSIGNMENT_TEAM":
        return _wh("team_size", "ASSIGNMENT_PROPERTY", "BTL01", "team_size")
    if label == "ASSIGNMENT_COMPONENT":
        component = _topic(
            next(node.subtrees(lambda item: item.label() == "COMPONENT"))
        ).replace(" ", "_")
        return LogicalForm("YES_NO", None, Atom("HAS_COMPONENT", ("BTL01", component)))
    if label == "ASSIGNMENT_OUTPUTS":
        return _wh("output", "PART_OUTPUT", _part(node[0]))
    if label == "DEADLINE":
        part_nodes = list(node.subtrees(lambda item: item.label() == "PART_REF"))
        if part_nodes:
            return _wh("date", "PART_DEADLINE", _part(part_nodes[0]))
        return _wh("date", "ASSIGNMENT_DEADLINE", "BTL01")
    if label == "RESOURCE_TOPIC":
        subject = next(node.subtrees(lambda item: item.label() == "RESOURCE_SUBJECT"))
        topic = _topic(subject).replace(" ", "_")
        resource, title = Variable("resource"), Variable("title")
        return LogicalForm(
            "WH",
            title,
            Connective(
                "AND",
                (
                    Atom("RESOURCE_TOPIC", (resource, topic)),
                    Atom("RESOURCE_TITLE", (resource, title)),
                ),
            ),
        )
    if label == "RESOURCE_CHAPTER":
        chapter_node = next(
            node.subtrees(lambda item: item.label() in {"CHAPTER_REF", "PART_REF"})
        )
        chapter = (
            Reference("chapter")
            if chapter_node.label() == "PART_REF"
            else _chapter(chapter_node)
        )
        topic, resource, title = (
            Variable("topic"),
            Variable("resource"),
            Variable("title"),
        )
        return LogicalForm(
            "WH",
            title,
            Connective(
                "AND",
                (
                    Atom("HAS_TOPIC", (chapter, topic)),
                    Atom("RESOURCE_TOPIC", (resource, topic)),
                    Atom("RESOURCE_TITLE", (resource, title)),
                ),
            ),
        )
    if label == "REGULATION":
        subject = " ".join(
            next(node.subtrees(lambda item: item.label() == "RULE_SUBJECT")).leaves()
        )
        key = {
            "sử dụng ai": "AI_USAGE",
            "ai": "AI_USAGE",
            "source code": "SOURCE_CODE",
            "llm/rag": "LLM_RAG",
            "thư viện ngoài": "EXTERNAL_LIBRARIES",
        }[subject]
        return _wh("rule", "RULE_TEXT", key)
    if label == "SYSTEM_NOT_FOUND_RULE":
        return _wh("rule", "RULE_TEXT", "OUT_OF_SCOPE")
    if label == "PERMISSION":
        text = " ".join(node.leaves())
        key = (
            "EXTERNAL_LIBRARIES"
            if "thư viện" in text
            else "ASSIGNMENT_SHARING"
            if "chia sẻ" in text
            else "AI_USAGE"
            if "công cụ ai" in text
            else "LLM_RAG"
        )
        return LogicalForm("YES_NO", None, Atom("PERMITTED", (key,)))
    if label == "CHAPTER_ELLIPSIS":
        return LogicalForm(
            "ELLIPSIS",
            None,
            Atom("SHIFT_CHAPTER", (1 if "sau" in node.leaves() else -1,)),
        )
    raise SemanticError(f"Chưa hỗ trợ cấu trúc {label}.")


def render_expression(expr) -> str:
    if isinstance(expr, Connective):
        return (
            "("
            + f" {expr.operator} ".join(render_expression(c) for c in expr.children)
            + ")"
        )

    def render_arg(arg):
        if isinstance(arg, Variable):
            return "?" + arg.name
        if isinstance(arg, Reference):
            return f"REF({arg.kind})"
        return str(arg)

    return f"{expr.predicate}({', '.join(render_arg(arg) for arg in expr.args)})"


def render_logical_form(form: LogicalForm) -> str:
    if form.restriction is not None:
        result = f" -> ?{form.variable.name}" if form.variable else ""
        return (
            f"{form.query_kind} ?{form.scope_variable.name}: "
            f"{render_expression(form.restriction)}; "
            f"{render_expression(form.expression)}{result}"
        )
    prefix = (
        f"{form.query_kind} ?{form.variable.name}" if form.variable else form.query_kind
    )
    return f"{prefix}: {render_expression(form.expression)}"
