"""Two people, one case, two notebooks.

This is the property the deployed game needs and the local one never had
(D-077). Everything here runs against `InMemorySessions`, which is the point:
whatever ends up behind the boundary has to pass exactly these.
"""

from fastapi.testclient import TestClient

from mystery.example import OPENING_NIGHT
from mystery.models import Mystery
from mystery.session import InMemorySessions, Session
from mystery.solver import solve
from mystery.web import Case, Game, build_app

CASE = Case(solve(Mystery.model_validate(OPENING_NIGHT), seed=0), id="opening-night")


def _answers(system, question):
    ids = [
        line.strip()[1:].split("]")[0]
        for line in system.splitlines()
        if line.strip().startswith("[")
    ]
    return {"speech": "As I said.", "used": ids[:1], "refused": False}


# --- the store --------------------------------------------------------------


def test_a_new_session_is_empty_and_unguessable() -> None:
    store = InMemorySessions()
    session = store.create("opening-night")

    assert session.transcript.rounds == 0
    assert not session.solved
    assert len(session.id) > 12, "a session id is the only lock on a notebook"


def test_two_sessions_of_one_case_do_not_share_an_id() -> None:
    store = InMemorySessions()

    assert store.create("a").id != store.create("a").id
    assert store.count() == 2


def test_a_session_that_was_never_started_is_not_found() -> None:
    assert InMemorySessions().get("made-up") is None


# --- the case is shared, the play is not -------------------------------------


def test_one_case_serves_two_players_without_mixing_them() -> None:
    """The bug that could not be configured away: one process, one transcript,
    and two strangers filling in each other's timeline."""
    app = build_app(CASE, _answers)
    ilse, tomas = TestClient(app), TestClient(app)

    ilse.post("/ask", json={"who": "ilse", "text": "Where were you?"})
    ilse.post("/ask", json={"who": "nadia", "text": "And you?"})
    tomas.post("/ask", json={"who": "renske", "text": "Where were you?"})

    assert ilse.get("/state").json()["notebook"]["questions"] == 2
    assert tomas.get("/state").json()["notebook"]["questions"] == 1


def test_one_player_accusing_does_not_end_anybody_elses_evening() -> None:
    app = build_app(CASE, _answers)
    quick, slow = TestClient(app), TestClient(app)

    quick.post("/accuse", json={"who": "tomas"})

    assert slow.post("/ask", json={"who": "ilse", "text": "Well?"}).status_code == 200


def test_coming_back_with_the_same_cookie_is_the_same_evening() -> None:
    app = build_app(CASE, _answers)
    player = TestClient(app)

    player.post("/ask", json={"who": "ilse", "text": "Where were you?"})
    again = player.get("/state").json()["notebook"]

    assert again["questions"] == 1, "a returning player keeps their notebook"


def test_the_case_is_built_once_and_shared() -> None:
    """Briefs are per character, not per player. Two people asking the same
    suspect the same question are entitled to the same facts."""
    app = build_app(CASE, _answers)
    one, two = TestClient(app), TestClient(app)

    one.get("/state")
    two.get("/state")

    assert one.get("/state").json()["suspects"] == two.get("/state").json()["suspects"]


def test_together_puts_everyone_in_one_notebook() -> None:
    """The old behaviour, kept on purpose. Two people in a room with one case
    between them want to share what they have found."""
    app = build_app(CASE, _answers, together=True)
    you, friend = TestClient(app), TestClient(app)

    you.post("/ask", json={"who": "ilse", "text": "Where were you?"})

    assert friend.get("/state").json()["notebook"]["questions"] == 1


def test_a_game_still_works_and_means_together() -> None:
    """Everything that had one Game and served it keeps working."""
    game = Game(CASE, _answers, session=Session(case_id="opening-night"))
    app = build_app(game)

    TestClient(app).post("/ask", json={"who": "ilse", "text": "Where were you?"})

    assert game.transcript.rounds == 1


def test_a_session_does_not_follow_you_into_a_different_case() -> None:
    """From a real session record (D-107): `case_id` said one case and ninety
    seven of its hundred and one questions belonged to another. Two cases served
    on the same port in the same browser shared a cookie, and the transcript,
    the notebook and the gossip all ran across both."""
    from fastapi.testclient import TestClient

    from mystery.session import InMemorySessions
    from mystery.web import Case, build_app

    store = InMemorySessions()
    client = TestClient(build_app(CASE, _answers, sessions=store))
    client.post("/ask", json={"who": "ilse", "text": "Where were you?"})
    assert client.get("/state").json()["notebook"]["questions"] == 1

    # Same browser, same cookie jar, a different case on the same port.
    elsewhere = Case(CASE.mystery, id="the-ferry")
    second = TestClient(build_app(elsewhere, _answers, sessions=store))
    second.cookies = client.cookies
    started_fresh = second.get("/state").json()["notebook"]["questions"]

    assert started_fresh == 0, "the old evening followed the player into a new case"


def test_the_same_case_still_remembers_you() -> None:
    """The fix must not throw away a session on every page load."""
    from fastapi.testclient import TestClient

    from mystery.session import InMemorySessions
    from mystery.web import build_app

    store = InMemorySessions()
    client = TestClient(build_app(CASE, _answers, sessions=store))
    client.post("/ask", json={"who": "ilse", "text": "Where were you?"})

    again = TestClient(build_app(CASE, _answers, sessions=store))
    again.cookies = client.cookies

    assert again.get("/state").json()["notebook"]["questions"] == 1
