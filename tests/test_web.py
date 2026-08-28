"""Tests for the notebook the player actually reads.

The web module is mostly plumbing and an embedded page, neither of which is
worth testing. What is worth testing is the one piece of real logic in it: the
timeline the Map tab draws, which turns a pile of statements into a grid of
rooms, hours and initials (D-062). It is the only place in the project where the
player's evidence is reshaped rather than passed along, and reshaping is where
things quietly go wrong.

No model and no server here. A Game takes any responder, so the responder is a
function that returns a fixed line.
"""

import json

from mystery.models import FalseClaim
from mystery.web import Game, _initials
from test_agent import CASE


class Person:
    """The only thing _initials looks at is id and name."""

    def __init__(self, id: str, name: str) -> None:
        self.id, self.name = id, name


def test_initials_are_first_and_last():
    tags = _initials([Person("a", "Ilse Vermeer"), Person("b", "Tomas Behr")])
    assert tags == {"a": "IV", "b": "TB"}


def test_a_single_name_gets_two_letters():
    assert _initials([Person("a", "Nadia")]) == {"a": "NA"}


def test_colliding_tags_grow_apart():
    """Two identical squares in the grid would be worse than no grid at all."""
    tags = _initials([Person("a", "Ilse Vermeer"), Person("b", "Iris Vermeer")])
    assert tags["a"] != tags["b"]
    assert tags["a"] == "IV" and tags["b"].startswith("IV")


def responder_saying(speech: str, used: list[str]):
    return lambda system, question: {"speech": speech, "used": used, "refused": False}


def test_an_unquestioned_cast_is_entirely_unaccounted_for():
    game = Game(CASE, responder_saying("", []))
    book = game.notebook()

    assert book["timeline"] == {}
    for slot in CASE.slots:
        # Four people, nobody asked, so every one of them is a hole.
        assert len(book["missing"][slot.id]) == len(CASE.characters)


def test_an_answer_puts_a_tag_in_a_room():
    game = Game(CASE, responder_saying("The study, all evening.", ["self:s1"]))
    game.ask("vera", "Where were you?")
    book = game.notebook()

    placed = book["timeline"]["s1"]["study"]
    assert [p["tag"] for p in placed] == ["VE"]
    # She said it about herself, so nothing corroborates it yet.
    assert placed[0]["firm"] is False
    assert placed[0]["disputed"] is False
    assert "VE" not in {p["tag"] for p in book["missing"]["s1"]}
    assert "OT" in {p["tag"] for p in book["missing"]["s1"]}


def test_two_people_placing_someone_in_two_rooms_is_disputed():
    """The one thing the grid exists to show: a person in two places at once.

    Which needs a liar, so this case has one. Otto claims the hall for the
    middle hour and was in the study, where two people saw him.
    """
    case = CASE.model_copy(
        update={
            "placements": {
                "otto": {"s0": "hall", "s1": "study", "s2": "cellar"},
                "magnus": {"s0": "hall", "s1": "hall", "s2": "cellar"},
                "vera": {"s0": "study", "s1": "study", "s2": "hall"},
                "clara": {"s0": "study", "s1": "study", "s2": "hall"},
            },
            "false_claims": [FalseClaim(character="otto", place="hall", slot="s1")],
        }
    )

    game = Game(case, responder_saying("Otto was with us in the study.", ["saw:otto@s1"]))
    game.ask("vera", "Where was Otto?")
    game.responder = responder_saying("The hall, the whole time.", ["self:s1"])
    game.ask("otto", "Where were you?")

    book = game.notebook()
    otto = [p for room in book["timeline"]["s1"].values() for p in room if p["tag"] == "OT"]

    assert len(otto) == 2, "he should appear in both rooms, not be silently merged"
    assert all(p["disputed"] for p in otto)


def test_a_second_witness_firms_a_claim_up():
    game = Game(CASE, responder_saying("Vera was in the hall with me.", ["saw:vera@s2"]))
    game.ask("clara", "Where was Vera?")
    game.responder = responder_saying("The hall.", ["self:s2"])
    game.ask("vera", "Where were you?")

    hall = game.notebook()["timeline"]["s2"]["hall"]
    vera = next(p for p in hall if p["tag"] == "VE")
    assert vera["firm"] is True, "two independent sources, not one"
    assert vera["disputed"] is False


# --- the accusation asks for a reason (D-065) -------------------------------


def _played(case, script):
    """A game where each character says one scripted thing when asked."""
    game = Game(case, lambda system, question: {"speech": "", "used": [], "refused": False})
    for who, used in script:
        game.responder = lambda system, question, used=used: {
            "speech": "...",
            "used": used,
            "refused": False,
        }
        game.ask(who, "Well?")
    return game


def test_a_secret_you_never_surfaced_is_not_on_the_charge_sheet() -> None:
    """You cannot offer a motive you did not find. Otherwise the list of
    options is itself the answer."""
    game = _played(CASE, [])

    assert game.notebook()["found"] == []


def test_hearing_a_secret_from_somebody_else_surfaces_it() -> None:
    """Clara knows Otto's motive without it being hers, so she can tell you."""
    game = _played(CASE, [("clara", ["heard:motive"])])

    assert [f["id"] for f in game.notebook()["found"]] == ["motive"]


def test_the_right_person_for_the_right_reason() -> None:
    game = _played(CASE, [("clara", ["heard:motive"])])

    verdict = game.accuse("otto", "motive")

    assert verdict["correct"] and verdict["right_reason"]


def test_the_right_person_for_no_reason_at_all() -> None:
    """The ending the one-bit accusation could not express: you named him, and
    you never found out why."""
    game = _played(CASE, [])

    verdict = game.accuse("otto", None)

    assert verdict["correct"]
    assert not verdict["right_reason"]
    assert verdict["offered"] is None


def test_a_motive_you_never_heard_does_not_count_even_if_it_is_right() -> None:
    """Guessing the id is not knowing it."""
    game = _played(CASE, [])

    verdict = game.accuse("otto", "motive")

    assert verdict["correct"]
    assert not verdict["right_reason"], "you never got it out of anybody"


def test_the_wrong_reason_is_reported_back() -> None:
    game = _played(CASE, [("vera", ["secret:affair"]), ("clara", ["heard:motive"])])

    verdict = game.accuse("otto", "affair")

    assert verdict["correct"]
    assert not verdict["right_reason"]
    assert "Vera and Otto" in verdict["offered"]


def test_what_you_missed_is_measured_by_what_came_out() -> None:
    """Not by whether the holder happened to get mentioned. The old version
    counted a secret as found because somebody put its holder in a room."""
    game = _played(CASE, [("clara", ["heard:motive"])])

    missed = game.accuse("otto", "motive")["missed"]

    assert not any("threatened to expose" in m for m in missed)
    assert any("Vera and Otto" in m for m in missed)


# --- backdrops are optional and never load-bearing (D-069) ------------------


def _app_for(game):
    from fastapi.testclient import TestClient

    from mystery.web import build_app

    return TestClient(build_app(game))


def test_a_game_without_backdrops_offers_none() -> None:
    state = _app_for(_played(CASE, [])).get("/state").json()

    assert state["scene"] is None
    assert all(p["scene"] is None for p in state["places"])


def test_a_game_with_backdrops_points_at_them() -> None:
    game = _played(CASE, [])
    game.case.scenery = {"setting": "setting.png", "hall": "hall.png"}

    state = _app_for(game).get("/state").json()

    assert state["scene"] == "/scene/setting.png"
    by_id = {p["id"]: p["scene"] for p in state["places"]}
    assert by_id["hall"] == "/scene/hall.png"
    assert by_id["study"] is None, "a room with no picture must not claim one"


def test_asking_for_a_backdrop_that_is_not_there_is_a_404_not_a_crash() -> None:
    """Decoration must never be able to take the game down with it."""
    assert _app_for(_played(CASE, [])).get("/scene/setting.png").status_code == 404


# --- what the browser is allowed to know (D-074) ----------------------------


def test_the_browser_is_never_told_what_anybody_wants() -> None:
    """A tooltip on the cast chips was showing every suspect's private motive.

    `wants` is the thing the player is supposed to work out, and it was one
    hover away. The fix is not to stop drawing the tooltip: it is that the
    browser has no business receiving the field at all.
    """
    state = _app_for(_played(CASE, [])).get("/state").json()
    everything = json.dumps(state)

    for character in CASE.characters:
        if character.wants:
            assert character.wants not in everything, character.id
        if character.manner:
            assert character.manner not in everything, character.id


def test_the_browser_is_told_who_these_people_are() -> None:
    """What replaced it: the public half, which is printed under their name."""
    roles = {"vera": "The housekeeper", "clara": "His sister"}
    introduced = CASE.model_copy(
        update={
            "characters": [
                c.model_copy(update={"role": roles.get(c.id, "A guest")})
                for c in CASE.characters
            ]
        }
    )

    state = _app_for(_played(introduced, [])).get("/state").json()
    by_id = {s["id"]: s["role"] for s in state["suspects"]}

    assert by_id["vera"] == "The housekeeper"
    assert by_id["clara"] == "His sister"
