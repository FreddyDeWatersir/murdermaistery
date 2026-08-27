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
