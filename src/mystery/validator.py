"""Validator rules for mystery ground truth.

A rule is a function taking a Mystery and returning a list of Violations, empty
if it is satisfied.

Rules come in phases, because a mystery passes through two states with different
expectations. A **proposed** mystery has just come back from the model, grid and
all, and may well have small breakages in it: those are the repairer's job, not
grounds for rejection. A **final** mystery has been through the solver and every
rule must hold.

Per D-023 every rule states who it is protecting against: the language model,
our own solver, or a file someone edited by hand.

Violation and ValidationResult are dataclasses rather than Pydantic models
because Pydantic's job is parsing untrusted input, and these are objects we
construct ourselves from data we already trust. Reach for Pydantic at the
boundary, plain dataclasses inside it.
"""

from dataclasses import dataclass, field
from typing import Literal

from mystery.models import Mystery

Phase = Literal["proposed", "final"]


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


def check_references_exist(mystery: Mystery) -> list[Violation]:
    """V4: every id a constraint mentions must exist in the cast, and every place
    and slot it names must exist too.

    Guards: the language model, mostly. A model will cheerfully write a
    constraint about "the butler" for a cast containing "james", or reference a
    conservatory it invented halfway through. This is the first rule in the
    project whose job is to catch generation rather than our own code.
    """
    people = {character.id for character in mystery.characters}
    places = {place.id for place in mystery.places}
    slots = {slot.id for slot in mystery.slots}

    violations: list[Violation] = []

    for constraint in mystery.constraints:
        for person in constraint.people:
            if person not in people:
                violations.append(
                    Violation(
                        rule="V4",
                        message=(
                            f"Constraint {constraint.id!r} names {person!r}, "
                            f"who is not in the cast"
                        ),
                    )
                )

        if constraint.place is not None and constraint.place not in places:
            violations.append(
                Violation(
                    rule="V4",
                    message=(
                        f"Constraint {constraint.id!r} is set in {constraint.place!r}, "
                        f"which is not a place in this mystery"
                    ),
                )
            )

        if constraint.slot is not None and constraint.slot not in slots:
            violations.append(
                Violation(
                    rule="V4",
                    message=(
                        f"Constraint {constraint.id!r} happens at {constraint.slot!r}, "
                        f"which is not a slot in this mystery"
                    ),
                )
            )

    secrets = {secret.id for secret in mystery.secrets}

    if mystery.murder is not None and mystery.murder not in {c.id for c in mystery.constraints}:
        violations.append(
            Violation(
                rule="V4",
                message=(
                    f"The murder is said to be constraint {mystery.murder!r}, which does "
                    f"not exist. `murder` takes the id of one of the constraints"
                ),
            )
        )

    if mystery.false_confessor is not None and mystery.false_confessor not in people:
        violations.append(
            Violation(
                rule="V4",
                message=(
                    f"{mystery.false_confessor!r} is set to confess to the murder and "
                    f"is not in the cast"
                ),
            )
        )

    for claim in mystery.false_claims:
        if claim.character not in people:
            violations.append(
                Violation(
                    rule="V4",
                    message=f"A false claim is told by {claim.character!r}, who is not in the cast",
                )
            )
        if claim.place not in places:
            violations.append(
                Violation(
                    rule="V4",
                    message=(
                        f"{claim.character!r} claims to have been in {claim.place!r}, "
                        f"which is not a place in this mystery"
                    ),
                )
            )
        if claim.slot not in slots:
            violations.append(
                Violation(
                    rule="V4",
                    message=(
                        f"{claim.character!r} tells their lie at {claim.slot!r}, "
                        f"which is not a slot in this mystery"
                    ),
                )
            )
        if claim.covers and claim.covers not in secrets:
            violations.append(
                Violation(
                    rule="V4",
                    message=(
                        f"{claim.character!r} lies to cover secret {claim.covers!r}, "
                        f"which does not exist. `covers` takes the id of a secret"
                    ),
                )
            )

    return violations


def check_false_claims_are_false(mystery: Mystery) -> list[Violation]:
    """V8: a lie has to be a lie, and one person tells at most one.

    Guards: the model, and one piece of our own bookkeeping.

    A claim that matches the grid is not a false claim, and nothing downstream
    survives it: the alibi analysis reports the story holds, the brief hands the
    character a "lie" identical to the truth, and the player is hunting a
    contradiction that does not exist.

    One lie per person because the brief withholds what a liar saw during the
    moment they are lying about (D-042). Two lies from one mouth means two
    withheld moments and a character who saw almost nothing all evening, which
    reads as evasion rather than as a person.
    """
    violations: list[Violation] = []
    told_by: set[str] = set()

    for claim in mystery.false_claims:
        truth = mystery.placements.get(claim.character, {}).get(claim.slot)

        if truth is not None and truth == claim.place:
            violations.append(
                Violation(
                    rule="V8",
                    message=(
                        f"{claim.character!r} claims {claim.place!r} at {claim.slot!r}, "
                        f"which is exactly where the timeline puts them. The lie is not a lie"
                    ),
                )
            )

        if claim.character in told_by:
            violations.append(
                Violation(
                    rule="V8",
                    message=f"{claim.character!r} tells more than one lie about where they were",
                )
            )
        told_by.add(claim.character)

    return violations


def check_constraints_match_timeline(mystery: Mystery) -> list[Violation]:
    """V1: everyone named in a bound constraint must be placed in that
    constraint's place, in that constraint's slot.

    Guards: the solver. Constraints are what the story asked for, placements are
    what the solver produced, and this is the acceptance test that the second
    satisfies the first.

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


def check_constraints_do_not_contradict(mystery: Mystery) -> list[Violation]:
    """V6: no character may be required in two different places in one slot.

    Guards: the language model. Writing eight constraints without a spreadsheet,
    a model will put the same person in the kitchen overhearing an argument and
    on the deck taking a pitch at the same moment. The set is then unsatisfiable
    and no repair exists, so this has to be caught and reported rather than
    handed to the solver, which would otherwise thrash between the two.
    """
    violations: list[Violation] = []
    wanted: dict[tuple[str, str], tuple[str, str]] = {}

    for constraint in mystery.constraints:
        if not constraint.is_bound:
            continue
        for person in constraint.people:
            key = (person, constraint.slot)
            existing = wanted.get(key)
            if existing and existing[1] != constraint.place:
                violations.append(
                    Violation(
                        rule="V6",
                        message=(
                            f"{person!r} is required in {existing[1]!r} by "
                            f"{existing[0]!r} and in {constraint.place!r} by "
                            f"{constraint.id!r}, both at {constraint.slot!r}"
                        ),
                    )
                )
            else:
                wanted[key] = (constraint.id, constraint.place)

    return violations


def murder_slot(mystery: Mystery) -> str | None:
    """When the killing happens. One definition, on the model (D-071)."""
    scene = mystery.murder_scene
    return scene.slot if scene is not None and scene.is_bound else None


def check_the_victim_stays_dead(mystery: Mystery) -> list[Violation]:
    """V7: nothing involving the victim happens after the murder, and the body
    does not move.

    Guards: the model, and our own rescheduler. A real generated case had the
    victim strangled in the vault, walk to the main gallery, and return to the
    vault to blackmail somebody. Every other rule passed it. Rescheduling a scene
    to a later slot (D-033) can also do this, so the fix belongs in both places
    and the rule is the backstop.
    """
    killed_at = murder_slot(mystery)
    if killed_at is None:
        return []

    index = {slot.id: slot.index for slot in mystery.slots}
    after = index.get(killed_at)
    if after is None:
        return []

    violations: list[Violation] = []

    for constraint in mystery.constraints:
        if (
            constraint.is_bound
            and mystery.victim in constraint.people
            and index.get(constraint.slot, -1) > after
            and mystery.killer not in constraint.people
        ):
            violations.append(
                Violation(
                    rule="V7",
                    message=(
                        f"Constraint {constraint.id!r} involves the victim at "
                        f"{constraint.slot!r}, which is after they were killed at "
                        f"{killed_at!r}"
                    ),
                )
            )

    resting_place = mystery.placements.get(mystery.victim, {}).get(killed_at)
    for slot in mystery.slots:
        if slot.index <= after:
            continue
        where = mystery.placements.get(mystery.victim, {}).get(slot.id)
        if where is not None and where != resting_place:
            violations.append(
                Violation(
                    rule="V7",
                    message=(
                        f"The victim is in {where!r} at {slot.id!r} but was killed "
                        f"in {resting_place!r} at {killed_at!r}. Bodies stay put"
                    ),
                )
            )

    return violations


# What the model just handed us. Only referential integrity applies: everything
# else is what the repairer exists to fix, so failing on it here would reject
# proposals that are one small move away from correct.
# What the model just handed us. Only referential integrity applies. A clash
# between two constraints is not grounds for rejection: the solver reschedules
# one of them (D-033), and only a clash that survives that is a real failure.
PROPOSED_RULES = [
    check_references_exist,
]

# After the solver. Everything must hold.
FINAL_RULES = [
    check_references_exist,
    check_constraints_do_not_contradict,
    check_the_victim_stays_dead,
    check_false_claims_are_false,
    check_constraints_match_timeline,
    check_exclusive_constraints_are_private,
    check_every_constraint_was_placed,
]


def validate(mystery: Mystery, phase: Phase = "final") -> ValidationResult:
    rules = PROPOSED_RULES if phase == "proposed" else FINAL_RULES
    violations = [v for rule in rules for v in rule(mystery)]
    return ValidationResult(violations=violations)
