"""Tests for the shelf of saved cases.

The distinction being protected here is the one that made the module necessary
(D-073). The generation cache is keyed by a hash of the request and the prompt,
so it stops paying twice while a prompt is being developed and loses everything
the moment the prompt changes. A saved case has to survive exactly that.
"""

from mystery.example import OPENING_NIGHT
from mystery.library import catalogue, entries, load, save, slug
from mystery.models import Mystery
from mystery.web import _existing

CASE = Mystery.model_validate(OPENING_NIGHT)


def test_a_saved_case_comes_back_the_same(tmp_path) -> None:
    kept = save(CASE, "a theatre", "the_lie", 3, folder=tmp_path)
    back = load(kept.id, folder=tmp_path)

    assert back.mystery.model_dump() == CASE.model_dump()
    assert (back.setting, back.topology, back.seed) == ("a theatre", "the_lie", 3)


def test_a_case_is_named_after_itself_not_hashed(tmp_path) -> None:
    """The whole point. `a3f9c2e1.json` is not something anybody comes back to.

    Four random characters on the end, so no writer has to ask whether a name is
    free (D-081), and the readable part is still the part you type.
    """
    kept = save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)

    assert kept.id.startswith("opening-night-")
    assert load("opening-night", folder=tmp_path).id == kept.id, "a prefix is enough"


def test_two_cases_with_one_title_both_survive(tmp_path) -> None:
    first = save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)
    second = save(CASE, "a theatre", "mutual_alibi", 1, folder=tmp_path)

    assert first.id != second.id
    assert len(entries(tmp_path)) == 2


def test_an_ambiguous_prefix_is_refused_rather_than_guessed(tmp_path) -> None:
    save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)
    save(CASE, "a theatre", "the_lie", 1, folder=tmp_path)

    try:
        load("opening-night", folder=tmp_path)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("two cases match that prefix, so it means nothing")


def test_a_listing_opens_nothing(tmp_path) -> None:
    """The reason the shelf was split. Everything here comes from the names."""
    from mystery.library import cards

    save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)
    save(CASE, "a theatre", "the_lie", 1, folder=tmp_path)
    for path in tmp_path.glob("*.json"):
        path.write_text("{ not json", encoding="utf-8")

    assert len(cards(tmp_path)) == 2, "a listing must not need to parse anything"


def test_slugs_survive_a_title_with_nothing_usable_in_it() -> None:
    assert slug("!!!") == "untitled"
    assert slug("The Vermeer Forgery") == "the-vermeer-forgery"


def test_asking_for_a_case_that_is_not_there_says_what_is(tmp_path) -> None:
    save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)

    try:
        load("the-butler", folder=tmp_path)
    except FileNotFoundError as error:
        assert "opening-night" in str(error)
    else:
        raise AssertionError("a missing case must not load silently")


def test_an_unreadable_file_does_not_hide_the_rest(tmp_path) -> None:
    kept = save(CASE, "a theatre", "the_lie", 0, folder=tmp_path)
    (tmp_path / "broken.json").write_text("{ not json", encoding="utf-8")

    assert [c.id for c in entries(tmp_path)] == [kept.id]


def test_an_empty_shelf_says_so(tmp_path) -> None:
    assert "Nothing saved yet" in catalogue(tmp_path)


def test_art_already_on_disk_belongs_to_the_case(tmp_path) -> None:
    """Paid for once. A saved case brings its faces back without --art."""
    folder = tmp_path / "portraits"
    folder.mkdir()
    (folder / "wouter.png").write_bytes(b"")
    (folder / "ilse.png").write_bytes(b"")

    assert _existing(folder) == {"wouter": "wouter.png", "ilse": "ilse.png"}


def test_no_art_is_not_an_error(tmp_path) -> None:
    assert _existing(tmp_path / "nothing-here") == {}
