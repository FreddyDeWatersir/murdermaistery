"""Ground truth data model for a mystery.

Design note, see docs/decisions.md D-021 and D-011.

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
    times (findings F3, decision D-011). No rule uses it yet; it is here so the
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


class Event(BaseModel):
    """Something that happened, at a place, in a slot, to specific people.

    This is the second description of the same world. The timeline says where
    everyone was; events say what occurred. Nothing forces the two to agree,
    which is exactly where rule V1 lives.
    """

    id: str
    slot: SlotId
    place: PlaceId
    participants: list[CharacterId]
    description: str = ""


class Mystery(BaseModel):
    title: str
    characters: list[Character]
    places: list[Place]
    slots: list[Slot]
    placements: dict[CharacterId, dict[SlotId, PlaceId]]
    events: list[Event] = Field(default_factory=list)
