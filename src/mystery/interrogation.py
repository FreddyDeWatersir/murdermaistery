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
from mystery.models import CharacterId, Mystery, PlaceId, SlotId, with_article

log = structlog.get_logger()


def _how_they_are_going_about_it(
    spoken: dict[CharacterId, int], mystery: Mystery, listener: CharacterId
) -> list[str]:
    """What the house makes of the person asking (D-100).

    The player has no authority here, so the only thing they can spend is how
    they are seen, and until now nobody saw them at all. This is the cheapest
    honest version: it reads how the questioning has actually been distributed,
    which the transcript already knows, and hands each suspect an impression to
    have about it. No score, no meter, nothing that unlocks. A person with an
    opinion of you is a person, and their `manner` decides what they do with it.
    """
    total = sum(spoken.values())
    if total < 3:
        return []

    names = {c.id: c.name for c in mystery.characters}
    mine = spoken.get(listener, 0)
    others = {who: n for who, n in spoken.items() if who != listener}
    read: list[str] = []

    hardest, most = max(others.items(), key=lambda kv: kv[1], default=(None, 0))
    if hardest and most >= 6:
        read.append(
            f"They have taken {names.get(hardest, hardest)} apart. An hour of it, "
            f"from somebody with no standing here at all. Make of that what you like."
        )

    untouched = [
        c.name
        for c in mystery.characters
        if c.id not in (mystery.victim, listener) and not spoken.get(c.id)
    ]
    if untouched and total >= 6:
        read.append(
            f"They have not gone near {', '.join(untouched)} all evening, which is "
            f"either an oversight or a decision."
        )

    if mine == 0 and total >= 6:
        read.append(
            "They have not asked you anything yet. Everybody else, and not you."
        )
    elif mine and mine * 3 <= total and total >= 9:
        read.append("They keep leaving you and going back to the others.")

    return read


def word_got_back(
    transcript: "Transcript",
    mystery: Mystery,
    knowledge: dict[CharacterId, Knowledge],
    listener: CharacterId,
) -> list[str]:
    """What this person has heard about the questioning so far (D-099).

    Five people in one building on one evening talk to each other. Until now
    they did not, which made the house five separate booths and made half the
    break conditions in every case unreachable: "she folds if told that someone
    has already mentioned it" describes a world where people talk, and that
    world did not exist.

    Two tiers, and the split is the whole safety argument.

    **Everyone hears who has been questioned**, and roughly how much. That is
    visible from a corridor and gives away nothing.

    **Only somebody who already knows a secret hears that it came up.** A person
    cannot be told about a thing they do not know, so nothing here can put a
    secret into a brief that did not already have it, and the closure that
    decides whether a case is winnable is untouched. What changes is that a
    person who has been protecting something can now learn it is already out,
    which is precisely the condition half of them are written to break on.

    No model call, no new state: this is a view over the transcript and the
    knowledge that already exist.
    """
    names = {c.id: c.name for c in mystery.characters}
    secrets = {s.id: s for s in mystery.secrets}
    know = knowledge.get(listener)
    mine = set(know.conceals) if know else set()
    aware = set(know.aware_of) if know else set()

    lines: list[str] = []
    told: list[str] = []

    spoken = transcript.spoken_to()
    for who, count in sorted(spoken.items()):
        if who == listener:
            continue
        lines.append(
            f"They have been questioning {names.get(who, who)}"
            + (" at length" if count >= 4 else "")
            + "."
        )

    lines += _how_they_are_going_about_it(spoken, mystery, listener)

    for secret_id, teller in sorted(transcript.who_gave_up().items()):
        secret = secrets.get(secret_id)
        if secret is None or teller == listener:
            continue

        if secret_id in mine:
            # The one that matters: they are still guarding something the room
            # already knows. Half the break conditions in every generated case
            # describe exactly this moment.
            told.append(
                f"They already know this, and it did not come from you. "
                f"{names.get(teller, teller)} told them. \u2014 {secret.summary}"
            )
        elif secret_id in aware:
            teller_name = names.get(teller, teller)
            told.append(
                f"{teller_name} has admitted it to them. \u2014 {secret.summary}"
                if teller == secret.holder
                else f"{teller_name} has told them about "
                f"{names.get(secret.holder, secret.holder)}. \u2014 {secret.summary}"
            )

    # A long evening would otherwise arrive as twenty lines of recap. What is
    # yours comes first, because it is the part that changes what you do.
    mine_first = [line for line in told if line.startswith("They already know")]
    rest = [line for line in told if not line.startswith("They already know")]
    return lines + mine_first + rest[: max(0, 6 - len(mine_first))]


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


def _hour(label: str) -> str:
    for dash in ("\u2014", "\u2013", " - "):
        if dash in label:
            return label.split(dash, 1)[0].strip()
    return label


def _handle(secret, fallback: str) -> str:
    """A secret named short enough to be worth repeating.

    The full summary is already in this character's brief, so the ledger only
    has to say which one has come out. First sentence, capped, because a
    generator writes summaries of any length and this line is here to save
    tokens rather than spend them.
    """
    if secret is None:
        return fallback.replace("_", " ")
    text = secret.summary.strip()
    for stop in (". ", "; "):
        if stop in text[:120]:
            text = text[: text.index(stop) + 1]
            break
    return text if len(text) <= 120 else text[:117].rstrip() + "..."


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

    def ledger(self, mystery: Mystery, character: CharacterId) -> list[str]:
        """What this character has committed to, in one line each (D-140).

        The prompt used to carry every answer this person had given, verbatim,
        on every question. Measured on a played case that was a third of the
        whole cost of the run, growing linearly, and quadratic over an evening.

        It was also the long way round. A character does not need forty of their
        own paragraphs to stay consistent; they need to know what they have
        committed to, and this program already computes exactly that. Assertions
        are what they said about who was where. `cited` says which secrets have
        already left their mouth. Both are structured, both are already stored,
        and neither needs a model to summarise it, which means nothing here can
        drift away from what was actually said.

        One line per position rather than one per statement, because a suspect
        who has held the same story for ten questions has committed to one
        thing, not ten. Latest wins: somebody who changed their story is bound
        by the version they are standing on now, and the fact that they moved is
        the notebook's business rather than theirs.
        """
        names = {c.id: c.name for c in mystery.characters}
        names.update({t.id: t.name for t in mystery.things})
        # Slot labels are written as "19:45 - power back, the last cousins
        # leaving". The clause after the dash is scene-setting, which is worth
        # having in the facts and is repeated waste here, where the line only
        # has to identify the hour.
        times = {s.id: _hour(s.label) for s in mystery.slots}
        places = {p.id: p.name for p in mystery.places}

        mine = [s for s in self.statements if s.speaker == character]
        if not mine:
            return []

        placed: dict[tuple[str, str], str] = {}
        given: list[str] = []
        for statement in mine:
            for assertion in statement.assertions:
                placed[(assertion.subject, assertion.slot)] = assertion.place
            for cited in statement.cited:
                if cited.startswith(("secret:", "heard:")):
                    given.append(cited.split(":", 1)[1])

        lines = []
        for (subject, slot), place in sorted(
            placed.items(), key=lambda kv: (kv[0][0] != character, kv[0][1])
        ):
            where = f"in {with_article(places.get(place, place))} at {times.get(slot, slot)}"
            if subject == character:
                lines.append(f"You have said you were {where}.")
            else:
                lines.append(f"You have said {names.get(subject, subject)} was {where}.")

        # The secret itself is already in their brief in full, so naming it is
        # enough. Repeating the whole summary here would be paying twice for it.
        secrets = {s.id: s for s in mystery.secrets}
        for held in dict.fromkeys(given):
            secret = secrets.get(held)
            lines.append(f"You have already told them: {_handle(secret, held)}")

        # How many questions they have taken is already in the live block, which
        # says it better ("this is question nine, they keep coming back to you").
        # A refusal is not counted anywhere else and changes how the next one
        # lands, so that one line stays.
        refused = sum(1 for s in mine if s.refused)
        if refused:
            lines.append(
                f"You have refused to answer {refused} "
                f"{'time' if refused == 1 else 'times'} already."
            )
        return lines

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

    def spoken_to(self) -> dict[CharacterId, int]:
        """Who has been questioned, and how much. The cheapest thing that travels."""
        counts: dict[CharacterId, int] = {}
        for statement in self.statements:
            counts[statement.speaker] = counts.get(statement.speaker, 0) + 1
        return counts

    def who_gave_up(self) -> dict[str, CharacterId]:
        """Which secret came out of whose mouth, first time only.

        The distinction the whole gossip layer turns on: a secret its holder
        gave up themselves is a different event from a secret somebody else told
        you about them, and only the second one is worth carrying back.
        """
        first: dict[str, CharacterId] = {}
        for statement in self.statements:
            for cited in statement.cited:
                if cited.startswith(("secret:", "heard:")):
                    first.setdefault(cited.split(":", 1)[1], statement.speaker)
        return first

    def contradictions(self) -> list[Contradiction]:
        """Every pair of statements that cannot both be true.

        Keyed on (subject, slot): two people cannot both be right about where one
        person stood at one moment. Self-contradictions fall out of the same
        comparison, because a speaker who changes their story is disagreeing with
        an earlier version of themselves.
        """
        # One entry per *disagreement*, not per statement that repeats one
        # (D-133). The old version kept the first claim for each (subject, slot)
        # and appended a fresh contradiction every time any later statement
        # differed from it, so a suspect who held their story across ten
        # questions produced ten identical contradictions and the badge climbed
        # for saying the same thing again. A contradiction is a property of the
        # testimony, not an event in the transcript: asking twice cannot make the
        # house more inconsistent than it is.
        said: dict[tuple[CharacterId, SlotId], dict[CharacterId, PlaceId]] = {}
        emitted: set[tuple] = set()
        found: list[Contradiction] = []

        def note(subject, slot, first, second) -> None:
            # Sorted, so A-disagrees-with-B and B-disagrees-with-A are one thing.
            pair = (subject, slot, *sorted([first, second]))
            if pair in emitted:
                return
            emitted.add(pair)
            found.append(
                Contradiction(subject=subject, slot=slot, first=first, second=second)
            )

        for statement in self.statements:
            for assertion in statement.assertions:
                key = (assertion.subject, assertion.slot)
                positions = said.setdefault(key, {})
                mine = positions.get(statement.speaker)

                if mine == assertion.place:
                    # They have said this before. Repetition is not new evidence.
                    continue

                if mine is not None:
                    # Changing your own story, which is the loudest kind and the
                    # one that must survive the deduplication above.
                    note(
                        assertion.subject,
                        assertion.slot,
                        (statement.speaker, mine),
                        (statement.speaker, assertion.place),
                    )

                positions[statement.speaker] = assertion.place

                for speaker, place in positions.items():
                    if speaker != statement.speaker and place != assertion.place:
                        note(
                            assertion.subject,
                            assertion.slot,
                            (speaker, place),
                            (statement.speaker, assertion.place),
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
