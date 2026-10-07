"""A case in another language (D-208): words translated, ids untouched."""

import json

from mystery.example import OPENING_NIGHT
from mystery.models import Mystery


def _upper(texts, glossary, lang):
    return [f"[{lang}]{t}" for t in texts]


def test_words_change_and_ids_do_not() -> None:
    from mystery.translate import translate_mystery

    raw = json.loads(json.dumps(OPENING_NIGHT))
    out = translate_mystery(raw, "it", _upper)
    m, before = Mystery.model_validate(out), Mystery.model_validate(OPENING_NIGHT)

    assert m.language == "it"
    assert [c.id for c in m.characters] == [c.id for c in before.characters]
    assert m.placements == before.placements
    assert [c.name for c in m.characters] == [c.name for c in before.characters]
    assert all(p.name.startswith("[it]") for p in m.places)
    assert all(s.label.startswith("[it]") for s in m.slots)
    assert m.false_claims[0].place == before.false_claims[0].place
    assert m.secrets[0].holder == before.secrets[0].holder


def test_names_go_first_and_are_handed_on_as_a_glossary() -> None:
    from mystery.translate import translate_mystery

    seen = []

    def spy(texts, glossary, lang):
        seen.append(dict(glossary))
        return texts

    translate_mystery(json.loads(json.dumps(OPENING_NIGHT)), "fr", spy)
    assert seen[0] == {} and len(seen) >= 2 and seen[-1]


def test_a_translated_case_is_saved_beside_the_original_with_its_pictures(tmp_path) -> None:
    from mystery.translate import translate_case

    library, art = tmp_path / "cases", tmp_path / "art"
    library.mkdir()
    (art / "opening" / "portraits").mkdir(parents=True)
    (art / "opening" / "portraits" / "x.png").write_bytes(b"png")
    record = {
        "id": "opening",
        "title": "Opening Night",
        "setting": "a theatre",
        "topology": "the_lie",
        "seed": 1,
        "saved": "2026-10-07T00:00:00+00:00",
        "mystery": OPENING_NIGHT,
    }
    (library / "20261007T000000.000__opening.json").write_text(json.dumps(record), "utf-8")

    path = translate_case("opening", "it", _upper, library, art)
    saved = json.loads(path.read_text("utf-8"))
    assert saved["id"] == "opening-it" and saved["translated_from"] == "opening"
    assert saved["setting"] == "[it]a theatre"
    assert (art / "opening-it" / "portraits" / "x.png").exists()


def test_the_suspects_are_told_to_speak_it() -> None:
    from mystery.agent import build_brief, render_person
    from mystery.knowledge import derive

    m = Mystery.model_validate(OPENING_NIGHT).model_copy(update={"language": "it"})
    who = next(c.id for c in m.characters if c.id != m.victim)
    assert "You speak Italian" in render_person(build_brief(m, derive(m), who))
