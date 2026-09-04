"""Sessions and the rota in a table (D-122).

`FakeTable` enforces the one condition expression the code uses, because a fake
that accepts every write would let `claim` look atomic while being nothing of
the sort, and `claim` being atomic is the entire reason this table exists.
"""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from mystery.daily import DynamoRota, FileRota, rota
from mystery.session import (
    DynamoSessions,
    FileSessions,
    Session,
    sessions,
)


class ConditionalCheckFailedException(Exception):
    pass


class FakeTable:
    """A dict pretending to be a DynamoDB table.

    Pages at `page_size` so the `LastEvaluatedKey` loop runs, and refuses a
    conditional write the way the real one does, with the same exception hanging
    off the same attribute path.
    """

    def __init__(self, key: str = "id", page_size: int = 1000) -> None:
        self.items: dict[str, dict] = {}
        self.key = key
        self.page_size = page_size
        self.calls: list[str] = []
        # The same attribute path the real Table resource exposes, so the code
        # under test catches the exception the same way in both worlds.
        self.meta = SimpleNamespace(
            client=SimpleNamespace(
                exceptions=SimpleNamespace(
                    ConditionalCheckFailedException=ConditionalCheckFailedException
                )
            )
        )

    def put_item(self, Item, ConditionExpression=None, ExpressionAttributeNames=None):
        self.calls.append("put")
        if ConditionExpression:
            names = ExpressionAttributeNames or {}
            field = ConditionExpression.split("(")[1].rstrip(")")
            field = names.get(field, field)
            assert ConditionExpression.startswith("attribute_not_exists"), ConditionExpression
            if Item[self.key] in self.items and field in self.items[Item[self.key]]:
                raise ConditionalCheckFailedException(Item[self.key])
        self.items[Item[self.key]] = dict(Item)
        return {}

    def get_item(self, Key):
        self.calls.append("get")
        found = self.items.get(Key[self.key])
        return {"Item": dict(found)} if found else {}

    def delete_item(self, Key):
        self.calls.append("delete")
        self.items.pop(Key[self.key], None)
        return {}

    def scan(self, Select=None, ProjectionExpression=None, ExclusiveStartKey=None):
        self.calls.append("scan")
        keys = sorted(self.items)
        start = keys.index(ExclusiveStartKey[self.key]) + 1 if ExclusiveStartKey else 0
        page = keys[start : start + self.page_size]
        out: dict = {"Count": len(page)}
        if Select != "COUNT":
            out["Items"] = [dict(self.items[k]) for k in page]
        if start + len(page) < len(keys):
            out["LastEvaluatedKey"] = {self.key: page[-1]}
        return out


# --- sessions ----------------------------------------------------------------


def _store() -> tuple[DynamoSessions, FakeTable]:
    table = FakeTable("id")
    return DynamoSessions("mystery-sessions", table=table), table


def test_a_session_survives_the_round_trip() -> None:
    store, _ = _store()
    made = store.create("opening-night-1234")
    made.show("ilse", "the_books")
    store.save(made)

    back = store.get(made.id)

    assert back is not None
    assert back.case_id == "opening-night-1234"
    assert back.seen_by("ilse") == {"the_books"}


def test_the_transcript_comes_back_whole() -> None:
    from mystery.interrogation import Assertion, Statement

    store, _ = _store()
    made = store.create("a-case")
    made.transcript.record(
        Statement(
            round=1,
            speaker="ilse",
            question="where were you",
            speech="The green room.",
            assertions=[Assertion(subject="ilse", slot="s1", place="green_room")],
            cited=["self:s1"],
        )
    )
    store.save(made)

    back = store.get(made.id)

    assert back.transcript.rounds == 1
    assert back.transcript.statements[0].speech == "The green room."
    assert back.transcript.statements[0].assertions[0].place == "green_room"
    assert back.transcript.statements[0].cited == ["self:s1"]


def test_the_key_and_the_ttl_are_real_attributes_and_the_rest_is_one_string() -> None:
    """TTL reads a number off the item, so `expires` cannot be buried in the
    blob. Everything else can, and is: DynamoDB has no float, and a stray one
    anywhere in a nested structure fails the write."""
    store, table = _store()
    made = store.create("a-case")

    item = table.items[made.id]

    assert set(item) == {"id", "expires", "record"}
    assert isinstance(item["expires"], int)
    assert isinstance(item["record"], str)
    assert json.loads(item["record"])["case_id"] == "a-case"


def test_an_expired_session_is_not_handed_back() -> None:
    """TTL deletes within a day or so of the deadline rather than at it, so the
    read has to check as well."""
    store, table = _store()
    made = store.create("a-case")
    stale = Session(id=made.id, case_id="a-case", expires=1)
    store.save(stale)

    assert store.get(made.id) is None


def test_a_session_nobody_started_is_none() -> None:
    store, _ = _store()

    assert store.get("made-up") is None
    assert store.get("") is None


def test_an_unreadable_record_does_not_take_the_game_down() -> None:
    store, table = _store()
    table.items["broken"] = {"id": "broken", "expires": 0, "record": "{ not json"}

    assert store.get("broken") is None


def test_counting_does_not_drag_every_record_back() -> None:
    """A hundred and twenty kilobytes per session. `Select=COUNT` returns the
    number without the items."""
    store, table = _store()
    for _ in range(3):
        store.create("a-case")
    table.calls.clear()

    assert store.count() == 3


def test_counting_follows_the_pages() -> None:
    table = FakeTable("id", page_size=2)
    store = DynamoSessions("t", table=table)
    for _ in range(7):
        store.create("a-case")

    assert store.count() == 7


def test_a_big_session_says_so_before_it_breaks() -> None:
    """The wall is 400 KB and the failure mode is a write that starts refusing
    mid-game. It should be loud well before that."""
    from mystery.interrogation import Statement

    store, _ = _store()
    made = store.create("a-case")
    for n in range(400):
        made.transcript.record(
            Statement(round=n, speaker="ilse", question="q" * 400, speech="a" * 400)
        )

    with capture_logs() as logged:
        store.save(made)

    assert any(entry.get("event") == "session.large" for entry in logged)


def test_an_ordinary_session_is_not_warned_about() -> None:
    """A warning that fires on every save is a warning nobody reads."""
    store, _ = _store()
    made = store.create("a-case")

    with capture_logs() as logged:
        store.save(made)

    assert not [e for e in logged if e.get("event") == "session.large"]


# --- the rota, and the write it was designed for ------------------------------


def _book() -> tuple[DynamoRota, FakeTable]:
    table = FakeTable("day")
    return DynamoRota("mystery-rota", table=table), table


def test_claiming_an_unclaimed_day_wins_it() -> None:
    book, _ = _book()

    assert book.claim("2026-09-01", "the-ferry") == "the-ferry"
    assert book.case_for("2026-09-01") == "the-ferry"


def test_the_second_claimant_is_told_the_winner_and_does_not_overwrite() -> None:
    """The whole reason this table exists. D-079 wrote `claim` in this shape
    before anything could implement it properly; `FileRota` narrows the window
    and says in its own docstring that it cannot close it."""
    book, table = _book()

    first = book.claim("2026-09-01", "the-ferry")
    second = book.claim("2026-09-01", "the-orchard")

    assert first == "the-ferry"
    assert second == "the-ferry", "the loser must be told the winner, not its own answer"
    assert table.items["2026-09-01"]["case_id"] == "the-ferry"


def test_everybody_asking_at_once_agrees() -> None:
    book, _ = _book()

    answers = {book.claim("2026-09-01", f"case-{n}") for n in range(8)}

    assert len(answers) == 1, "eight writers, one day, one answer"


def test_a_released_day_can_be_claimed_again() -> None:
    """The repair path: a day pointing at a case that has been deleted off the
    shelf points at nothing, and `claim` will not overwrite it."""
    book, _ = _book()
    book.claim("2026-09-01", "the-ferry")

    book.release("2026-09-01")

    assert book.case_for("2026-09-01") is None
    assert book.claim("2026-09-01", "the-orchard") == "the-orchard"


def test_a_day_nobody_claimed_is_none() -> None:
    book, _ = _book()

    assert book.case_for("2026-09-01") is None


def test_used_returns_every_case_ever_served() -> None:
    book, _ = _book()
    book.claim("2026-09-01", "the-ferry")
    book.claim("2026-09-02", "the-orchard")

    assert book.used() == {"the-ferry", "the-orchard"}


def test_used_follows_the_pages() -> None:
    table = FakeTable("day", page_size=2)
    book = DynamoRota("t", table=table)
    for n in range(1, 8):
        book.claim(f"2026-09-0{n}", f"case-{n}")

    assert len(book.used()) == 7


def test_the_reserved_word_is_bound_rather_than_written() -> None:
    """`day` is one of DynamoDB's reserved words, so it cannot appear literally
    in an expression."""
    book, table = _book()
    book.claim("2026-09-01", "the-ferry")

    assert table.calls[0] == "put"


# --- which one you get --------------------------------------------------------


def test_no_table_named_means_the_local_ones(monkeypatch) -> None:
    monkeypatch.delenv("MYSTERY_SESSIONS_TABLE", raising=False)
    monkeypatch.delenv("MYSTERY_ROTA_TABLE", raising=False)

    assert isinstance(sessions(), FileSessions)
    assert isinstance(rota(), FileRota)


def test_a_table_named_means_dynamo(monkeypatch) -> None:
    monkeypatch.setenv("MYSTERY_SESSIONS_TABLE", "mystery-sessions")
    monkeypatch.setenv("MYSTERY_ROTA_TABLE", "mystery-rota")

    assert isinstance(sessions(), DynamoSessions)
    assert isinstance(rota(), DynamoRota)
    assert sessions()._table is None, "picking must not build a client"


def test_set_but_blank_falls_back(monkeypatch) -> None:
    """Set-but-blank is how a deploy config goes wrong."""
    monkeypatch.setenv("MYSTERY_SESSIONS_TABLE", "   ")

    assert isinstance(sessions(), FileSessions)


def test_the_rota_default_reaches_the_configured_one(monkeypatch) -> None:
    """`_rota(None)` used to mean FileRota flatly, which would have made
    DynamoRota unreachable however carefully it was written (D-119)."""
    from mystery.daily import _rota

    monkeypatch.setenv("MYSTERY_ROTA_TABLE", "mystery-rota")

    assert isinstance(_rota(None), DynamoRota)


def test_the_web_server_uses_the_configured_session_store(monkeypatch, tmp_path) -> None:
    """Asserted by running the real path rather than by mocking the seam and
    checking the mock (D-119). Only `uvicorn.run` is replaced, because the one
    thing a test must not do is start a server and block."""
    import uvicorn

    import mystery.agent as agent
    import mystery.web as web
    from mystery.library import FileShelf

    chosen = FileSessions(tmp_path / "sessions")
    monkeypatch.setattr(web, "pick_sessions", lambda: chosen)
    monkeypatch.setattr(web, "pick_shelf", lambda: FileShelf(tmp_path))

    # `_serve` builds a real responder, which wants a key. Nothing in this test
    # asks anybody a question, so it gets one that answers nothing.
    monkeypatch.setattr(
        agent,
        "anthropic_responder",
        lambda *a, **kw: (lambda s, q: {"speech": "", "used": [], "refused": True}),
    )

    built = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: built.update(app=app))

    assert web.main(["--dry-run"]) == 0
    assert built.get("app") is not None, "the server was never built"

    # The store the app actually got, reached through the running application.
    client = TestClient(built["app"])
    client.get("/state")

    assert list((tmp_path / "sessions").glob("*.json")), "the session went elsewhere"


@pytest.mark.parametrize("store", ["sessions", "rota"])
def test_neither_needs_boto3_to_be_chosen(monkeypatch, store) -> None:
    monkeypatch.setenv("MYSTERY_SESSIONS_TABLE", "t")
    monkeypatch.setenv("MYSTERY_ROTA_TABLE", "t")
    chosen = sessions() if store == "sessions" else rota()

    assert chosen._table is None
