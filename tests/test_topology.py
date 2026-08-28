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
