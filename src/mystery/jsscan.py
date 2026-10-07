"""Where the string literals are in a piece of JavaScript (D-209).

Only as much of a lexer as the page needs: comments, quoted strings, template
literals with their `${...}` (which may hold strings and templates of their
own), and regular expressions, told from division by what came before them.
Used to translate the page's words without touching its code.
"""

from __future__ import annotations

import re

_BEFORE_REGEX = set("(,=:[!&|?{};+-*%<>~^")
_KEYWORDS = ("return", "typeof", "case", "in", "of", "new", "delete", "void", "throw")


def string_literals(src: str) -> list[tuple[int, int, str, str]]:
    """(start, end, quote, raw text between the quotes) for every literal."""
    out: list[tuple[int, int, str, str]] = []
    n = len(src)

    def code(i: int, depth: int) -> int:
        last = ""
        while i < n:
            c = src[i]
            if src.startswith("//", i):
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if src.startswith("/*", i):
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "'\"":
                j = i + 1
                while j < n and src[j] != c:
                    j += 2 if src[j] == "\\" else 1
                out.append((i, j + 1, c, src[i + 1 : j]))
                i, last = j + 1, '"'
                continue
            if c == "`":
                i, last = template(i + 1), '"'
                continue
            if c == "{" and depth:
                depth += 1
            elif c == "}" and depth:
                depth -= 1
                if depth == 0:
                    return i + 1
            if c == "/":
                word = re.search(r"([A-Za-z_$][\w$]*)\s*$", src[max(0, i - 20) : i])
                if (
                    last == ""
                    or last in _BEFORE_REGEX
                    or (word and word.group(1) in _KEYWORDS and last.isalpha())
                ):
                    j, inside = i + 1, False
                    while j < n and src[j] != "\n":
                        ch = src[j]
                        if ch == "\\":
                            j += 2
                            continue
                        if ch == "[":
                            inside = True
                        elif ch == "]":
                            inside = False
                        elif ch == "/" and not inside:
                            break
                        j += 1
                    j += 1
                    while j < n and src[j].isalpha():
                        j += 1
                    i, last = j, "/"
                    continue
            if not c.isspace():
                last = c
            i += 1
        return i

    def template(i: int) -> int:
        start = i
        while i < n:
            if src[i] == "\\":
                i += 2
                continue
            if src[i] == "`":
                out.append((start - 1, i + 1, "`", src[start:i]))
                return i + 1
            if src.startswith("${", i):
                i = code(i + 2, 1)
                continue
            i += 1
        return i

    code(0, 0)
    return sorted(out)
