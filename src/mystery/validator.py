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

import re
from dataclasses import dataclass, field
from typing import Literal

from mystery.models import Constraint, Mystery

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


def check_exclusive_scenes_do_not_collide(mystery: Mystery) -> list[Violation]:
    """V9: one room, one moment, one private scene.

    Guards: the language model. V6 catches the same person in two rooms at once.
    This is its dual and it went unnoticed for longer: two *different* private
    scenes booked into the same room at the same moment. Exclusive means nobody
    else is present, so two exclusive constraints on one place and slot with
    different casts cannot both be true, whatever the prose around them says.

    It came out of a real generation (D-090). A conversation was overheard from
    the corridor, and because the place was written "the office and the corridor
    outside it", the model put the listener *in the office*, exclusively, in the
    same slot as the murder. Both scenes read beautifully and the set was
    unsatisfiable. The solver did what an over-constrained solver does, which is
    produce something that satisfies neither, and the failure surfaced as five
    downstream complaints about a timeline that was never the problem.

    Caught at the proposed phase on purpose. The drafting loop feeds violations
    back as complaints, so a model that books two scenes into one room is told
    exactly that and can move one of them, in the same run, for the price of one
    more call. That is much cheaper than a rejected draft and far clearer than
    watching the solver flail.
    """
    violations: list[Violation] = []
    booked: dict[tuple[str, str], Constraint] = {}

    for constraint in mystery.constraints:
        if not constraint.exclusive or not constraint.is_bound:
            continue

        key = (constraint.place, constraint.slot)
        first = booked.get(key)
        if first is None:
            booked[key] = constraint
            continue
        if set(first.people) == set(constraint.people):
            continue

        violations.append(
            Violation(
                rule="V9",
                message=(
                    f"{first.id!r} and {constraint.id!r} are both private scenes in "
                    f"{constraint.place!r} at {constraint.slot!r}, with different "
                    f"people in them: {sorted(first.people)} and "
                    f"{sorted(constraint.people)}. Exclusive means nobody else is "
                    f"there, so only one of these can happen. Move one to another "
                    f"place or another moment. If somebody is meant to overhear "
                    f"from outside, put them in a different place: a listener in "
                    f"the room is not overhearing, they are present"
                ),
            )
        )

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
def check_the_body_is_not_stepped_over(mystery: Mystery) -> list[Violation]:
    """V10: after the killing, nobody is in the room with the body.

    Guards: the language model. The discovery says the body was found after the
    evening was over, which means nobody found it during the evening, which
    means nobody was in that room. A case that puts three people in the murder
    room an hour after the murder is a case where either the body was found then
    and the story is wrong, or three people stood next to a corpse and carried on
    working (D-094).

    It came out of a playtest where the reader could not work out when the victim
    died. The killer lied about the murder hour, and then the victim appeared in
    the same room an hour later with other people around him, so the timeline
    read as though he had been alive the whole time and the lie made no sense.

    The victim is exempt: they are the body, and V7 already requires them to stay
    where they fell.
    """
    killed_at = murder_slot(mystery)
    scene = mystery.murder_scene
    if killed_at is None or scene is None or scene.place is None:
        return []

    index = {slot.id: slot.index for slot in mystery.slots}
    when = index.get(killed_at)
    if when is None:
        return []

    later = sorted(
        (slot for slot in mystery.slots if slot.index > when), key=lambda s: s.index
    )
    violations: list[Violation] = []

    for slot in later:
        intruders = sorted(
            character.id
            for character in mystery.characters
            if character.id != mystery.victim
            and mystery.placements.get(character.id, {}).get(slot.id) == scene.place
        )
        if intruders:
            violations.append(
                Violation(
                    rule="V10",
                    message=(
                        f"{intruders} are in {scene.place!r} at {slot.id!r}, after the "
                        f"murder happened there at {killed_at!r}. The body is on that "
                        f"floor. Either they found it, which the discovery says nobody "
                        f"did until later, or they stepped over it. Move them, or move "
                        f"the scene they are there for"
                    ),
                )
            )

    return violations


def check_every_lie_covers_something(mystery: Mystery) -> list[Violation]:
    """V11: nobody lies about where they were for no reason.

    A11 has reported this for innocents since it existed, and reporting was the
    wrong strength. An unmotivated lie is not a case that is merely worse: it is
    a trap in the middle of the board. The player catches somebody out, which is
    the game's single strongest signal, presses it for ten questions and finds
    nothing underneath, and what they learn is that pressing does not pay. That
    is the opposite of the mechanic. A rule, from the proposed phase, so the
    model is told to fix it while it still costs a repair rather than a draft
    (D-111).

    `covers` pointing at a secret that does not exist is V4's job. This is the
    emptier failure: a lie with no `covers` at all.
    """
    return [
        Violation(
            rule="V11",
            message=(
                f"{claim.character!r} lies about where they were and `covers` is "
                f"empty. Give the id of the secret the lie protects, or take the "
                f"lie out: a lie with nothing under it is a dead end the player "
                f"cannot tell from a live one"
            ),
        )
        for claim in mystery.false_claims
        if not claim.covers.strip()
    ]


# A year in a role line. 1900-2099 is every date a case of this kind will use.
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


def check_roles_are_roles_not_histories(mystery: Mystery) -> list[Violation]:
    """V12: a `role` says what somebody is, not what they once did (D-137).

    Protects against the language model, and against a specific failure that cost
    a played case most of its second half. `role` is the one authored line that
    is broadcast: every other character is handed it in their roster, and it is
    printed under the portrait. It is not a fact. Nothing derives from it, nothing
    checks it, and no character can cite it.

    So a role that carries a dated event invents a fact for the whole house. One
    case gave the foreman "he witnessed the will of 2011", and there was no will
    of 2011 anywhere in the case: no secret, no constraint, no line of common
    ground. Five suspects had been told it and improvised freely around it, the
    man himself had not (that half is fixed separately) and denied it flatly, and
    the player spent thirteen of seventy-one questions on a document that did not
    exist, including the last three of the game.

    Dated events belong in `secrets` or `common_ground`, where they are held by
    somebody, gated, citable and true. A year in a role is the cheap mechanical
    signature of one that is not, so that is what this looks for.
    """
    return [
        Violation(
            rule="V12",
            message=(
                f"{character.name}'s role mentions {', '.join(YEAR.findall(character.role))}. "
                f"A role says what somebody is, not what they once did: nothing in "
                f"the case derives from it and nobody can cite it, so a dated event "
                f"here is a fact the whole house believes and nobody holds. Put the "
                f"event in `common_ground` or in a secret, and leave the role as the "
                f"standing it describes"
            ),
        )
        for character in mystery.characters
        if YEAR.search(character.role or "")
    ]


def check_the_commission_names_nobody(mystery: Mystery) -> list[Violation]:
    """V13: the briefing does not name a suspect (D-138).

    The commission is what the player is told before the first question: who
    wants an account of tonight and what they want it to say. It is allowed to
    carry a belief the house has already settled on, and that belief is allowed
    to be wrong, which is the whole of D-129.

    What it is not allowed to do is name the person. On a five-suspect case a
    name in the opening screen is an enormous prior even when it is the wrong
    one, and when it is the right one there is no case left: one played case
    opened with the family having agreed it was Anand, and Anand had done it.

    "They have already settled on one name between them" is a good briefing.
    Which name is a thing to find out in the first ten questions, not a thing to
    be handed. The victim is exempt: they are named everywhere already.
    """
    text = mystery.commission or ""
    if not text.strip():
        return []
    named = sorted(
        {
            character.name
            for character in mystery.characters
            if character.id != mystery.victim
            for word in character.name.split()
            if len(word) > 2 and re.search(rf"\b{re.escape(word)}\b", text)
        }
    )
    if not named:
        return []
    return [
        Violation(
            rule="V13",
            message=(
                f"the commission names {', '.join(named)}. The player reads this "
                f"before the first question, and a name there decides the case "
                f"before it starts. Say what the household believes without saying "
                f"who they believe it about: 'they have already settled on one name "
                f"between them' is the briefing, and which name is the game"
            ),
        )
    ]


PROPOSED_RULES = [
    check_roles_are_roles_not_histories,
    check_the_commission_names_nobody,
    check_every_lie_covers_something,
    check_references_exist,
    check_constraints_do_not_contradict,
    check_exclusive_scenes_do_not_collide,
    check_the_body_is_not_stepped_over,
]

# After the solver. Everything must hold.
FINAL_RULES = [
    check_roles_are_roles_not_histories,
    check_the_commission_names_nobody,
    check_every_lie_covers_something,
    check_references_exist,
    check_constraints_do_not_contradict,
    check_the_victim_stays_dead,
    check_false_claims_are_false,
    check_constraints_match_timeline,
    check_exclusive_constraints_are_private,
    check_every_constraint_was_placed,
    check_exclusive_scenes_do_not_collide,
    check_the_body_is_not_stepped_over,
]


def validate(mystery: Mystery, phase: Phase = "final") -> ValidationResult:
    rules = PROPOSED_RULES if phase == "proposed" else FINAL_RULES
    violations = [v for rule in rules for v in rule(mystery)]
    return ValidationResult(violations=violations)
