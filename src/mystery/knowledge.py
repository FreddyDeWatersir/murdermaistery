"""What each character knows, derived from the timeline.

The grid says where everyone was. This works out what that means each person can
testify to, which is everything the play layer needs and the only way to check
the property this project was specified around on day one:

    the killer's alibi is falsifiable from combined testimony but not from any
    single one.

Knowledge is three-state per D-012, and the distinction matters more than it
sounds. `observations` are things a character knows and will say. `conceals` are
things they know and will not say. Anything absent is a thing they do not know,
and an agent that produces it is leaking rather than confessing. Those two look
identical in a transcript and are opposite events.

Nothing here calls a model. Deriving knowledge is set arithmetic over a grid, and
keeping it that way is what makes the agent layer testable later: the facts are
computed, and only the voice is generated.
"""

from dataclasses import dataclass, field

from mystery.models import CharacterId, Mystery, PlaceId, SlotId


@dataclass(frozen=True)
class Observation:
    """One character seeing another somewhere, at some time."""

    subject: CharacterId
    place: PlaceId
    slot: SlotId


@dataclass
class Knowledge:
    """Everything one character can draw on when questioned."""

    character: CharacterId
    movements: dict[SlotId, PlaceId] = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)
    conceals: list[str] = field(default_factory=list)
    aware_of: list[str] = field(default_factory=list)

    @property
    def is_credible(self) -> bool:
        """A witness with nothing of their own to hide.

        This is the property that decides whether a piece of testimony settles a
        question on its own. In both hand-built prototypes every witness against
        the killer was compromised: one was a proven liar, one had just admitted
        hating the victim. That is what made their evidence suggestive rather
        than conclusive, and it is the whole reason the cases were fun rather
        than a single lucky question.
        """
        return not self.conceals

    def saw(self, subject: CharacterId, slot: SlotId) -> bool:
        return any(o.subject == subject and o.slot == slot for o in self.observations)

    def where_they_saw(self, subject: CharacterId, slot: SlotId) -> PlaceId | None:
        for observation in self.observations:
            if observation.subject == subject and observation.slot == slot:
                return observation.place
        return None


def murder_slot_index(mystery: Mystery) -> int | None:
    """When the killing happened, as a slot index."""
    if mystery.killer is None or mystery.victim is None:
        return None
    index = {slot.id: slot.index for slot in mystery.slots}
    for constraint in mystery.constraints:
        if (
            constraint.is_bound
            and mystery.killer in constraint.people
            and mystery.victim in constraint.people
        ):
            return index.get(constraint.slot)
    return None


def derive(mystery: Mystery) -> dict[CharacterId, Knowledge]:
    """Work out what everyone saw.

    Co-location is the whole mechanism: two people in a room at the same time
    each know the other was there. That is deliberately mechanical, because it is
    the part that must never be invented.
    """
    killed_at = murder_slot_index(mystery)
    ordered = sorted(mystery.slots, key=lambda s: s.index)

    knowledge = {
        character.id: Knowledge(
            character=character.id,
            movements=dict(mystery.placements.get(character.id, {})),
        )
        for character in mystery.characters
    }

    for slot in ordered:
        # The victim stops observing at the moment they die. The body is still in
        # the room, and other people still see it, but it testifies to nothing.
        by_place: dict[PlaceId, list[CharacterId]] = {}
        for character in mystery.characters:
            place = mystery.placements.get(character.id, {}).get(slot.id)
            if place is not None:
                by_place.setdefault(place, []).append(character.id)

        for place, present in by_place.items():
            for observer in present:
                if (
                    observer == mystery.victim
                    and killed_at is not None
                    and slot.index >= killed_at
                ):
                    continue
                for subject in present:
                    if subject == observer:
                        continue
                    knowledge[observer].observations.append(
                        Observation(subject=subject, place=place, slot=slot.id)
                    )

    for secret in mystery.secrets:
        if secret.holder in knowledge:
            knowledge[secret.holder].conceals.append(secret.id)
        for person in secret.known_by:
            if person in knowledge and person != secret.holder:
                knowledge[person].aware_of.append(secret.id)

    return knowledge


@dataclass
class AlibiAnalysis:
    """Who can break the killer's story, and whether any of them can do it alone."""

    claim_holds: bool
    contradictors: list[CharacterId] = field(default_factory=list)
    credible: list[CharacterId] = field(default_factory=list)

    @property
    def breakable(self) -> bool:
        return len(self.contradictors) >= 2

    @property
    def settled_by_one(self) -> bool:
        """True when a single unimpeachable witness ends the case.

        Two contradictors are not enough on their own. If one of them has nothing
        to hide, the player asks that person one question and it is over.
        """
        return bool(self.credible)


def analyse_alibi(mystery: Mystery, knowledge: dict[CharacterId, Knowledge]) -> AlibiAnalysis:
    """Work out who could falsify the false claim.

    Two ways to contradict a claim of "I was in room R at time T":

    1. You were in R at T and did not see them there.
    2. You saw them somewhere other than R at T.

    The second is usually empty for a private murder, because the only person who
    saw the killer is the one who died. Which means the case rests entirely on
    the first, and on how believable those witnesses are.
    """
    claim = mystery.false_claim
    if claim is None:
        return AlibiAnalysis(claim_holds=True)

    truth = mystery.placements.get(claim.character, {}).get(claim.slot)
    if truth == claim.place:
        return AlibiAnalysis(claim_holds=True)

    contradictors: list[CharacterId] = []

    for character in mystery.characters:
        if character.id in (claim.character, mystery.victim):
            continue

        know = knowledge[character.id]
        in_the_room = know.movements.get(claim.slot) == claim.place
        saw_elsewhere = (
            know.saw(claim.character, claim.slot)
            and know.where_they_saw(claim.character, claim.slot) != claim.place
        )

        if (in_the_room and not know.saw(claim.character, claim.slot)) or saw_elsewhere:
            contradictors.append(character.id)

    return AlibiAnalysis(
        claim_holds=False,
        contradictors=sorted(contradictors),
        credible=sorted(c for c in contradictors if knowledge[c].is_credible),
    )
