"""The interrogation loop, and the contradiction tracker.

Every answer a character gives is reduced to a set of assertions: this person was
in that room at that time. The tracker compares assertions across the whole
transcript, which turns "did anyone say something that does not fit" from a
memory problem into set arithmetic.

That distinction is load-bearing. In the paper playtest the case broke open
because two conflicting claims happened to land in adjacent rows of a table, and
the same two claims eleven messages apart in prose would very likely have been
missed. Deduction here is a memory problem before it is a reasoning problem.

Which raises the question left open as D-019: if the software finds every
contradiction, what is left for the player? The answer this module takes is that
there are two different things and only one of them is memory work.

**Contradictions** are proven. Two statements assert different places for the
same person at the same moment, and one of them is false. Finding these is
bookkeeping, the player gains nothing by doing it by hand, and the software does
it.

**Leads** are not proven. Somebody claims to have been in a room, and another
character who was in that room has never mentioned them. That is suggestive and
it is not evidence: the witness may simply not have been asked. Chasing it means
deciding who to press and how, which is the game.

So the tracker does the remembering and leaves the deciding.
"""

from dataclasses import dataclass, field

import structlog

from mystery.agent import Brief, Reply
from mystery.knowledge import Knowledge
from mystery.models import CharacterId, Mystery, PlaceId, SlotId

log = structlog.get_logger()


@dataclass(frozen=True)
class Assertion:
    """A claim that somebody was somewhere at some time."""

    subject: CharacterId
    slot: SlotId
    place: PlaceId


@dataclass
class Statement:
    """One answer, and what it committed the speaker to."""

    round: int
    speaker: CharacterId
    question: str
    speech: str
    assertions: list[Assertion] = field(default_factory=list)
    refused: bool = False
    # Every fact id the reply cited, not only the ones that place somebody in a
    # room. Assertions answer "where was everyone"; this answers "what has the
    # player actually been told", which is what the accusation needs (D-065).
    cited: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Contradiction:
    """Two statements that cannot both be true."""

    subject: CharacterId
    slot: SlotId
    first: tuple[CharacterId, PlaceId]
    second: tuple[CharacterId, PlaceId]

    @property
    def is_self_contradiction(self) -> bool:
        return self.first[0] == self.second[0]


@dataclass(frozen=True)
class Lead:
    """Somebody's account has a hole where another person says they were.

    `witness_has_spoken` is the difference between a question worth asking and a
    hole in an answer already given. If the witness has never described that room
    at that time, their silence means nothing: nobody asked them. If they *have*
    described it, named who was with them, and left the claimant out, their
    account and the claim cannot both be complete.

    That second kind is what broke the hand-built case: Renske described the
    lighting box during the interval and Wouter was not in her account of it.
    """

    claimant: CharacterId
    slot: SlotId
    place: PlaceId
    silent_witness: CharacterId
    witness_has_spoken: bool = False


def assertions_from(brief: Brief, reply: Reply) -> list[Assertion]:
    """Reduce a reply to what it committed the speaker to.

    Only cited facts count. A model that says something in prose without citing
    it has made a claim the tracker cannot see, which is the same limitation the
    leakage detector has and for the same reason (D-041).

    Guarded facts count too, and that is the whole point of them (D-064). When a
    liar finally admits where they really were, that retraction has to land in
    the notebook and flip the timeline, or the player watches somebody come
    clean while the grid goes on showing the lie.
    """
    by_id = {fact.id: fact for fact in (*brief.facts, *brief.guarded)}

    return [
        Assertion(subject=fact.subject, slot=fact.slot, place=fact.place)
        for used in reply.used
        if (fact := by_id.get(used))
        and fact.subject is not None
        and fact.slot is not None
        and fact.place is not None
    ]


@dataclass
class Transcript:
    statements: list[Statement] = field(default_factory=list)

    def record(self, statement: Statement) -> None:
        self.statements.append(statement)
        log.info(
            "interrogation.statement",
            round=statement.round,
            speaker=statement.speaker,
            assertions=len(statement.assertions),
            refused=statement.refused,
        )

    @property
    def rounds(self) -> int:
        return max((s.round for s in self.statements), default=0)

    def asked(self, character: CharacterId) -> int:
        return sum(1 for s in self.statements if s.speaker == character)

    def surfaced_secrets(self) -> set[str]:
        """Which secrets have actually come out.

        Two ways in: the person holding it gave it up (`secret:x`), or somebody
        who knew it told you (`heard:x`). Both are citations, so this is set
        membership rather than a judgement about prose, which is the same trick
        the leak detector uses and for the same reason (D-041).
        """
        return {
            cited.split(":", 1)[1]
            for statement in self.statements
            for cited in statement.cited
            if cited.startswith(("secret:", "heard:"))
        }

    def contradictions(self) -> list[Contradiction]:
        """Every pair of statements that cannot both be true.

        Keyed on (subject, slot): two people cannot both be right about where one
        person stood at one moment. Self-contradictions fall out of the same
        comparison, because a speaker who changes their story is disagreeing with
        an earlier version of themselves.
        """
        seen: dict[tuple[CharacterId, SlotId], tuple[CharacterId, PlaceId]] = {}
        found: list[Contradiction] = []

        for statement in self.statements:
            for assertion in statement.assertions:
                key = (assertion.subject, assertion.slot)
                previous = seen.get(key)

                if previous is None:
                    seen[key] = (statement.speaker, assertion.place)
                elif previous[1] != assertion.place:
                    found.append(
                        Contradiction(
                            subject=assertion.subject,
                            slot=assertion.slot,
                            first=previous,
                            second=(statement.speaker, assertion.place),
                        )
                    )

        return found

    def leads(
        self, mystery: Mystery, knowledge: dict[CharacterId, Knowledge]
    ) -> list[Lead]:
        """Rooms where somebody claims to have been and nobody has confirmed it.

        Deliberately not evidence. The silent witness may never have been asked,
        and pressing them is the player's move to make, not the software's.
        """
        found: list[Lead] = []

        confirmed = {
            (a.subject, a.slot)
            for s in self.statements
            for a in s.assertions
            if a.subject != s.speaker
        }

        # Every (person, place, slot) anyone has put on the record, so we can ask
        # whether a witness has described a moment without mentioning somebody.
        spoken_about: dict[tuple[CharacterId, SlotId, PlaceId], set[CharacterId]] = {}
        for s in self.statements:
            for a in s.assertions:
                spoken_about.setdefault((s.speaker, a.slot, a.place), set()).add(a.subject)

        for statement in self.statements:
            for assertion in statement.assertions:
                if assertion.subject != statement.speaker:
                    continue
                if (assertion.subject, assertion.slot) in confirmed:
                    continue

                for character in mystery.characters:
                    if character.id in (statement.speaker, mystery.victim):
                        continue
                    if knowledge[character.id].movements.get(assertion.slot) != assertion.place:
                        continue

                    named = spoken_about.get(
                        (character.id, assertion.slot, assertion.place), set()
                    )
                    found.append(
                        Lead(
                            claimant=statement.speaker,
                            slot=assertion.slot,
                            place=assertion.place,
                            silent_witness=character.id,
                            witness_has_spoken=bool(named),
                        )
                    )

        return found
