"""Tests for validator rules.

Each rule gets at least two tests: one mystery it must reject, and one it must
accept. A rule with only the rejecting test can be satisfied by a validator that
rejects everything, which passes the suite and is useless.
"""

from mystery.models import Mystery
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
