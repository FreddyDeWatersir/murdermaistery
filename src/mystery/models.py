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
    """

    id: PlaceId
    name: str
    within: PlaceId | None = None


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
    """

    id: str
    holder: CharacterId
    about: CharacterId | None = None
    summary: str
    known_by: list[CharacterId] = Field(default_factory=list)
    revealed_by: str | None = None
    breaks_when: str = ""
    is_motive: bool = False


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
    murder: str | None = None
    false_claims: list[FalseClaim] = Field(default_factory=list)
    # Somebody who says they did it and did not. Only some shapes of case have
    # one, so it is optional and means nothing when absent (D-067).
    false_confessor: CharacterId | None = None
    discovery: Discovery | None = None

    @property
    def false_claim(self) -> FalseClaim | None:
        """The killer's lie, which is the one the case turns on.

        Everything that asks about "the lie" means this one: the alibi analysis,
        the reveal, and the advisory that checks the killer has a story to
        break. Kept as a property so those readers did not all have to learn
        about the list (D-063).
        """
        return self.lie_by(self.killer) if self.killer else None

    def lie_by(self, character: CharacterId) -> "FalseClaim | None":
        return next((c for c in self.false_claims if c.character == character), None)

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
