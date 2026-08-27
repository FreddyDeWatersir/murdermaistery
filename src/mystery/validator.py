"""Validator rules for mystery ground truth.

A rule is a function taking a Mystery and returning a list of Violations, empty
if it is satisfied. `validate` runs every rule in RULES and collects the result.

Violation and ValidationResult are dataclasses rather than Pydantic models
because Pydantic's job is parsing and checking untrusted input, and these are
objects we construct ourselves from data we already trust. Reach for Pydantic at
the boundary, plain dataclasses inside it.

Per D-023 every rule states who it is protecting against: the language model,
our own solver, or a file someone edited by hand.
"""

from dataclasses import dataclass, field

from mystery.models import Mystery


@dataclass(frozen=True)
class Violation:
    rule: str
    message: str


@dataclass
class ValidationResult:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    @property
    def failed_rules(self) -> set[str]:
        return {v.rule for v in self.violations}


def check_constraints_match_timeline(mystery: Mystery) -> list[Violation]:
    """V1: everyone named in a bound constraint must be placed in that
    constraint's place, in that constraint's slot.

    Guards: the solver. Constraints are what the story asked for, placements are
    what the solver produced, and this is the acceptance test that the second
    satisfies the first.

    Unbound constraints are skipped. Whether they should exist at all in a
    finished mystery is V3's business, not this rule's. One rule, one claim.

    One Violation per person who is somewhere else, so a single misplaced
    constraint reports everyone it disagrees about rather than only the first.
    """
    violations: list[Violation] = []

    for constraint in mystery.constraints:
        if not constraint.is_bound:
            continue

        for person in constraint.people:
            actual_place = mystery.placements.get(person, {}).get(constraint.slot)

            if actual_place != constraint.place:
                violations.append(
                    Violation(
                        rule="V1",
                        message=(
                            f"Constraint {constraint.id!r} has {person!r} in "
                            f"{constraint.place!r} at {constraint.slot!r}, but the "
                            f"timeline places them in {actual_place!r}"
                        ),
                    )
                )

    return violations


def check_exclusive_constraints_are_private(mystery: Mystery) -> list[Violation]:
    """V2: a constraint marked exclusive must have nobody present beyond the
    people it names.

    Guards: the solver. "Alone together" is behind every tryst, every
    unwitnessed confrontation, and the murder itself. A solver that satisfies
    the named people but lets a fourth person stand in the room has quietly
    destroyed the case.

    One Violation per intruder.
    """
    violations: list[Violation] = []

    for constraint in mystery.constraints:
        if not (constraint.exclusive and constraint.is_bound):
            continue

        present = mystery.who_is_in(constraint.place, constraint.slot)
        intruders = present - set(constraint.people)

        for intruder in sorted(intruders):
            violations.append(
                Violation(
                    rule="V2",
                    message=(
                        f"Constraint {constraint.id!r} is exclusive to "
                        f"{sorted(constraint.people)}, but the timeline also places "
                        f"{intruder!r} in {constraint.place!r} at {constraint.slot!r}"
                    ),
                )
            )

    return violations


def check_every_constraint_was_placed(mystery: Mystery) -> list[Violation]:
    """V3: in a solved mystery, no constraint may still be unbound.

    Guards: the solver. An unbound constraint is the solver saying, silently,
    that it could not find anywhere to put this. That must be loud, because the
    correct response is to relax or regenerate that one constraint rather than
    discard the whole mystery (D-022).
    """
    return [
        Violation(
            rule="V3",
            message=(
                f"Constraint {constraint.id!r} was never placed: "
                f"place={constraint.place!r}, slot={constraint.slot!r}"
            ),
        )
        for constraint in mystery.constraints
        if not constraint.is_bound
    ]


RULES = [
    check_constraints_match_timeline,
    check_exclusive_constraints_are_private,
    check_every_constraint_was_placed,
]


def validate(mystery: Mystery) -> ValidationResult:
    violations = [v for rule in RULES for v in rule(mystery)]
    return ValidationResult(violations=violations)
