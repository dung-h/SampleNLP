"""CFG parsing; the only dynamic lexical class is an integer token."""

from itertools import islice
from pathlib import Path
import re
import unicodedata

from nltk import CFG, ChartParser
from nltk.tree import Tree


class ParseError(ValueError):
    pass


class Parser:
    def __init__(self):
        grammar_path = Path(__file__).with_name("grammar.cfg")
        self.grammar = CFG.fromstring(grammar_path.read_text(encoding="utf-8"))
        self.parser = ChartParser(self.grammar)

    def parse(self, sentence: str) -> Tree:
        if not isinstance(sentence, str):
            raise ParseError("Câu hỏi phải là văn bản.")
        text = unicodedata.normalize("NFC", sentence).strip().casefold()
        if text.endswith("?"):
            text = text[:-1].rstrip()
        words = text.split()
        if not words:
            raise ParseError("Câu hỏi rỗng.")

        def lexical_token(word):
            if word.isascii() and word.isdecimal():
                return "__number__"
            if word in {"i", "ii", "iii", "iv"}:
                return "__part__"
            if re.fullmatch(r"l\.?o\.?\d+(?:\.\d+)?", word):
                return "__lo__"
            return word

        tokens = [lexical_token(word) for word in words]
        try:
            parses = list(islice(self.parser.parse(tokens), 2))
        except ValueError as exc:  # Words outside the finite prototype lexicon.
            raise ParseError("Câu hỏi có từ ngoài phạm vi văn phạm.") from exc
        if not parses:
            raise ParseError("Câu hỏi không thuộc văn phạm thử nghiệm.")
        if len(parses) > 1:
            raise ParseError("Câu hỏi có nhiều cách phân tích; chưa tự chọn.")
        tree = parses[0]
        for position, word in zip(tree.treepositions("leaves"), words):
            tree[position] = word
        return tree
