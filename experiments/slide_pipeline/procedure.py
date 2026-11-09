"""Interpret a restricted Retrieve/Test query over extensional KB facts."""

from dataclasses import dataclass

from .logic import Atom, Connective, LogicalForm, Reference, Variable

# Explicit semantic vocabulary -> relations in this experiment's KB.
# Other existing predicates retain their names; this is not a generic ontology mapper.
PREDICATE_GROUNDING = {"DISCUSSES": "HAS_TOPIC", "TAUGHT_IN": "SCHEDULED_IN"}


class UnresolvedReference(ValueError):
    pass


@dataclass(frozen=True)
class Procedure:
    operation: str  # RETRIEVE, TEST, COUNT, ITERATE, CHECK_ALL, or FIND_THE
    variable: Variable | None
    expression: Atom | Connective
    scope_variable: Variable | None = None
    restriction: Atom | Connective | None = None


@dataclass(frozen=True)
class Result:
    status: str  # FOUND, NOT_FOUND, or UNKNOWN when evidence is insufficient
    values: list
    sources: list[str]
    reason: str | None = None


def resolve(
    form: LogicalForm,
    chapter: str | None,
    assignment_part: str | None = None,
    previous: LogicalForm | None = None,
    focus: str | None = None,
) -> LogicalForm:
    if form.query_kind == "ELLIPSIS":
        if not chapter or previous is None or not isinstance(previous.expression, Atom):
            raise UnresolvedReference(
                "Chưa có câu hỏi về chương để xác định câu rút gọn."
            )
        if (
            previous.expression.predicate
            not in {
                "HAS_KEYWORD",
                "HAS_TOPIC",
                "DISCUSSES",
                "CHAPTER_SUMMARY",
                "CHAPTER_SUBTOPIC",
            }
            or previous.expression.args[0] != chapter
        ):
            raise UnresolvedReference("Không thể kế thừa nội dung câu hỏi trước.")
        number = int(chapter[2:]) + form.expression.args[0]
        if number < 1:
            raise UnresolvedReference("Không xác định được chương yêu cầu.")
        expression = Atom(
            previous.expression.predicate,
            (f"CH{number:02d}", *previous.expression.args[1:]),
        )
        return LogicalForm(previous.query_kind, previous.variable, expression)

    def visit(expr):
        if isinstance(expr, Connective):
            return Connective(
                expr.operator, tuple(visit(child) for child in expr.children)
            )
        args = []
        for arg in expr.args:
            if isinstance(arg, Reference):
                if arg.kind == "chapter":
                    value = chapter
                elif arg.kind == "assignment_part":
                    value = assignment_part
                elif arg.kind == "pronoun":
                    value = (
                        chapter
                        if focus == "chapter"
                        else assignment_part
                        if focus == "assignment_part"
                        else None
                    )
                else:
                    value = None
                if value is None:
                    raise UnresolvedReference(
                        "Chưa xác định được đối tượng đang được nhắc đến."
                    )
                args.append(value)
            else:
                args.append(arg)
        return Atom(expr.predicate, tuple(args))

    return LogicalForm(
        form.query_kind,
        form.variable,
        visit(form.expression),
        form.scope_variable,
        visit(form.restriction) if form.restriction is not None else None,
    )


def translate(form: LogicalForm) -> Procedure:
    # Domain grounding: LF vocabulary need not be identical to the KB schema.
    def compile_expr(expr):
        if isinstance(expr, Connective):
            return Connective(
                expr.operator, tuple(compile_expr(c) for c in expr.children)
            )
        return Atom(PREDICATE_GROUNDING.get(expr.predicate, expr.predicate), expr.args)

    expression = compile_expr(form.expression)
    restriction = (
        compile_expr(form.restriction) if form.restriction is not None else None
    )
    if form.query_kind in {"WH", "COUNT"} and form.variable is not None:
        return Procedure(
            "RETRIEVE" if form.query_kind == "WH" else "COUNT",
            form.variable,
            expression,
        )
    if form.query_kind == "YES_NO" and form.variable is None:
        return Procedure("TEST", None, expression)
    if (
        form.query_kind in {"EACH", "EVERY", "THE"}
        and form.scope_variable
        and restriction
    ):
        return Procedure(
            {"EACH": "ITERATE", "EVERY": "CHECK_ALL", "THE": "FIND_THE"}[
                form.query_kind
            ],
            form.variable,
            expression,
            form.scope_variable,
            restriction,
        )
    raise ValueError("Logical form không thuộc phạm vi thử nghiệm.")


def _match_atom(atom, rows, facts):
    result = []
    for bindings, sources in rows:
        for fact in facts:
            if fact.predicate != atom.predicate or len(fact.args) != len(atom.args):
                continue
            updated = dict(bindings)
            for term, value in zip(atom.args, fact.args):
                if isinstance(term, Variable):
                    if term.name in updated and updated[term.name] != value:
                        break
                    updated[term.name] = value
                elif term != value:
                    break
            else:
                result.append((updated, sources | {fact.source}))
    return result


def _evaluate(expr, rows, facts):
    if isinstance(expr, Atom):
        return _match_atom(expr, rows, facts)
    if expr.operator == "AND":
        for child in expr.children:
            rows = _evaluate(child, rows, facts)
        return rows
    if expr.operator == "OR":
        return [
            match for child in expr.children for match in _evaluate(child, rows, facts)
        ]
    raise ValueError(f"Toán tử chưa hỗ trợ: {expr.operator}")


def execute(procedure: Procedure, kb) -> Result:
    if procedure.restriction is not None:
        # The restrictor enumerates the known domain, then the body is evaluated
        # with each individual binding. Absence of a fact is not negation.
        domains = _evaluate(procedure.restriction, [({}, set())], kb.facts)
        name = procedure.scope_variable.name
        grouped = {}
        for bindings, sources in domains:
            if name in bindings:
                grouped.setdefault(bindings[name], set()).update(sources)
        if not grouped:
            return Result("UNKNOWN", [], [], "NO_REFERENT")
        if procedure.operation == "FIND_THE" and len(grouped) != 1:
            return Result(
                "UNKNOWN",
                [],
                sorted(set().union(*grouped.values())),
                "AMBIGUOUS_REFERENT",
            )
        values, all_sources = [], set()
        for individual, sources in sorted(grouped.items()):
            all_sources.update(sources)
            matches = _evaluate(
                procedure.expression, [({name: individual}, set(sources))], kb.facts
            )
            if not matches:
                return Result("UNKNOWN", [], sorted(all_sources), "MISSING_BODY")
            for bindings, support in matches:
                all_sources.update(support)
                if (
                    procedure.variable is not None
                    and procedure.variable.name in bindings
                ):
                    value = bindings[procedure.variable.name]
                    values.append(
                        f"{individual}: {value}"
                        if procedure.operation == "ITERATE"
                        else value
                    )
        if procedure.operation == "CHECK_ALL":
            return Result("FOUND", [True], sorted(all_sources))
        return (
            Result("FOUND", sorted(set(values)), sorted(all_sources))
            if values
            else Result("UNKNOWN", [], sorted(all_sources))
        )
    matches = _evaluate(procedure.expression, [({}, set())], kb.facts)
    if not matches:
        if (
            procedure.operation == "TEST"
            and isinstance(procedure.expression, Atom)
            and procedure.expression.predicate == "PERMITTED"
        ):
            negative = Atom("NOT_PERMITTED", procedure.expression.args)
            evidence = _evaluate(negative, [({}, set())], kb.facts)
            if evidence:
                return Result(
                    "FOUND",
                    [False],
                    sorted(set().union(*(source for _, source in evidence))),
                )
        # Missing positive facts do not prove that a natural-language claim is false.
        return Result(
            "UNKNOWN" if procedure.operation == "TEST" else "NOT_FOUND", [], []
        )
    sources = sorted(set().union(*(source for _, source in matches)))
    if procedure.operation == "TEST":
        return Result("FOUND", [True], sources)
    values = sorted(
        {
            binding[procedure.variable.name]
            for binding, _ in matches
            if procedure.variable.name in binding
        }
    )
    if procedure.operation == "COUNT" and values:
        return Result("FOUND", [str(len(values))], sources)
    return Result("FOUND", values, sources) if values else Result("NOT_FOUND", [], [])
