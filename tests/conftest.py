"""Shared fixtures.

pytest loads conftest.py automatically. Anything decorated with @pytest.fixture
here is available to every test file in this directory and below, with no import
needed. A test asks for a fixture by naming it as a parameter.

These two are built in Python. Once there are more than a handful they move to
JSON files under tests/fixtures/ and get loaded, because the corpus of bad
mysteries is meant to be readable as data rather than as code.
"""

import pytest

from mystery.models import Character, Event, Mystery, Place, Slot

CHARACTERS = [
    Character(id="bram", name="Bram Kessels"),
    Character(id="tomas", name="Tomas Behr"),
    Character(id="nadia", name="Nadia Groot"),
]

PLACES = [
    Place(id="green_room", name="Green Room"),
    Place(id="stage_door", name="Stage Door"),
]

SLOTS = [
    Slot(id="s1", label="20:40", index=0),
    Slot(id="s2", label="21:00", index=1),
]

CONFRONTATION = Event(
    id="bram_sacks_tomas",
    slot="s1",
    place="green_room",
    participants=["bram", "tomas"],
    description="Bram tells Tomas this is his last production here. Nadia hears it.",
)


def _fragment(placements: dict[str, dict[str, str]]) -> Mystery:
    return Mystery(
        title="Opening Night (fragment)",
        characters=CHARACTERS,
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        events=[CONFRONTATION],
    )


@pytest.fixture
def prototype_02_bug() -> Mystery:
    """The actual defect from the hand-built prototype 02.

    The confrontation is written as happening in the green room at 20:40, but
    the movement grid puts Tomas at the stage door in that slot. Both statements
    were written by hand, both were reread, and neither was noticed. It surfaced
    only when a player asked a question that touched it mid-game.
    """
    return _fragment(
        {
            "bram": {"s1": "green_room", "s2": "green_room"},
            "tomas": {"s1": "stage_door", "s2": "green_room"},
            "nadia": {"s1": "green_room", "s2": "green_room"},
        }
    )


@pytest.fixture
def coherent_fragment() -> Mystery:
    """The same fragment with Tomas where the confrontation says he was."""
    return _fragment(
        {
            "bram": {"s1": "green_room", "s2": "green_room"},
            "tomas": {"s1": "green_room", "s2": "green_room"},
            "nadia": {"s1": "green_room", "s2": "green_room"},
        }
    )
