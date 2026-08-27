"""Shared fixtures.

pytest loads conftest.py automatically. Anything decorated with @pytest.fixture
here is available to every test file in this directory and below, with no import
needed. A test asks for a fixture by naming it as a parameter.

These are built in Python. Once there are more than a handful they move to JSON
files under tests/fixtures/ and get loaded, because the corpus of bad mysteries
is meant to be readable as data rather than as code.
"""

import pytest

from mystery.models import Character, Constraint, Mystery, Place, Slot

CHARACTERS = [
    Character(id="bram", name="Bram Kessels"),
    Character(id="tomas", name="Tomas Behr"),
    Character(id="nadia", name="Nadia Groot"),
    Character(id="wouter", name="Wouter Damen"),
]

PLACES = [
    Place(id="green_room", name="Green Room"),
    Place(id="stage_door", name="Stage Door"),
    Place(id="prop_store", name="Prop Store"),
]

SLOTS = [
    Slot(id="s1", label="20:40", index=0),
    Slot(id="s2", label="21:00", index=1),
]

CONFRONTATION = Constraint(
    id="bram_sacks_tomas",
    people=["bram", "tomas"],
    place="green_room",
    slot="s1",
    description="Bram tells Tomas this is his last production here. Nadia hears it.",
)

MURDER = Constraint(
    id="murder",
    people=["wouter", "bram"],
    exclusive=True,
    place="prop_store",
    slot="s2",
    description="Wouter kills Bram during the interval.",
)

# "Tomas has no alibi for the interval." One person, exclusive, and it does not
# say where. No separate Alone type is needed (D-024).
TOMAS_ALONE = Constraint(
    id="tomas_has_no_alibi",
    people=["tomas"],
    exclusive=True,
    description="Tomas is by himself during the interval, and knows how it looks.",
)


def _fragment(placements: dict[str, dict[str, str]], constraints: list[Constraint]) -> Mystery:
    return Mystery(
        title="Opening Night (fragment)",
        characters=CHARACTERS,
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        constraints=constraints,
    )


COHERENT_GRID = {
    "bram": {"s1": "green_room", "s2": "prop_store"},
    "tomas": {"s1": "green_room", "s2": "green_room"},
    "nadia": {"s1": "green_room", "s2": "green_room"},
    "wouter": {"s1": "prop_store", "s2": "prop_store"},
}


@pytest.fixture
def prototype_02_bug() -> Mystery:
    """The actual defect from the hand-built prototype 02.

    The confrontation is written as happening in the green room at 20:40, but
    the movement grid puts Tomas at the stage door in that slot. Both statements
    were written by hand, both were reread, and neither was noticed. It surfaced
    only when a player asked a question that touched it mid-game.
    """
    return _fragment(
        COHERENT_GRID | {"tomas": {"s1": "stage_door", "s2": "green_room"}},
        [CONFRONTATION],
    )


@pytest.fixture
def coherent_fragment() -> Mystery:
    """The same fragment with Tomas where the confrontation says he was."""
    return _fragment(COHERENT_GRID, [CONFRONTATION])


@pytest.fixture
def murder_with_a_bystander() -> Mystery:
    """A murder the solver placed correctly and then ruined.

    Wouter and Bram are both in the prop store at 21:00, so V1 is satisfied. But
    Nadia is standing there too, which means the murder had a witness and the
    case is dead before it starts.
    """
    return _fragment(
        COHERENT_GRID | {"nadia": {"s1": "green_room", "s2": "prop_store"}},
        [MURDER],
    )


@pytest.fixture
def private_murder() -> Mystery:
    """The same murder with the room to itself."""
    return _fragment(COHERENT_GRID, [MURDER])


@pytest.fixture
def unplaced_constraint() -> Mystery:
    """A mystery the solver did not finish.

    The grid is internally fine. The story simply did not get everything it
    asked for: nowhere was found to put Tomas by himself.
    """
    return _fragment(COHERENT_GRID, [MURDER, TOMAS_ALONE])


@pytest.fixture
def solved_alone_constraint() -> Mystery:
    """The same, with the solver having bound Tomas alone in the green room."""
    return _fragment(
        COHERENT_GRID | {"nadia": {"s1": "green_room", "s2": "stage_door"}},
        [
            MURDER,
            TOMAS_ALONE.model_copy(update={"place": "green_room", "slot": "s2"}),
        ],
    )
