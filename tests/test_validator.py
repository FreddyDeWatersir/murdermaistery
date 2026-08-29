"""Tests for validator rules.

Each rule gets at least two tests: one mystery it must reject, and one it must
accept. A rule with only the rejecting test can be satisfied by a validator that
rejects everything, which passes the suite and is useless.
"""

from conftest import CHARACTERS, COHERENT_GRID, MURDER, PLACES, SLOTS

from mystery.models import Constraint, Mystery
from mystery.validator import validate

# V1: bound constraints must agree with the timeline


def test_rejects_constraint_contradicting_the_timeline(prototype_02_bug: Mystery) -> None:
    result = validate(prototype_02_bug)

    assert not result.ok
    assert "V1" in result.failed_rules


def test_names_the_character_the_timeline_disagrees_about(prototype_02_bug: Mystery) -> None:
    result = validate(prototype_02_bug)

    assert len(result.violations) == 1
    assert "tomas" in result.violations[0].message


def test_accepts_a_fragment_whose_constraints_match(coherent_fragment: Mystery) -> None:
    result = validate(coherent_fragment)

    # Passing result.violations as the assertion message means a failure prints
    # what went wrong instead of just "assert False".
    assert result.ok, result.violations


# V2: exclusive constraints must be private


def test_rejects_an_exclusive_constraint_with_a_bystander(
    murder_with_a_bystander: Mystery,
) -> None:
    result = validate(murder_with_a_bystander)

    assert not result.ok
    assert "V2" in result.failed_rules


def test_v2_names_the_intruder_not_the_participants(murder_with_a_bystander: Mystery) -> None:
    result = validate(murder_with_a_bystander)

    assert len(result.violations) == 1
    assert "nadia" in result.violations[0].message


def test_v1_still_passes_when_only_v2_is_broken(murder_with_a_bystander: Mystery) -> None:
    """The bystander does not move the named people, so V1 is satisfied.

    Worth asserting explicitly: it proves the two rules are independent and that
    a V2 failure is not just V1 wearing a different label.
    """
    result = validate(murder_with_a_bystander)

    assert "V1" not in result.failed_rules


def test_accepts_a_murder_with_the_room_to_itself(private_murder: Mystery) -> None:
    result = validate(private_murder)

    assert result.ok, result.violations


# V3: the solver must have placed everything it was given


def test_rejects_a_constraint_the_solver_never_placed(unplaced_constraint: Mystery) -> None:
    result = validate(unplaced_constraint)

    assert not result.ok
    assert "V3" in result.failed_rules


def test_an_unplaced_constraint_does_not_also_trip_v1_or_v2(
    unplaced_constraint: Mystery,
) -> None:
    """An unbound constraint is invisible to the rules that compare against the
    grid, because there is nothing yet to compare.

    This is the assertion that keeps the three rules honest about their own
    scope. Without it, V1 quietly becomes "V1 and also V3".
    """
    result = validate(unplaced_constraint)

    assert result.failed_rules == {"V3"}


def test_accepts_a_mystery_where_every_constraint_was_placed(
    solved_alone_constraint: Mystery,
) -> None:
    result = validate(solved_alone_constraint)

    assert result.ok, result.violations


# V6: the model's constraints must not contradict each other


def test_a_clash_is_rescheduled_rather_than_rejected(coherent_fragment: Mystery) -> None:
    """The failure that broke a real generated case, and the answer to it.

    The model put one character in two rooms at the same moment. Both scenes are
    fine; they simply cannot both happen at 20:40. The solver moves the less
    load-bearing one to a different slot rather than the mystery being thrown
    away (D-033).
    """
    from mystery.models import Constraint
    from mystery.solver import solve

    clashing = coherent_fragment.model_copy(
        update={
            "constraints": [
                *coherent_fragment.constraints,
                Constraint(
                    id="elsewhere",
                    people=["tomas"],
                    place="prop_store",
                    slot="s1",
                    description="Tomas is also, somehow, in the prop store.",
                ),
            ]
        }
    )

    # The clash is real and V6 sees it.
    assert "V6" in validate(clashing).failed_rules

    fixed = solve(clashing, seed=1)

    # And it is gone, with both scenes still in the case.
    assert validate(fixed).ok, validate(fixed).violations
    assert all(c.is_bound for c in fixed.constraints), "a scene was dropped"

    moved = next(c for c in fixed.constraints if c.id == "elsewhere")
    assert (moved.place, moved.slot) != ("prop_store", "s1")


def test_v6_still_reports_a_clash_that_survives_repair(coherent_fragment: Mystery) -> None:
    """V6 has not stopped mattering, it has stopped being fatal at the door."""
    from mystery.models import Constraint

    impossible = coherent_fragment.model_copy(
        update={
            "constraints": [
                *coherent_fragment.constraints,
                Constraint(id="elsewhere", people=["tomas"], place="prop_store", slot="s1"),
            ]
        }
    )

    result = validate(impossible)

    assert "V6" in result.failed_rules
    assert "tomas" in [v.message for v in result.violations if v.rule == "V6"][0]


def test_v6_is_quiet_when_constraints_agree(coherent_fragment: Mystery) -> None:
    assert "V6" not in validate(coherent_fragment).failed_rules


# V7: the victim's story ends when they die


def _murder_case(victim_trail: dict[str, str], extra=None):
    """A three-slot case with the murder in slot s1, for testing what comes after."""
    from mystery.models import Character, Constraint, Mystery, Place, Slot

    slots = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)]
    return Mystery(
        title="After the fact",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "b")],
        places=[Place(id="vault", name="Vault"), Place(id="hall", name="Hall")],
        slots=slots,
        placements={
            "k": {"s0": "hall", "s1": "vault", "s2": "hall"},
            "b": {"s0": "hall", "s1": "hall", "s2": "hall"},
            "v": victim_trail,
        },
        constraints=[
            Constraint(id="murder", people=["k", "v"], exclusive=True, place="vault", slot="s1"),
            *([extra] if extra else []),
        ],
    )


def test_v7_catches_a_victim_who_walks_away_from_their_own_murder() -> None:
    """The real failure. Helena was strangled in the vault at 20:30, and was in
    the main gallery at 20:45."""
    walking = _murder_case({"s0": "hall", "s1": "vault", "s2": "hall"})

    result = validate(walking)

    assert "V7" in result.failed_rules
    assert "Bodies stay put" in [v.message for v in result.violations if v.rule == "V7"][0]


def test_v7_catches_a_scene_scheduled_after_the_victim_died() -> None:
    from mystery.models import Constraint

    posthumous = _murder_case(
        {"s0": "hall", "s1": "vault", "s2": "vault"},
        Constraint(
            id="blackmail", people=["v", "b"], exclusive=True, place="hall", slot="s2"
        ),
    )

    result = validate(posthumous)

    assert "V7" in result.failed_rules
    assert "blackmail" in [v.message for v in result.violations if v.rule == "V7"][0]


def test_v7_is_quiet_when_the_body_stays_where_it_fell() -> None:
    resting = _murder_case({"s0": "hall", "s1": "vault", "s2": "vault"})

    assert "V7" not in validate(resting).failed_rules


def test_the_solver_lays_the_body_to_rest() -> None:
    """Not just detected: fixed. The solver pins the victim after the murder."""
    from mystery.solver import solve

    fixed = solve(_murder_case({"s0": "hall", "s1": "vault", "s2": "hall"}), seed=1)

    assert fixed.placements["v"]["s2"] == "vault"
    assert validate(fixed).ok, validate(fixed).violations


# --- V8, and the list of lies (D-063) ---------------------------------------


def _liar_case(*claims):
    """The same three-slot case, with whatever lies the test wants told."""
    from mystery.models import Character, Constraint, Mystery, Place, Slot

    return Mystery(
        title="Everyone lies",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "b")],
        places=[Place(id="vault", name="Vault"), Place(id="hall", name="Hall")],
        slots=[Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)],
        placements={
            "k": {"s0": "hall", "s1": "vault", "s2": "vault"},
            "b": {"s0": "hall", "s1": "hall", "s2": "hall"},
            "v": {"s0": "hall", "s1": "vault", "s2": "vault"},
        },
        constraints=[
            Constraint(id="murder", people=["k", "v"], exclusive=True, place="vault", slot="s1")
        ],
        false_claims=list(claims),
    )


def test_v8_catches_a_lie_that_is_not_a_lie() -> None:
    """Where the whole mechanic quietly dies: a claim matching the grid.

    Nothing downstream survives it. The alibi analysis reports the story holds,
    the brief hands the character a lie identical to the truth, and the player
    hunts a contradiction that was never there.
    """
    from mystery.models import FalseClaim

    honest = _liar_case(FalseClaim(character="k", place="vault", slot="s1"))

    result = validate(honest)

    assert "V8" in result.failed_rules
    assert "not a lie" in [v.message for v in result.violations if v.rule == "V8"][0]


def test_v8_allows_one_lie_each() -> None:
    from mystery.models import FalseClaim

    two_liars = _liar_case(
        FalseClaim(character="k", place="hall", slot="s1"),
        FalseClaim(character="b", place="vault", slot="s0"),
    )

    assert "V8" not in validate(two_liars).failed_rules


def test_v8_stops_one_person_telling_two_lies() -> None:
    """A liar's sightings are withheld for the moment they lie about (D-042).
    Two lies means two blind moments and a witness who saw nothing all evening.
    """
    from mystery.models import FalseClaim

    overworked = _liar_case(
        FalseClaim(character="b", place="vault", slot="s0"),
        FalseClaim(character="b", place="vault", slot="s2"),
    )

    result = validate(overworked)

    assert "V8" in result.failed_rules
    assert "more than one lie" in [v.message for v in result.violations if v.rule == "V8"][0]


def test_v4_catches_a_lie_covering_a_secret_that_does_not_exist() -> None:
    from mystery.models import FalseClaim

    dangling = _liar_case(
        FalseClaim(character="b", place="vault", slot="s0", covers="the_affair")
    )

    result = validate(dangling)

    assert "V4" in result.failed_rules
    assert "the_affair" in [v.message for v in result.violations if v.rule == "V4"][0]


def test_the_killers_lie_is_the_one_the_case_turns_on() -> None:
    """Three lies in the list, and everything that says "the lie" means one."""
    from mystery.models import FalseClaim

    case = _liar_case(
        FalseClaim(character="b", place="vault", slot="s0"),
        FalseClaim(character="k", place="hall", slot="s1"),
    )

    assert case.false_claim is not None
    assert case.false_claim.character == "k"
    assert case.lie_by("b").slot == "s0"
    assert case.lie_by("v") is None


# --- which scene is the murder (D-071) --------------------------------------


def _two_scenes(order, murder_id=None):
    """The killer and the victim alone twice: the threat, then the killing."""
    from mystery.models import Character, Constraint, Mystery, Place, Slot

    threat = Constraint(
        id="threat", people=["k", "v"], exclusive=True, place="hall", slot="s0"
    )
    killing = Constraint(
        id="the_end", people=["k", "v"], exclusive=True, place="vault", slot="s2"
    )
    scenes = [threat, killing] if order == "threat first" else [killing, threat]

    return Mystery(
        title="Twice alone",
        killer="k",
        victim="v",
        murder=murder_id,
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "b")],
        places=[Place(id="vault", name="Vault"), Place(id="hall", name="Hall")],
        slots=[Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)],
        placements={
            "k": {"s0": "hall", "s1": "hall", "s2": "vault"},
            "v": {"s0": "hall", "s1": "hall", "s2": "vault"},
            "b": {"s0": "vault", "s1": "hall", "s2": "hall"},
        },
        constraints=scenes,
    )


def test_the_murder_is_the_last_time_they_were_alone_not_the_first() -> None:
    """The bug that broke two real cases in a row.

    Every module looked for "a constraint with the killer and the victim in it"
    and took the first in list order. The prompt asks for an earlier private
    confrontation, so which one came first was down to the model's typing order,
    and half the time the threat was treated as the killing.
    """
    for order in ("threat first", "killing first"):
        case = _two_scenes(order)
        assert case.murder_scene.id == "the_end", order
        assert case.murder_slot == "s2", order


def test_an_explicit_murder_id_beats_the_guess() -> None:
    """A model that tells us outranks us working it out."""
    unusual = _two_scenes("threat first", murder_id="threat")

    assert unusual.murder_scene.id == "threat"


def test_v4_catches_a_murder_that_names_no_constraint() -> None:
    from mystery.validator import validate

    assert "V4" in validate(_two_scenes("threat first", murder_id="the_stabbing")).failed_rules


def test_the_victim_may_meet_people_before_the_murder() -> None:
    """V7 fired on every legitimate pre-murder scene while the confrontation
    was being mistaken for the killing."""
    from mystery.validator import validate

    for order in ("threat first", "killing first"):
        assert "V7" not in validate(_two_scenes(order)).failed_rules, order


# V9: one room, one moment, one private scene


def _scenes(*constraints: Constraint) -> Mystery:
    return Mystery(
        title="collision",
        characters=CHARACTERS,
        places=PLACES,
        slots=SLOTS,
        placements=COHERENT_GRID,
        constraints=list(constraints),
    )


def test_two_private_scenes_cannot_share_a_room_and_a_moment() -> None:
    """From a real generation (D-090).

    A conversation overheard from the corridor, with the listener placed *in*
    the office, because the place had been written "the office and the corridor
    outside it". Both exclusive, one room, one slot. Unsatisfiable, and it
    surfaced as five complaints about a timeline that was never the problem.
    """
    result = validate(
        _scenes(
            MURDER,
            Constraint(
                id="overheard",
                people=["nadia"],
                place="prop_store",
                slot="s2",
                exclusive=True,
            ),
        ),
        phase="proposed",
    )

    assert "V9" in result.failed_rules
    message = next(v.message for v in result.violations if v.rule == "V9")
    assert "murder" in message and "overheard" in message
    assert "overhearing" in message, "the message has to say how to fix it"


def test_the_same_scene_written_twice_is_not_a_collision() -> None:
    """Same room, same moment, same people. Redundant, not contradictory."""
    twice = _scenes(
        MURDER,
        Constraint(
            id="again",
            people=["bram", "wouter"],
            place="prop_store",
            slot="s2",
            exclusive=True,
        ),
    )

    assert "V9" not in validate(twice, phase="proposed").failed_rules


def test_two_scenes_in_one_room_are_fine_if_neither_is_private() -> None:
    """Only `exclusive` promises the room is empty, so only `exclusive` collides."""
    shared = _scenes(
        Constraint(id="a", people=["bram"], place="prop_store", slot="s2"),
        Constraint(id="b", people=["wouter"], place="prop_store", slot="s2"),
    )

    assert "V9" not in validate(shared, phase="proposed").failed_rules


def test_the_drafting_loop_hears_about_collisions_not_only_the_solver() -> None:
    """At the proposed phase the model is handed its own violations back as
    complaints, so it repairs this in the same run for the price of one more
    call rather than costing a whole draft."""
    from mystery.validator import PROPOSED_RULES, check_exclusive_scenes_do_not_collide

    assert check_exclusive_scenes_do_not_collide in PROPOSED_RULES
