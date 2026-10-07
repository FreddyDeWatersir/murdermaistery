"""Ground truth data model for a mystery.

Design notes: docs/decisions.md D-011, D-021, D-022, D-024.

`placements` is a nested dict rather than a list of records on purpose. With
`dict[CharacterId, dict[SlotId, PlaceId]]`, "one character in two places during
the same slot" is not merely invalid, it is unrepresentable: a dict key holds
exactly one value. Validator rules should only cover failures the type system
cannot prevent, so that half of the constraint costs us nothing to enforce.

The other half, that every character has *some* placement in every slot, is not
free. Nothing here stops a hole in the grid. That is a rule, not a type.
"""

from typing import Literal

from pydantic import BaseModel, Field

CharacterId = str
PlaceId = str
SlotId = str


class Place(BaseModel):
    """A location in the building.

    `within` exists because a dressing room is not the same observational
    position as the corridor it opens onto. Playtesting hit this four separate
    times (finding F3, decision D-011). No rule uses it yet; it is here so the
    fixture corpus does not have to be migrated later.

    `adjacent` is what you can reach or hear from here: the doors out of this
    room (D-093). It is what makes a building out of a list of rooms, and it is
    the difference between the Map tab drawing a plan and drawing a table.
    Symmetry is enforced rather than requested, because a door works from both
    sides and no prompt reliably remembers to say so twice.
    """

    id: PlaceId
    name: str
    within: PlaceId | None = None
    adjacent: list[PlaceId] = Field(default_factory=list)


class Character(BaseModel):
    """A person at the gathering, and how they behave when questioned.

    Everything below `name` is the half of a character sheet that cannot be
    derived from a timeline. The grid gives facts; this gives a person. In the
    hand-built prototypes it was the difference between a witness reciting
    locations and Renske refusing to answer until she was told something first
    (D-044).
    """

    id: CharacterId
    name: str
    wants: str = ""
    manner: str = ""
    # How the sentences come out, as opposed to what they do with the question
    # (D-127). Dealt from the seed like the manner, and independent of it: a
    # blunt three-word answerer can still be the one who answers for everybody.
    voice: str = ""
    under_pressure: str = ""
    # What the player is told about them before asking anything: their job, and
    # what they were to the victim. Public, printable, and no part of the puzzle
    # (D-074). Distinct from `wants`, which is private and stays server side.
    role: str = ""
    # "woman", "man", or whatever the generator writes. Stated rather than
    # sniffed out of the `look` sentence, which is what the drawn portrait used
    # to do and got wrong whenever the sentence did not say.
    gender: str = ""
    impressions: dict[CharacterId, str] = Field(default_factory=dict)
    look: str = ""
    # A number, from the skeleton (D-201). In the prose only, a woman of
    # fifty-six was "a girl of nineteen" twelve years ago and nothing could
    # notice. As a number it can be subtracted.
    age: int | None = None


class Slot(BaseModel):
    """One discrete unit of time. `index` gives the ordering; `label` is for humans."""

    id: SlotId
    label: str
    index: int


class Constraint(BaseModel):
    """Something the story requires to be true.

    This is the contract between the language model and the solver (D-022). The
    model emits constraints; the solver finds a grid satisfying all of them at
    once.

    `place` and `slot` are optional because an unsolved constraint does not know
    them yet. "A tryst, private, some time in the middle of the evening" is a
    real constraint with both fields empty. The solver's whole job is to bind
    them, and a constraint still unbound after solving means the solver could
    not place it (D-024).

    `exclusive` means these people and nobody else. It is the constraint behind
    every tryst, every unwitnessed confrontation, and the murder. Note that
    "Alex is alone in the back office" needs no separate kind: it is simply
    `people=["alex"], exclusive=True`. Same predicate, one type.
    """

    id: str
    people: list[CharacterId]
    exclusive: bool = False
    place: PlaceId | None = None
    slot: SlotId | None = None
    description: str = ""

    @property
    def is_bound(self) -> bool:
        """True once the solver has chosen a place and a slot for this."""
        return self.place is not None and self.slot is not None


class Account(BaseModel):
    """What one person says happened in a scene they were in (D-132).

    The third falsifiable axis, and the one that finally makes the web
    load-bearing. Person-place-slot says who was in the room. Thing-place-slot
    says what was in it. Neither says **what happened there**, so a scene was one
    authoritative `description` the player never saw, and `impressions` were
    opinions, which cannot be wrong.

    An account can be. Two people were in the library when the argument
    happened; each gives their version; the versions disagree; and now catching
    somebody out does not require catching them in a room.

    **`honest` is the point of the whole class.** A false account is not
    automatically a lie. Somebody can be certain and wrong — about what was said,
    who said it first, whether the door was open — and until now every fact in
    this game was true and every conflict meant a liar. That made a contradiction
    an accusation. With honest error in the mix, a contradiction becomes a
    question: one of you is wrong, and which is the interesting part.
    """

    # The scene this is about: the id of a `Constraint`.
    constraint: str
    character: CharacterId
    # Their version, in their voice, one or two sentences.
    says: str
    # Whether it is what actually happened.
    true: bool = True
    # If it is not true: are they lying, or do they simply remember it wrong?
    # A liar can be broken. A person who is honestly mistaken can only be shown
    # something, and will be relieved rather than caught.
    honest: bool = False
    # What would make them change their account. For a liar, what breaks them;
    # for an honest mistake, what would jog it.
    changes_when: str = ""


class Thing(BaseModel):
    """An object with a path through the evening (D-131).

    The second falsifiable axis, and the reason for it: until now every claim the
    game can check reduced to *person, place, slot*. So the only lie anybody
    could tell was about which room they were in, the only contradiction was a
    collision on one grid, and the notebook was a spreadsheet with a story
    printed next to it.

    A thing has its own `where`, slot by slot, and it moves because somebody
    moved it. That makes an object's path a claim people can be wrong about
    without lying about themselves, which is the oldest evidence in the
    tradition: the weapon was in the hall at eight and beside the body at
    eleven, so somebody carried it, and the interesting question is who and when
    rather than who was in the drawing room.

    `Secret.evidence` is a different thing and stays: that is a document produced
    to open a gate. This is an object that was somewhere.
    """

    id: str
    name: str
    # Whose it is, when that means anything. A key belongs to somebody; a stone
    # off a newel post belongs to the house.
    belongs_to: CharacterId | None = None
    # Slot to place. A dict rather than a list of records for the same reason
    # `placements` is: "in two rooms at once" becomes unrepresentable rather
    # than merely invalid.
    where: dict[SlotId, PlaceId] = Field(default_factory=dict)
    # Who carried it, when it moved. The id of whoever was responsible, per slot
    # in which its place changes. Not derivable: two people were in that room.
    moved_by: dict[SlotId, CharacterId] = Field(default_factory=dict)
    # What its path is worth knowing. One sentence, for the reveal.
    matters: str = ""
    # Which dealt role it plays (D-203): residue, killer_trace, misleading,
    # carried, weapon. Empty on every case before the deck.
    role: str = ""

    @property
    def moves(self) -> int:
        seen = list(self.where.values())
        return sum(1 for a, b in zip(seen, seen[1:], strict=False) if a != b)


_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def age_words(n: int) -> list[str]:
    """Ways an age is written in prose: "61", "sixty-one", "sixty one" (D-201)."""
    if n < 0 or n > 119:
        return [str(n)]
    if n < 20:
        word = [_ONES[n]]
    elif n < 100:
        tens, ones = divmod(n, 10)
        word = [_TENS[tens]] if not ones else [f"{_TENS[tens]}-{_ONES[ones]}",
                                                f"{_TENS[tens]} {_ONES[ones]}"]
    else:
        rest = n - 100
        tail = age_words(rest)[1:] if rest >= 20 or rest == 0 else [_ONES[rest]]
        word = [f"a hundred and {t}" for t in tail if t != "zero"] or ["a hundred"]
    return [str(n), *word]


def with_article(name: str) -> str:
    """A name with exactly one article in front of it.

    A generator writes both "stone head of a newel post" and "a signet ring",
    and both "hall" and "The central hall". Anything that puts one of these in a
    sentence has to cope with both, and doing it in two places is how the two
    places disagree.
    """
    first = name.split(" ", 1)[0].lower()
    return name if first in ("a", "an", "the") else f"the {name}"


class Secret(BaseModel):
    """Something a character is concealing.

    This is the layer that makes a cast into a mystery rather than a list of
    people who were in rooms. Constraints say where everyone was; secrets say
    why anyone would lie about it.

    `about` is usually the victim, and that is the point. In a case that works,
    the victim holds something over almost everyone, so that half the cast has a
    motive and the killer is not the only person with a reason to be evasive.

    `revealed_by` names another secret that has to surface first. That gating is
    what stops the obvious suspect being the answer: the killer's motive stays
    invisible until some unrelated-looking thread is pulled.

    `is_motive` marks the one secret that explains why the killer did it. A
    killer usually holds two: the background that made them vulnerable, and the
    reason they picked up the sculpture. Guessing which is which by taking the
    first match got A5 wrong on two real cases, so it is stated rather than
    inferred.

    `breaks_when` is the condition under which the holder stops concealing it.
    Concealment that never breaks is a wall, not a mystery, and playtesting
    showed the conditions are per character rather than global: one secret held
    for five rounds and went under a direct, named press, another went sideways
    under an emotional question its holder was not braced for (D-012).

    `evidence` is the thing itself, when the secret has one: the ledger pages,
    the forged letter, the photograph. A secret with an object attached hands
    the player something they can carry to somebody else and put in front of
    them, which is the only way a gate can be checked rather than judged
    (D-087). Most secrets have none and are simply things you know.
    """

    id: str
    holder: CharacterId
    about: CharacterId | None = None
    summary: str
    known_by: list[CharacterId] = Field(default_factory=list)
    revealed_by: str | None = None
    breaks_when: str = ""
    evidence: str = ""
    is_motive: bool = False
    # Would a reader who learned only this put the holder on the list (D-106)?
    # Distinct from `is_motive`, which is the one reason the killer actually
    # acted. A case where only the killer has a damning secret is smooth and
    # dull: the player finds the one person with something and is finished.
    # Stated rather than inferred, because "a secret about the victim" and "a
    # reason to kill the victim" are not the same thing and only the writer
    # knows which one this is.
    damning: bool = False
    # Why having `revealed_by` makes this come out, in one sentence (D-191).
    # Written with the skeleton, so a gate has a reason before anybody writes a
    # breaking point, and the prose stage writes `breaks_when` from it.
    how_it_opens: str = ""


def with_doors_both_ways(places: list[Place]) -> list[Place]:
    """Every door open from both sides, and nobody adjacent to themselves.

    A model writing a floor plan will say the corridor opens onto the office and
    then describe the office without mentioning the corridor. Both halves are
    the same door. Repairing this is not worth a validator rule and a retry: it
    is bookkeeping with exactly one right answer, so it is done rather than
    complained about (D-093).
    """
    known = {place.id for place in places}
    doors: dict[str, set[str]] = {place.id: set() for place in places}

    for place in places:
        for other in place.adjacent:
            if other == place.id or other not in known:
                continue
            doors[place.id].add(other)
            doors[other].add(place.id)

    return [
        place.model_copy(update={"adjacent": sorted(doors[place.id])})
        for place in places
    ]


# How old somebody was at a past event, in the three words that matter for what
# they could have done there (D-201). Bounds overlap at sixteen to nineteen on
# purpose: a novice of seventeen can be either.
STAGES: dict[str, tuple[int, int]] = {"child": (3, 12), "youth": (13, 19), "adult": (16, 200)}
Stage = Literal["child", "youth", "adult"]


class Presence(BaseModel):
    """One person at a past event (D-201)."""

    # A character id, or "investigator" for the player.
    who: str
    age_then: int
    stage: Stage
    # What they were there, in a few words: "a brother of the choir", "a girl
    # in the stalls". Said to anybody who knows they were there.
    role: str = ""
    # Whether the house knows they were there. A presence nobody knows about is
    # told only to the person themselves.
    known: bool = True


class PastEvent(BaseModel):
    """The old business, as a roster (D-201).

    "Four of us stood in that choir" left the case to say who, and five suspects
    each said someone different. Here the who is a list, the when is a number,
    and a count in the prose has something to agree with.
    """

    id: str
    what: str
    years_ago: int
    present: list[Presence] = Field(default_factory=list)


class Investigator(BaseModel):
    """Who the player is tonight, and why anybody is talking to them (D-101).

    Written per case rather than fixed, because the only frame that works in
    every setting is a vague one, and a vague one is exactly what made the
    question "why would they answer me at all" unanswerable. An assessor sent by
    the insurer, a solicitor acting for the estate, somebody the dead man himself
    engaged three weeks ago about the thefts: each is specific, each belongs to
    its setting, and each has a reason to be standing there at midnight.

    `standing` is the crucial half. Never police, never able to compel anybody.
    The compliance model is not authority: it is that the police are an hour away
    and everybody would rather their version reached them first, through
    somebody, than be the subject of somebody else's.

    `name` came last (D-198): the suspects call the player by it, and a player
    who only read "a Benedictine of Sahagún" at the bottom of the file did not
    know that "Brother Lope" was them. Empty on every case before it.
    """

    name: str = ""
    role: str = ""
    why_here: str = ""
    standing: str = ""


class FalseClaim(BaseModel):
    """Where somebody says they were, which is not where they were.

    Innocent people lie too, and that is the point of this being a list on the
    mystery rather than a single field (D-063). When exactly one person lies
    about their movements, "who lied" and "who killed him" are the same
    question, the timeline answers it on its own, and every secret in the case
    is decoration. Three liars and the timeline gives you a shortlist instead of
    a name, which is the job it should have had all along.

    `covers` is the id of the secret this lie protects, and `admits_when` is
    what makes them drop it. Together they are the way out: a lie a player can
    detect but never resolve is not depth, it is noise.
    """

    character: CharacterId
    place: PlaceId
    slot: SlotId
    covers: str = ""
    admits_when: str = ""


class Discovery(BaseModel):
    """How the evening ended, which everybody knows.

    Playtesting found the suspects could not discuss the death itself, because
    nothing in the model said the body had been found, by whom, or where. That is
    common knowledge in the fiction and belongs in every brief (D-054).
    """

    finder: CharacterId
    place: PlaceId
    summary: str = ""


class Mystery(BaseModel):
    """The whole of a case.

    `killer` and `victim` are separate fields rather than a convention about
    which constraint is named "murder". Almost everything downstream needs them:
    knowledge derivation, the reveal, and every quality check that asks a
    question about the murder rather than about the grid.
    """

    title: str
    killer: CharacterId | None = None
    victim: CharacterId | None = None
    characters: list[Character]
    places: list[Place]
    slots: list[Slot]
    placements: dict[CharacterId, dict[SlotId, PlaceId]] = Field(default_factory=dict)
    constraints: list[Constraint] = Field(default_factory=list)
    secrets: list[Secret] = Field(default_factory=list)
    # The id of the constraint in which the killing happens. Optional, because
    # it can usually be worked out, and worth asking for anyway: working it out
    # is where two real cases went wrong (D-071).
    investigator: Investigator | None = None
    murder: str | None = None
    false_claims: list[FalseClaim] = Field(default_factory=list)
    # Somebody who says they did it and did not. Only some shapes of case have
    # one, so it is optional and means nothing when absent (D-067).
    false_confessor: CharacterId | None = None
    discovery: Discovery | None = None
    # Plain facts about the occasion that everybody in the building would state
    # the same way, and the only place a number about the house is allowed to
    # come from. Without it each suspect re-derives the world from their own role
    # text, and in one played case the same list of names was six long to one
    # person and nine long to another (D-111). Optional: cases written before it
    # existed simply have less shared ground.
    common_ground: list[str] = Field(default_factory=list)
    # What the player was told they are here to settle (D-129). Stated to them
    # in the briefing, because being told what you are for is not a spoiler.
    # Whether it was the right question is the case, and roughly two in five
    # commissions are wrong about something.
    commission: str = ""
    # Objects with paths of their own (D-131). The second thing in the game that
    # can be somewhere, and therefore the second thing anybody can be wrong
    # about.
    things: list[Thing] = Field(default_factory=list)
    # The old business, with who was there and how old (D-201).
    history: list[PastEvent] = Field(default_factory=list)
    # What people say happened in the scenes they were in (D-132). The third
    # thing that can be wrong, and the first that can be wrong innocently.
    accounts: list[Account] = Field(default_factory=list)

    # Which instructions produced this draft: the first eight characters of the
    # hash of the system prompt (D-166). Not content, and the model never writes
    # it; `generate` stamps it after parsing.
    #
    # Every base rate quoted in the decision log so far has been measured over a
    # corpus that mixes prompt versions with no way to tell them apart, which is
    # how "A22 fires on 97% of drafts" turned out to mean "28 of the 30 drafts
    # predate the instruction". A batch of drafts bought to measure something is
    # only worth the money if it can still be told apart from the next batch.
    built_with: str = ""

    # Which other world this case is set in, if any, and who is on their way
    # there instead of the police (D-182). Stamped by `generate` from the deal,
    # never written by the model, and empty on every case made before worlds
    # existed, which the page reads as the present day and the police.
    world: str = ""
    authority: str = ""
    # Where the killer was dealt to stand in the house (D-188), by key. Stamped
    # like `world`, so `--stats` can say how often the model lands it.
    killer_position: str = ""
    # Whether the deal said the body was moved next door (D-193). Stamped.
    moved_body: bool = False
    # What happened and why, in a paragraph, written first with the skeleton
    # (D-191). The prose stage writes from it. Never shown to a player.
    premise: str = ""
    # What the calls that made this case cost, in dollars, rejected ones not
    # included: those are in `var/rejected` with their own price (D-191).
    spent_usd: float = 0.0
    # The language the case is written in, when it is not English: set by
    # `--translate` on the copy it makes, never by the model (D-208).
    language: str = ""

    def accounts_of(self, constraint: str) -> list[Account]:
        return [a for a in self.accounts if a.constraint == constraint]

    @property
    def false_claim(self) -> FalseClaim | None:
        """The killer's lie, which is the one the case turns on.

        Everything that asks about "the lie" means this one: the alibi analysis,
        the reveal, and the advisory that checks the killer has a story to
        break. Kept as a property so those readers did not all have to learn
        about the list (D-063).
        """
        if not self.killer:
            return None
        # The killer may tell two (D-207); the one the case turns on is the
        # one about the hour of the killing, when there is one.
        scene = self.murder_scene
        lies = self.lies_by(self.killer)
        at_hour = next((c for c in lies if scene is not None and c.slot == scene.slot), None)
        return at_hour or (lies[0] if lies else None)

    def lie_by(self, character: CharacterId) -> "FalseClaim | None":
        return next((c for c in self.false_claims if c.character == character), None)

    def lies_by(self, character: CharacterId) -> "list[FalseClaim]":
        """Every lie this person tells: one, or for a killer dealt the earlier
        lie, two (D-207)."""
        return [c for c in self.false_claims if c.character == character]

    @property
    def found_in(self) -> "PlaceId | None":
        """Where the body was found: the discovery's room, else where it fell."""
        if self.discovery is not None and self.discovery.place:
            return self.discovery.place
        scene = self.murder_scene
        return scene.place if scene is not None else None

    @property
    def found_with(self) -> "list[Thing]":
        """What lay in the room with the body when it was found (D-199).

        The first thing anyone at the door would be told, and the natural first
        question about an object: when did that get there? Read off the paths,
        at the last hour, in the room of the finding.
        """
        room = self.found_in
        if room is None or not self.slots:
            return []
        last = self.slots[-1].id
        return [t for t in self.things if t.where.get(last) == room]

    @property
    def body_moved(self) -> bool:
        """Killed in one room, found in another (D-193). The killer carried the
        body next door in the hour of the killing.

        Only when the deal said so (`moved_body`, stamped like the world). Older
        cases sometimes found the body somewhere else for reasons of their own,
        a fall from an aircraft, and were valid as written."""
        scene = self.murder_scene
        return bool(
            self.moved_body
            and scene is not None
            and scene.place
            and self.discovery is not None
            and self.discovery.place
            and self.discovery.place != scene.place
        )

    @property
    def murder_scene(self) -> "Constraint | None":
        """The constraint in which the killer kills the victim.

        There was no single answer to this and it cost two generated cases
        (D-071). Four modules each looked for "a constraint containing the
        killer and the victim" and each took the *first* one in list order,
        which is only the murder if the model happened to write it first. A good
        case usually has an earlier private scene between those two, because the
        threat that causes the murder is the best reason for one, and the prompt
        asks for exactly that. So half the time the earlier confrontation was
        treated as the killing: the body was laid to rest before it died, every
        later scene became a scene with a corpse in it, and the validator
        rejected a case that was fine.

        Resolution order. An explicit `murder` id wins, because a model that
        tells us is better than us guessing. Otherwise, the latest exclusive
        scene between the two of them, which is not a guess but the invariant
        the whole timeline rests on: after the murder the victim meets nobody,
        so the last time they were alone together is the last time they could
        have been.
        """
        if not (self.killer and self.victim):
            return None

        candidates = [
            c for c in self.constraints if self.killer in c.people and self.victim in c.people
        ]
        if not candidates:
            return None

        named = next((c for c in candidates if c.id == self.murder), None)
        if named is not None:
            return named

        order = {slot.id: slot.index for slot in self.slots}
        return max(candidates, key=lambda c: (c.exclusive, order.get(c.slot or "", -1)))

    @property
    def murder_slot(self) -> SlotId | None:
        scene = self.murder_scene
        return scene.slot if scene else None

    def who_is_in(self, place: PlaceId, slot: SlotId) -> set[CharacterId]:
        """Everyone the timeline puts in `place` during `slot`.

        The grid is stored character-first because that is how it is written and
        read. This is the other direction, which the rules need constantly.
        """
        return {
            character
            for character, by_slot in self.placements.items()
            if by_slot.get(slot) == place
        }
