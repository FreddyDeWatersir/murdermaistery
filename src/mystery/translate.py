"""A case in another language, made once (D-208).

A room can be in Italian or French. The case it plays is a copy of an English
case with every word a person reads or hears translated, and every id left
alone, so the solver, the checks and the grid are the same case. The suspects
then speak the language because their knowledge is written in it, and say
"la sala capitolare" the way the plan and the timeline do, instead of each
translating "the chapter house" their own way on the fly.

Two passes. The names first (rooms, hours, objects, what people are, the
title), so that the second pass, everything else, is handed them and uses
the same words. Both passes go through one function, so a test can swap the
model for a dictionary.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

LANGUAGES = {"en": "English", "it": "Italian", "fr": "French"}

# Keys whose string values are ids or codes, never words a person reads.
_CODE = {
    "id",
    "killer",
    "victim",
    "murder",
    "holder",
    "about",
    "known_by",
    "revealed_by",
    "character",
    "place",
    "slot",
    "where",
    "moved_by",
    "belongs_to",
    "finder",
    "constraint",
    "covers",
    "who",
    "stage",
    "people",
    "adjacent",
    "within",
    "placements",
    "false_confessor",
    "built_with",
    "world",
    "killer_position",
    "language",
    "gender",
}
# Translated first, and handed to the second pass as a glossary.
_NAMES = ("places.name", "slots.label", "things.name", "characters.role", "title")

Translator = Callable[[list[str], dict[str, str], str], list[str]]


def _leaves(node: Any, path: tuple[str, ...] = ()) -> list[tuple[tuple, str]]:
    """Every translatable string in a mystery, with where it lives."""
    out: list[tuple[tuple, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _CODE:
                continue
            # A thing's `role` is a dealt card (D-203), not a description.
            if key == "role" and len(path) >= 2 and path[-2] == "things":
                continue
            # People keep their names, in every language.
            if key == "name" and len(path) >= 2 and path[-2] == "characters":
                continue
            out += _leaves(value, (*path, key))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            out += _leaves(value, (*path, i))
    elif isinstance(node, str) and node.strip():
        out.append((path, node))
    return out


def _kind(path: tuple) -> str:
    """ "places.name" for ("places", 3, "name"), for matching `_NAMES`."""
    return ".".join(str(p) for p in path if not isinstance(p, int))


def _put(node: Any, path: tuple, value: str) -> None:
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


def _batches(items: list[str], limit: int = 12_000) -> list[list[int]]:
    groups, current, size = [], [], 0
    for i, text in enumerate(items):
        if current and size + len(text) > limit:
            groups.append(current)
            current, size = [], 0
        current.append(i)
        size += len(text)
    if current:
        groups.append(current)
    return groups


def translate_mystery(mystery: dict[str, Any], lang: str, translate: Translator) -> dict[str, Any]:
    """A deep copy of `mystery` (a dict) with its words in `lang`."""
    out = json.loads(json.dumps(mystery))
    leaves = _leaves(out)
    first = [(p, t) for p, t in leaves if _kind(p) in _NAMES]
    rest = [(p, t) for p, t in leaves if _kind(p) not in _NAMES]

    glossary: dict[str, str] = {}
    for group in _batches([t for _, t in first]):
        said = translate([first[i][1] for i in group], {}, lang)
        for i, text in zip(group, said, strict=True):
            glossary[first[i][1]] = text
            _put(out, first[i][0], text)
    for group in _batches([t for _, t in rest]):
        said = translate([rest[i][1] for i in group], glossary, lang)
        for i, text in zip(group, said, strict=True):
            _put(out, rest[i][0], text)
    out["language"] = lang
    return out


SYSTEM = """You translate a murder mystery game from English into {language}. \
You are given a numbered list of texts from one case: names of rooms and hours, \
what people are, what they say, what they hide. Translate each into natural, \
literary {language} that fits the period and place of the case. Keep every \
person's name exactly as it is. Keep leading and trailing spaces and the \
punctuation at the ends. Never merge, split, drop or reorder items: the answer \
has exactly as many items as the question, in the same order."""


def anthropic_translator(model: str) -> Translator:
    """The real one: one streamed call per batch, a tool so the list comes back
    as a list."""
    import anthropic

    client = anthropic.Anthropic()
    schema = {
        "type": "object",
        "properties": {"texts": {"type": "array", "items": {"type": "string"}}},
        "required": ["texts"],
    }

    def translate(texts: list[str], glossary: dict[str, str], lang: str) -> list[str]:
        language = LANGUAGES[lang]
        terms = "\n".join(f"- {en} → {tr}" for en, tr in glossary.items())
        content = (
            (
                f"Use these translations for names wherever they appear:\n{terms}\n\n"
                if terms
                else ""
            )
            + f"Translate these {len(texts)} texts:\n"
            + json.dumps(texts, ensure_ascii=False, indent=1)
        )
        for _ in range(3):
            with client.messages.stream(
                model=model,
                max_tokens=24000,
                system=SYSTEM.format(language=language),
                messages=[{"role": "user", "content": content}],
                tools=[
                    {
                        "name": "translated",
                        "description": "Return the texts.",
                        "input_schema": schema,
                    }
                ],
                tool_choice={"type": "tool", "name": "translated"},
            ) as live:
                response = live.get_final_message()
            block = next((b for b in response.content if b.type == "tool_use"), None)
            said = (block.input or {}).get("texts", []) if block else []
            if len(said) == len(texts):
                return [str(s) for s in said]
        raise RuntimeError(
            f"the translation kept coming back with the wrong number of items "
            f"({len(said)} for {len(texts)})"
        )

    return translate


def translate_case(
    case_id: str, lang: str, translate: Translator, library: Path, art: Path
) -> Path:
    """Translate a saved case into `lang` and save it beside the original as
    `<id>-<lang>`, with a copy of its pictures. Returns the new file."""
    if lang not in LANGUAGES or lang == "en":
        raise ValueError(
            f"no such language {lang!r}: {', '.join(k for k in LANGUAGES if k != 'en')}"
        )
    source = next(library.glob(f"*__{case_id}.json"), None)
    if source is None:
        raise FileNotFoundError(f"no case {case_id!r} on the shelf")
    saved = json.loads(source.read_text(encoding="utf-8"))
    new_id = f"{saved['id']}-{lang}"
    saved["mystery"] = translate_mystery(saved["mystery"], lang, translate)
    if saved.get("setting"):
        saved["setting"] = translate([saved["setting"]], {}, lang)[0]
    saved["title"] = saved["mystery"].get("title", saved.get("title", ""))
    saved["id"] = new_id
    saved["translated_from"] = case_id
    target = source.with_name(source.name.replace(f"__{case_id}.json", f"__{new_id}.json"))
    target.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
    if (art / case_id).exists() and not (art / new_id).exists():
        shutil.copytree(art / case_id, art / new_id)
    return target
