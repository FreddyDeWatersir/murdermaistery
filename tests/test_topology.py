"""Tests for the topology library.

What is being tested is not that the briefs are well written, which is not
testable, but that a shape *demands* something: that asking for a mutual alibi
and getting an ordinary false claim is caught rather than passed. A library of
shapes that all accept the same case is a library of names (D-067).
"""

import pytest

from mystery.models import Character, Constraint, FalseClaim, Mystery, Place, Secret, Slot
from mystery.topology import DEFAULT, LIBRARY, assess, catalogue, get

PLACES = [Place(id=p, name=p.title()) for p in ("hall", "study", "cellar")]
SLOTS = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)]


def _case(placements, claims=(), confessor=None) -> Mystery:
    return Mystery(
        title="Test",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "a", "b")],
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        constraints=[
            Constraint(id="murder", people=["k", "v"], exclusive=True, place="cellar", slot="s1")
        ],
        secrets=[Secret(id="why", holder="k", about="v", summary="he knew", is_motive=True)],
        false_claims=list(claims),
        false_confessor=confessor,
    )


APART = {
    "k": {"s0": "hall", "s1": "cellar", "s2": "hall"},
    "v": {"s0": "hall", "s1": "cellar", "s2": "cellar"},
    "a": {"s0": "hall", "s1": "study", "s2": "hall"},
    "b": {"s0": "hall", "s1": "hall", "s2": "hall"},
}


def test_every_shape_has_a_brief_and_a_blurb() -> None:
    for topology in LIBRARY.values():
        assert topology.brief.strip(), topology.id
        assert topology.blurb.strip(), topology.id
        assert topology.id in catalogue()


def test_the_default_is_in_the_library() -> None:
    assert get(DEFAULT).id == DEFAULT


def test_an_unknown_shape_says_what_the_known_ones_are() -> None:
    with pytest.raises(KeyError, match="mutual_alibi"):
        get("the_butler_did_it")


def test_the_general_advisories_run_whatever_the_shape() -> None:
    plain = _case(APART, [FalseClaim(character="k", place="hall", slot="s1")])

    assert {a.check for a in assess(plain, "mutual_alibi")} & {"A1", "A3", "A10"}


# --- mutual alibi -----------------------------------------------------------


def test_t1_fires_when_nobody_actually_vouches_for_the_killer() -> None:
    """An ordinary false claim wearing the name of a mutual alibi. No general
    advisory would notice, because none of them knows what was asked for."""
    plain = _case(APART, [FalseClaim(character="k", place="hall", slot="s1")])

    assert "T1" in {a.check for a in assess(plain, "mutual_alibi")}


def test_t1_is_quiet_when_somebody_tells_the_same_story() -> None:
    vouched = _case(
        APART,
        [
            FalseClaim(character="k", place="hall", slot="s1"),
            FalseClaim(character="a", place="hall", slot="s1", covers="why"),
        ],
    )

    assert "T1" not in {a.check for a in assess(vouched, "mutual_alibi")}


def test_t2_fires_when_the_two_stories_hold_each_other_up() -> None:
    """The corroborator has to be catchable from their own side, or the alibi
    is a closed loop and the player has no way in."""
    alone = {
        **APART,
        "a": {"s0": "hall", "s1": "study", "s2": "hall"},
        "b": {"s0": "hall", "s1": "cellar", "s2": "hall"},
    }
    sealed = _case(
        alone,
        [
            FalseClaim(character="k", place="hall", slot="s1"),
            FalseClaim(character="a", place="hall", slot="s1", covers="why"),
        ],
    )

    assert "T2" in {a.check for a in assess(sealed, "mutual_alibi")}


def test_t2_is_quiet_when_a_third_person_can_place_the_corroborator() -> None:
    seen = {**APART, "b": {"s0": "hall", "s1": "study", "s2": "hall"}}
    catchable = _case(
        seen,
        [
            FalseClaim(character="k", place="hall", slot="s1"),
            FalseClaim(character="a", place="hall", slot="s1", covers="why"),
        ],
    )

    assert "T2" not in {a.check for a in assess(catchable, "mutual_alibi")}


# --- false confession -------------------------------------------------------


def test_t3_fires_when_nobody_confesses() -> None:
    plain = _case(APART, [FalseClaim(character="k", place="hall", slot="s1")])

    assert "T3" in {a.check for a in assess(plain, "false_confession")}


def test_t3_fires_when_the_killer_is_the_one_confessing() -> None:
    ended = _case(APART, [FalseClaim(character="k", place="hall", slot="s1")], confessor="k")

    assert "T3" in {a.check for a in assess(ended, "false_confession")}


def test_t4_fires_when_the_confession_cannot_be_disproved() -> None:
    """A confession the player cannot check is a coin flip between two people
    who both say they did it."""
    unseen = {**APART, "a": {"s0": "hall", "s1": "study", "s2": "hall"},
              "b": {"s0": "hall", "s1": "hall", "s2": "hall"}}
    unverifiable = _case(
        unseen, [FalseClaim(character="k", place="hall", slot="s1")], confessor="a"
    )

    assert "T4" in {a.check for a in assess(unverifiable, "false_confession")}


def test_t4_is_quiet_when_somebody_was_with_the_confessor() -> None:
    together = {**APART, "a": {"s0": "hall", "s1": "study", "s2": "hall"},
                "b": {"s0": "hall", "s1": "study", "s2": "hall"}}
    checkable = _case(
        together, [FalseClaim(character="k", place="hall", slot="s1")], confessor="a"
    )

    assert "T4" not in {a.check for a in assess(checkable, "false_confession")}


def test_the_confessor_is_told_to_confess_and_nobody_else_is() -> None:
    from mystery.agent import build_brief, render_system
    from mystery.knowledge import derive

    case = _case(APART, [FalseClaim(character="k", place="hall", slot="s1")], confessor="a")
    knowledge = derive(case)

    assert "you killed them" in render_system(build_brief(case, knowledge, "a"))
    assert "you killed them" not in render_system(build_brief(case, knowledge, "b"))


# The library, and how a shape gets picked (D-103)


def test_every_shape_has_at_least_one_check_of_its_own() -> None:
    """A shape with no checks is a paragraph, and the model will drift back to
    the plain shape while reporting that it did what was asked."""
    from mystery.topology import DEFAULT, LIBRARY

    for shape in LIBRARY.values():
        if shape.id == DEFAULT:
            continue  # the plain shape is what every general advisory assumes
        assert shape.checks, f"{shape.id} has nothing that would notice it drifted"


def test_the_shape_comes_from_the_seed() -> None:
    """Reproducible, not fixed: a seed reproduces the whole case rather than
    most of it."""
    from mystery.topology import LIBRARY, drawn

    assert drawn(483102) == drawn(483102)
    assert drawn(0) in LIBRARY
    assert len({drawn(n) for n in range(40)}) == len(LIBRARY), (
        "every shape should be reachable by some seed"
    )


def test_the_mapping_is_stable_when_a_shape_is_added() -> None:
    """Sorted rather than insertion-ordered, so adding a shape in the middle of
    the list does not silently repoint every existing seed."""
    from mystery.topology import LIBRARY, drawn

    assert drawn(2) == sorted(LIBRARY)[2 % len(LIBRARY)]


def test_the_command_line_reaches_the_draw(monkeypatch, tmp_path) -> None:
    """The shape is dealt by the seed, and for months nothing dealt it (D-154).

    `_draw` asked `if args.topology is None`, and the parser handed it
    `default=DEFAULT`, so the branch was never true and every case ever
    generated from the command line was the plain shape. Thirty drafts in the
    corpus, twenty-nine with the same three-liar structure, and the uniform
    draw over seven shapes never happened once.

    The two tests above prove `drawn` works. Neither of them could catch this,
    because the thing that was broken was not the function, it was the wire.
    This one runs the program and looks at what the generator was actually
    asked for, which is the only place the truth was visible.
    """
    import mystery.web as web
    from mystery.example import OPENING_NIGHT
    from mystery.library import FileShelf
    from mystery.topology import drawn

    asked: list[str] = []

    def spy(request, **kwargs):
        asked.append(request.topology)
        return Mystery.model_validate(OPENING_NIGHT)

    monkeypatch.setattr(web, "pick_shelf", lambda: FileShelf(tmp_path))
    monkeypatch.setattr(web, "generate", spy)
    monkeypatch.setattr(web, "_serve", lambda *a, **kw: 0)

    for seed in range(14):
        web.main(["--dry-run", "--seed", str(seed)])

    assert asked == [drawn(seed) for seed in range(14)]
    assert len(set(asked)) > 1, "every seed asked for the same shape"

    asked.clear()
    web.main(["--dry-run", "--seed", "0", "--topology", "the_conspiracy"])
    assert asked == ["the_conspiracy"], "an explicit shape must still win"


def test_unplayed_deals_only_shapes_not_on_the_shelf() -> None:
    """Coverage, not randomness (D-155). Uniform draws need 18.2 cases to show
    all seven shapes; dealing without replacement needs seven."""
    from mystery.topology import LIBRARY, unplayed

    seen = {"the_lie", "the_frame"}
    for seed in range(60):
        assert unplayed(seen, seed) not in seen
        assert unplayed(seen, seed) in LIBRARY


def test_unplayed_reaches_every_remaining_shape() -> None:
    """A deck that only ever deals the alphabetically first card left is a deck
    that deals one card."""
    from mystery.topology import LIBRARY, unplayed

    seen = {"the_lie"}
    assert {unplayed(seen, n) for n in range(40)} == set(LIBRARY) - seen


def test_unplayed_falls_back_once_they_have_all_been_played() -> None:
    """No special case at the call site, and no empty-sequence crash: when the
    shelf holds all seven this is a uniform draw, which is correct then."""
    from mystery.topology import LIBRARY, drawn, unplayed

    assert unplayed(set(LIBRARY), 483102) == drawn(483102)


def test_unplayed_with_an_empty_shelf_is_the_ordinary_draw() -> None:
    """The first case somebody ever generates must not be a different shape
    depending on which flag they typed."""
    from mystery.topology import drawn, unplayed

    assert [unplayed((), n) for n in range(14)] == [drawn(n) for n in range(14)]


def test_the_command_line_deals_an_unplayed_shape(monkeypatch, tmp_path) -> None:
    """The wire again, and for the same reason as D-154: a draw nothing calls
    is a draw that does not happen."""
    import mystery.web as web
    from mystery.example import OPENING_NIGHT
    from mystery.library import FileShelf
    from mystery.models import Mystery

    shelf = FileShelf(tmp_path)
    example = Mystery.model_validate(OPENING_NIGHT)
    shelf.save(example, "an opening night", "the_lie", 1)
    shelf.save(example, "an opening night", "the_frame", 2)

    asked: list[str] = []

    def spy(request, **kwargs):
        asked.append(request.topology)
        return example

    monkeypatch.setattr(web, "pick_shelf", lambda: shelf)
    monkeypatch.setattr(web, "generate", spy)
    monkeypatch.setattr(web, "_serve", lambda *a, **kw: 0)

    for seed in range(12):
        web.main(["--dry-run", "--seed", str(seed), "--topology", "unplayed"])

    assert asked, "nothing was generated"
    assert not {"the_lie", "the_frame"} & set(asked), "dealt a shape already on the shelf"
