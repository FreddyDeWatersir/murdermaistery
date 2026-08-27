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


class Claim(BaseModel):
    """Where somebody says they were, which is not where they were.

    Without this the killer has nothing to lie about, and an interrogation game
    where nobody lies about their movements is a reading exercise.
    """

    character: CharacterId
    place: PlaceId
    slot: SlotId


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
    false_claim: Claim | None = None

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
