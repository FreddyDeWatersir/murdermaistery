"""Tests for the solver.

The solver's contract is stated entirely in terms of the validator: whatever it
returns must pass. That is not circular, it is the point. The constraints are
the specification, the validator checks the specification was met, and the
solver is the thing under test.
"""

from mystery.example import OPENING_NIGHT as SHIPPED_CASE
from mystery.models import Character, Constraint, Mystery, Place, Slot
from mystery.solver import solve, solve_until_valid
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


def test_the_solver_moves_an_innocents_lie_somewhere_it_can_be_caught() -> None:
    """An unbreakable lie is a wasted character (D-063).

    If nobody was in the room somebody claims, nobody can contradict them, the
    lie never surfaces, and the red herring the case was counting on does not
    fire. The room a liar names carries no story, so it is safe to move.
    """
    from mystery.models import Character, Constraint, FalseClaim, Mystery, Place, Slot
    from mystery.solver import solve

    case = Mystery(
        title="Nobody saw a thing",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "b", "c")],
        places=[Place(id=p, name=p.title()) for p in ("hall", "vault", "attic")],
        slots=[Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)],
        placements={
            "k": {"s0": "hall", "s1": "vault", "s2": "vault"},
            "v": {"s0": "hall", "s1": "vault", "s2": "vault"},
            "b": {"s0": "hall", "s1": "hall", "s2": "hall"},
            # Somebody has to be somewhere else, or there is nowhere for a liar
            # to be caught out and the repair has nothing to work with.
            "c": {"s0": "vault", "s1": "hall", "s2": "hall"},
        },
        constraints=[
            Constraint(id="murder", people=["k", "v"], exclusive=True, place="vault", slot="s1")
        ],
        false_claims=[
            FalseClaim(character="k", place="hall", slot="s1"),
            # The attic was empty all evening, so this one can never be caught.
            FalseClaim(character="b", place="attic", slot="s0", covers="something"),
        ],
    )

    fixed = solve(case, seed=3)
    lie = fixed.lie_by("b")

    assert lie.place != "attic", "an empty room is an unbreakable alibi"
    assert fixed.who_is_in(lie.place, lie.slot) - {"b"}, "somebody has to be able to deny it"
    assert lie.covers == "something", "the repair must not lose why they lied"


# --- the murder room is sealed (D-147) ---------------------------------------


def _with_holes_after_the_murder(case: Mystery) -> Mystery:
    """Everybody's evening after the killing, blanked.

    Which is what the filler is for, and what it used to get wrong: a hole in a
    late slot could be filled with any room in the house, including the one with
    the body in it.
    """
    order = {s.id: s.index for s in case.slots}
    when = order[case.murder_scene.slot]
    return case.model_copy(
        update={
            "placements": {
                who: {slot: place for slot, place in where.items() if order[slot] <= when}
                for who, where in case.placements.items()
            }
        }
    )


def test_nobody_is_ever_filled_into_the_room_with_the_body() -> None:
    """Fifty seeds, because the bug was a random choice among five rooms: one
    seed proves nothing and this one used to fail within the first handful.

    Two real drafts died of this in one evening, at about forty cents each, and
    what the program printed was "try another seed" (D-147)."""
    thin = _with_holes_after_the_murder(Mystery.model_validate(SHIPPED_CASE))

    for seed in range(50):
        broken = [v for v in validate(solve(thin, seed=seed)).violations if v.rule == "V10"]
        assert not broken, f"seed {seed}: {broken[0].message}"


def test_the_victim_is_still_left_where_they_fell() -> None:
    """The seal is for the living. V7 requires the body to stay put, and a seal
    that forgot the exception would move it."""
    case = Mystery.model_validate(SHIPPED_CASE)
    solved = solve(_with_holes_after_the_murder(case), seed=3)
    order = {s.id: s.index for s in solved.slots}
    scene = solved.murder_scene

    after = [s.id for s in solved.slots if order[s.id] > order[scene.slot]]
    assert all(solved.placements[solved.victim][s] == scene.place for s in after)


def test_a_scene_is_never_rehomed_on_top_of_the_body() -> None:
    """The other half. `_room_for` refused to move a scene involving the victim
    to after they were dead, and happily moved anybody else's scene into the
    room the victim was lying in."""
    case = Mystery.model_validate(SHIPPED_CASE)
    loose = case.model_copy(
        update={
            "constraints": [
                c.model_copy(update={"place": None, "slot": None})
                if c.id != case.murder_scene.id
                else c
                for c in case.constraints
            ]
        }
    )

    for seed in range(30):
        solved = solve(loose, seed=seed)
        broken = [v for v in validate(solved).violations if v.rule == "V10"]
        assert not broken, f"seed {seed}: {broken[0].message}"


def test_a_bad_arrangement_is_re_solved_rather_than_re_drafted() -> None:
    """Drafting is the strongest model and about forty cents; solving is
    arithmetic and free. A draft that survives the proposed rules and fails the
    final ones should cost another arrangement, never another draft (D-147)."""
    thin = _with_holes_after_the_murder(Mystery.model_validate(SHIPPED_CASE))
    solved, used, violations = solve_until_valid(thin, seed=0)

    assert not violations
    assert validate(solved).ok
    assert used >= 0


def test_it_says_which_arrangement_worked_so_the_case_can_be_had_again() -> None:
    """Deterministic, or the seed printed to the player is a lie."""
    thin = _with_holes_after_the_murder(Mystery.model_validate(SHIPPED_CASE))
    first, used, _ = solve_until_valid(thin, seed=11)
    again = solve(thin, seed=used)

    assert first.placements == again.placements


def test_giving_up_hands_back_the_reason_rather_than_nothing() -> None:
    """When no arrangement works the violations come back, so the program can
    say what is wrong instead of shrugging."""
    impossible = Mystery.model_validate(SHIPPED_CASE).model_copy(
        update={"characters": [], "placements": {}}
    )
    _, _, violations = solve_until_valid(impossible, seed=0, tries=2)

    assert violations
