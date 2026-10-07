"""Rooms (D-208): one process, one login per room, each its own game."""

import pytest
from fastapi.testclient import TestClient

from mystery.example import OPENING_NIGHT
from mystery.models import Mystery
from mystery.session import InMemorySessions
from mystery.solver import solve


def _answer(s, q):
    return {"speech": "", "used": [], "refused": True}


def _rooms(store):
    from mystery.web import Case, build_rooms

    case = Case(solve(Mystery.model_validate(OPENING_NIGHT)), id="opening")
    rooms = {"marco": {"case": "opening"}, "lucia": {"case": "opening"}}
    return build_rooms(rooms, _answer, store, lambda _id: case)


def test_each_login_gets_its_own_game_and_a_stranger_gets_none() -> None:
    store = InMemorySessions()
    client = TestClient(_rooms(store))

    marco = client.get("/state", headers={"X-Remote-User": "marco"})
    lucia = client.get("/state", headers={"X-Remote-User": "lucia"})
    assert marco.status_code == 200 and lucia.status_code == 200
    assert store.get("room-marco") is not None and store.get("room-lucia") is not None
    assert client.get("/state", headers={"X-Remote-User": "nobody"}).status_code == 403
    assert client.get("/state").status_code == 403


def test_a_room_keeps_its_game_across_a_restart() -> None:
    from mystery.web import room_session

    store = InMemorySessions()
    first = room_session(store, "marco", "opening")
    first.solved = True
    store.save(first)
    again = room_session(store, "marco", "opening")
    assert again.solved and again.id == "room-marco"
    # A different case in the same room is a fresh game.
    assert not room_session(store, "marco", "another").solved


def test_the_room_list_round_trips(tmp_path) -> None:
    from mystery.rooms import read, write

    path = tmp_path / "rooms.json"
    write({"marco": {"case": "x-it"}}, path)
    assert read(path) == {"marco": {"case": "x-it"}}
    assert read(tmp_path / "missing.json") == {}


@pytest.mark.parametrize(
    "name,ok",
    [("marco", True), ("Marco", False), ("a", False), ("lucia_2", True), ("../etc", False)],
)
def test_room_names_are_tame(name, ok) -> None:
    from mystery.rooms import NAME

    assert bool(NAME.match(name)) is ok
