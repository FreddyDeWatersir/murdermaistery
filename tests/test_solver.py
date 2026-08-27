"""Tests for the solver.

The solver's contract is stated entirely in terms of the validator: whatever it
returns must pass. That is not circular, it is the point. The constraints are
the specification, the validator checks the specification was met, and the
solver is the thing under test.
"""

from mystery.models import Character, Constraint, Mystery, Place, Slot
from mystery.solver import solve
from mystery.validator import validate

CHARACTERS = [
    Character(id="bram", name="Bram Kessels"),
    Character(id="tomas", name="Tomas Behr"),
    Character(id="nadia", name="Nadia Groot"),
    Character(id="wouter", name="Wouter Damen"),
    Character(id="renske", name="Renske Oud"),
]

PLACES = [
    Place(id="green_room", name="Green Room"),
    Place(id="stage_door", name="Stage Door"),
    Place(id="prop_store", name="Prop Store"),
    Place(id="lighting_box", name="Lighting Box"),
]

SLOTS = [
    Slot(id="s1", label="19:40", index=0),
    Slot(id="s2", label="20:00", index=1),
    Slot(id="s3", label="20:40", index=2),
    Slot(id="s4", label="21:00", index=3),
]

# Roughly the spine of prototype 02, stated as constraints with nothing bound.
OPENING_NIGHT = [
    Constraint(
        id="murder",
        people=["wouter", "bram"],
        exclusive=True,
        description="Wouter kills Bram. Nobody else present.",
    ),
    Constraint(
        id="bram_sacks_tomas",
        people=["bram", "tomas", "nadia"],
        description="Bram tells Tomas he is finished. Nadia is in the room.",
    ),
    Constraint(
        id="renske_searches_files",
        people=["renske"],
        exclusive=True,
        description="Renske goes through Bram's papers, alone.",
    ),
    Constraint(
        id="tomas_no_alibi",
        people=["tomas"],
        exclusive=True,
        description="Tomas is by himself, and knows how it looks.",
    ),
]


def _mystery(constraints: list[Constraint], **overrides) -> Mystery:
    base = {
        "title": "Opening Night",
        "characters": CHARACTERS,
        "places": PLACES,
        "slots": SLOTS,
        "constraints": constraints,
    }
    return Mystery(**(base | overrides))


def test_a_solved_mystery_passes_the_validator() -> None:
    solved = solve(_mystery(OPENING_NIGHT), seed=1)

    assert validate(solved).ok, validate(solved).violations


def test_everyone_is_somewhere_in_every_slot() -> None:
    """The other half of Federico's original rule.

    The dict makes "in two places at once" unrepresentable. Nothing makes the
    grid complete, so the solver has to do it and something has to check.
    """
    solved = solve(_mystery(OPENING_NIGHT), seed=1)

    for character in CHARACTERS:
        for slot in SLOTS:
            assert solved.placements[character.id].get(slot.id) is not None, (
                f"{character.id} has no placement in {slot.id}"
            )


def test_the_murder_room_ends_up_private() -> None:
    solved = solve(_mystery(OPENING_NIGHT), seed=1)
    murder = next(c for c in solved.constraints if c.id == "murder")

    assert murder.is_bound
    assert solved.who_is_in(murder.place, murder.slot) == {"wouter", "bram"}


def test_the_same_seed_gives_the_same_mystery() -> None:
    """Reproducibility is not a nicety here.

    A daily puzzle can be stored as a seed rather than as a document, and a
    solver bug can be reproduced from a failing seed instead of from a
    screenshot.
    """
    first = solve(_mystery(OPENING_NIGHT), seed=7)
    second = solve(_mystery(OPENING_NIGHT), seed=7)

    assert first.placements == second.placements


def _flatten(mystery: Mystery) -> tuple[tuple[str, str, str], ...]:
    """A grid as a sorted tuple of (character, slot, place), so grids compare."""
    return tuple(
        sorted(
            (character, slot, place)
            for character, by_slot in mystery.placements.items()
            for slot, place in by_slot.items()
        )
    )


def test_different_seeds_give_different_timelines() -> None:
    grids = {_flatten(solve(_mystery(OPENING_NIGHT), seed=s)) for s in range(6)}

    assert len(grids) > 1, "every seed produced the same grid"


def test_a_pre_bound_constraint_is_left_where_it_was() -> None:
    """Some constraints arrive already placed, for instance when a human has
    pinned the murder to a specific moment. The solver works around them."""
    pinned = [
        c.model_copy(update={"place": "prop_store", "slot": "s4"})
        if c.id == "murder"
        else c
        for c in OPENING_NIGHT
    ]

    solved = solve(_mystery(pinned), seed=3)
    murder = next(c for c in solved.constraints if c.id == "murder")

    assert (murder.place, murder.slot) == ("prop_store", "s4")
    assert validate(solved).ok, validate(solved).violations


def test_an_impossible_set_leaves_a_constraint_unbound_rather_than_crashing() -> None:
    """One room, one slot, two exclusive constraints with disjoint casts.

    There is exactly one cell and two things that each need it to themselves.
    The solver must not raise, must not silently drop the constraint, and must
    leave it unbound so V3 names it.

    V2 fires as well, and that is correct rather than a bug. With nowhere legal
    left to stand, the free-fill pass puts the second character into the cell the
    first has claimed. The alternative is leaving a hole in the grid, which is a
    quieter lie than an honest exclusivity violation, at least until V0 exists to
    catch holes. An unsatisfiable constraint set produces a broken mystery and
    the report should say so more than once.
    """
    impossible = _mystery(
        [
            Constraint(id="a_alone", people=["bram"], exclusive=True),
            Constraint(id="b_alone", people=["tomas"], exclusive=True),
        ],
        characters=[CHARACTERS[0], CHARACTERS[1]],
        places=[PLACES[0]],
        slots=[SLOTS[0]],
    )

    solved = solve(impossible, seed=1)
    result = validate(solved)

    assert not result.ok
    assert "V3" in result.failed_rules
    assert len([c for c in solved.constraints if not c.is_bound]) == 1
    assert len(solved.constraints) == 2, "the unplaceable constraint was dropped"
