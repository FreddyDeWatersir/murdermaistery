"""Validator rules for mystery ground truth.

A rule is a function taking a Mystery and returning a list of Violations, empty
if it is satisfied. `validate` runs every rule in RULES and collects the result.

Violation and ValidationResult are dataclasses rather than Pydantic models
because Pydantic's job is parsing and checking untrusted input, and these are
objects we construct ourselves from data we already trust. Reach for Pydantic at
the boundary, plain dataclasses inside it.
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


def check_events_match_timeline(mystery: Mystery) -> list[Violation]:
    """V1: every participant in an event must be placed in that event's place,
    in that event's slot.

    Events are what the story requires to happen. Placements are where the
    timeline actually puts people. This rule checks that the second satisfies
    the first, which is the acceptance test on the solver's output as much as it
    is a check on hand-written ground truth.

    One Violation per participant who is somewhere else, so a single badly
    placed event reports every person it disagrees about rather than only the
    first.
    """
    violations: list[Violation] = []

    for event in mystery.events:
        for person in event.participants:
            actual_place = mystery.placements.get(person, {}).get(event.slot)

            if actual_place != event.place:
                violations.append(
                    Violation(
                        rule="V1",
                        message=(
                            f"Event {event.id!r} has {person!r} in {event.place!r} "
                            f"at {event.slot!r}, but the timeline places them "
                            f"in {actual_place!r}"
                        ),
                    )
                )

    return violations


RULES = [
    check_events_match_timeline,
]


def validate(mystery: Mystery) -> ValidationResult:
    violations = [v for rule in RULES for v in rule(mystery)]
    return ValidationResult(violations=violations)
