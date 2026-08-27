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
    id: CharacterId
    name: str


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


class Mystery(BaseModel):
    title: str
    characters: list[Character]
    places: list[Place]
    slots: list[Slot]
    placements: dict[CharacterId, dict[SlotId, PlaceId]] = Field(default_factory=dict)
    constraints: list[Constraint] = Field(default_factory=list)

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
