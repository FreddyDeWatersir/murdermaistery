"""A session that has to survive leaving the process.

A dict can hold objects. A file, a table and a network hold bytes, so the
question these tests answer is whether an evening is still the same evening
after it has been through that conversion (D-080).
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from mystery.example import OPENING_NIGHT
from mystery.interrogation import Assertion, Statement
from mystery.models import Mystery
from mystery.session import FileSessions, Session
from mystery.solver import solve
from mystery.web import Case, build_app

CASE = Case(solve(Mystery.model_validate(OPENING_NIGHT), seed=0), id="opening-night")


def _evening() -> Session:
    session = Session(case_id="opening-night")
    session.transcript.record(
        Statement(
            round=1,
            speaker="ilse",
            question="Where were you at nine?",
            speech="The dressing corridor, all evening.",
            assertions=[Assertion(subject="ilse", slot="s1", place="dressing_corridor")],
            cited=["self:s1"],
        )
    )
    session.transcript.record(
        Statement(
            round=2,
            speaker="nadia",
            question="And Ilse?",
            speech="She was at the stage door. I saw her.",
            assertions=[Assertion(subject="ilse", slot="s1", place="stage_door")],
            cited=["saw:ilse@s1"],
        )
    )
    return session


# --- becoming a record and coming back --------------------------------------


def test_an_evening_survives_the_round_trip() -> None:
    back = Session.from_record(_evening().to_record())

    assert back.transcript.rounds == 2
    assert [s.speaker for s in back.transcript.statements] == ["ilse", "nadia"]


def test_the_contradiction_survives_too() -> None:
    """The assertions are the part that matters. Prose that comes back without
    its structure is a transcript rather than a notebook."""
    back = Session.from_record(_evening().to_record())

    conflicts = back.transcript.contradictions()
    assert len(conflicts) == 1
    assert conflicts[0].subject == "ilse"


def test_what_was_cited_survives() -> None:
    """Which decides what is on the charge sheet at the end (D-065)."""
    back = Session.from_record(_evening().to_record())

    assert back.transcript.statements[1].cited == ["saw:ilse@s1"]


def test_a_record_is_plain_data() -> None:
    """If it will not turn into JSON it will not go in a table."""
    import json

    json.dumps(_evening().to_record())


# --- the store --------------------------------------------------------------


def test_a_session_written_to_disk_comes_back(tmp_path) -> None:
    store = FileSessions(tmp_path)
    store.save(_evening())

    back = store.get(_evening().id)
    assert back is None, "different session, different id"

    session = _evening()
    store.save(session)
    assert store.get(session.id).transcript.rounds == 2


def test_an_unknown_session_is_not_found(tmp_path) -> None:
    assert FileSessions(tmp_path).get("nobody") is None


def test_a_session_id_cannot_name_a_file_of_its_own_choosing(tmp_path) -> None:
    """The id arrives from a cookie, which is to say from a stranger."""
    store = FileSessions(tmp_path)
    store.save(Session(id="../../etc/passwd", case_id="x"))

    assert not (tmp_path.parent / "etc").exists()
    assert list(tmp_path.glob("*.json"))


def test_an_expired_evening_is_gone(tmp_path) -> None:
    store = FileSessions(tmp_path)
    old = _evening()
    old.expires = int((datetime.now(UTC) - timedelta(hours=1)).timestamp())
    store.save(old)

    assert store.get(old.id) is None


def test_a_corrupt_file_is_not_a_crash(tmp_path) -> None:
    store = FileSessions(tmp_path)
    session = _evening()
    store.save(session)
    (tmp_path / f"{session.id}.json").write_text("{ not json", encoding="utf-8")

    assert store.get(session.id) is None


def test_the_notebook_survives_a_restart(tmp_path) -> None:
    """The whole point, end to end: same store, new server, same evening."""
    def answers(system, question):
        return {"speech": "The green room.", "used": ["self:s3"], "refused": False}

    store = FileSessions(tmp_path)
    player = TestClient(build_app(CASE, answers, sessions=store))
    player.post("/ask", json={"who": "ilse", "text": "Where were you?"})

    restarted = TestClient(build_app(CASE, answers, sessions=FileSessions(tmp_path)))
    restarted.cookies.update(player.cookies)

    assert restarted.get("/state").json()["notebook"]["questions"] == 1
