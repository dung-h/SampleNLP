"""Generate sentences from the same CFG used by the parser."""

from collections import deque
from nltk.parse.generate import generate

from .syntax import Parser


LEXICAL_EXAMPLES = {"__number__": "3", "__part__": "i", "__lo__": "l.o.2.5"}


def generate_sentences(limit: int = 500) -> list[str]:
    if not 1 <= limit <= 10000:
        raise ValueError("Số lượng câu phải từ 1 đến 10.000.")
    parser = Parser()
    # Visit each start production round-robin rather than exhausting the first
    # question family before reaching later families.
    start_rules = parser.grammar.productions(lhs=parser.grammar.start())
    streams = deque(
        iter(generate(parser.grammar, start=rule.rhs()[0], depth=14))
        for rule in start_rules
    )
    result, seen = [], set()
    while streams and len(result) < limit:
        stream = streams.popleft()
        try:
            tokens = next(stream)
        except StopIteration:
            continue
        streams.append(stream)
        sentence = (
            " ".join(LEXICAL_EXAMPLES.get(token, token) for token in tokens) + "?"
        )
        if sentence not in seen:
            parser.parse(sentence)
            seen.add(sentence)
            result.append(sentence)
    return result
