"""Who is playing, and what they have found out.

Until now a game was one Python object in one process, shared by everybody who
connected. On a laptop over wifi that is a feature and a liked one: two people
solving something together want one notebook. On the internet it is a bug that
cannot be configured away, because two strangers would be filling in each
other's timeline and the first to accuse would end the evening for everyone
(D-077).

So the two halves come apart. A **case** is what was generated: the mystery, the
derived knowledge, the briefs, the pictures. It never changes once it exists and
everybody can share one. A **session** is one person's play-through of it: what
they have asked, what they have been told, whether they have accused anybody. It
changes constantly and belongs to one player.

`Sessions` is the boundary that will eventually have a database behind it. There
are two implementations here and the second one is the point of the first: the
in-memory store is what tests and local play use, and anything the deployed
version needs has to be expressible through the same four methods. That is the
same trick as the model boundary in D-002, and it is what makes the cloud work
a swap rather than a rewrite.
"""

import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import structlog

from mystery.interrogation import Assertion, Statement, Transcript

log = structlog.get_logger()


def new_id() -> str:
    """Unguessable, because a session id is the only thing standing between one
    player's notebook and anybody who fancies reading it."""
    return secrets.token_urlsafe(12)


# How long an unfinished evening is kept. Long enough that somebody who starts
# at midnight and comes back after work still has their notebook; short enough
# that abandoned ones do not accumulate for ever. This is the timer instinct
# from the design conversation, put where it belongs: on how long a record
# lives, not on which case anybody is allowed to play (D-080).
KEEP = timedelta(hours=48)


@dataclass
class Session:
    """One person's evening with one case."""

    id: str = field(default_factory=new_id)
    case_id: str = ""
    transcript: Transcript = field(default_factory=Transcript)
    solved: bool = False
    started: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    # Seconds since the epoch, which is an odd thing to carry until you know
    # that DynamoDB expires a record by reading exactly this shape out of an
    # attribute and deleting the row for free. A field written for a database
    # that does not exist yet, because the alternative is a migration later.
    expires: int = field(
        default_factory=lambda: int((datetime.now(UTC) + KEEP).timestamp())
    )
    # What has been put in front of whom (D-087). Per character on purpose: a
    # suspect's story changes because of what happened in *their* conversation,
    # never because the player learned something in another room. Showing
    # Teodora the ledger tells Teodora nothing about what Nicanor knows.
    shown: dict[str, list[str]] = field(default_factory=dict)

    def show(self, to: str, secret_id: str) -> None:
        held = self.shown.setdefault(to, [])
        if secret_id not in held:
            held.append(secret_id)

    def seen_by(self, who: str) -> set[str]:
        return set(self.shown.get(who, ()))

    def to_record(self) -> dict[str, Any]:
        """Plain data, ready for a file, a table, or anything else.

        A dict in a process can hold objects. Everything else holds bytes, so
        this is the line where a session stops being Python and starts being a
        record. Written by hand rather than pickled: a pickle is unreadable in a
        console, unversioned, and unwise to load from anywhere you do not fully
        control.
        """
        return {
            "id": self.id,
            "case_id": self.case_id,
            "solved": self.solved,
            "started": self.started,
            "expires": self.expires,
            "shown": {who: list(ids) for who, ids in self.shown.items()},
            "statements": [asdict(s) for s in self.transcript.statements],
        }

    @classmethod
    def from_record(cls, raw: dict[str, Any]) -> "Session":
        transcript = Transcript(
            statements=[
                Statement(
                    round=s["round"],
                    speaker=s["speaker"],
                    question=s["question"],
                    speech=s["speech"],
                    assertions=[Assertion(**a) for a in s.get("assertions", [])],
                    refused=s.get("refused", False),
                    cited=list(s.get("cited", [])),
                )
                for s in raw.get("statements", [])
            ]
        )
        return cls(
            id=raw["id"],
            case_id=raw.get("case_id", ""),
            transcript=transcript,
            solved=raw.get("solved", False),
            started=raw.get("started", ""),
            expires=raw.get("expires", 0),
            shown={who: list(ids) for who, ids in raw.get("shown", {}).items()},
        )

    @property
    def expired(self) -> bool:
        return bool(self.expires) and self.expires < datetime.now(UTC).timestamp()


class Sessions(Protocol):
    """Where play-throughs live.

    Four methods, deliberately. Anything that needs more than this to work is
    something the deployed version would have to do differently from the local
    one, which is exactly the coupling this exists to prevent.
    """

    def create(self, case_id: str) -> Session: ...

    def get(self, session_id: str) -> Session | None: ...

    def save(self, session: Session) -> None: ...

    def count(self) -> int: ...


class InMemorySessions:
    """A dict. Everything a laptop needs, and the shape everything else copies.

    Sessions are lost when the process stops, which is correct for local play:
    the case is on the shelf and can be started again, and nobody expects a
    half-finished interrogation to survive a reboot of their own computer.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create(self, case_id: str) -> Session:
        session = Session(case_id=case_id)
        self._sessions[session.id] = session
        log.info("session.started", session=session.id, case=case_id)
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def save(self, session: Session) -> None:
        # A dict holds the same object, so this is already done. It is here
        # because a store with a network behind it will need it, and code that
        # forgets to call it now is code that breaks then.
        self._sessions[session.id] = session

    def count(self) -> int:
        return len(self._sessions)


class FileSessions:
    """Sessions on disk, one JSON file each.

    Two jobs. It is the default for local play (D-092), so restarting the
    server does not throw away everybody's notebook mid-interrogation. And it
    is the second implementation of the boundary, which is the part that
    matters: a boundary with one implementation behind it is a guess about what
    the interface should be, and a boundary with two is an interface.

    One file per session, never one file holding all of them. Same argument as
    the rota (D-079): a document holding everything means every write rewrites
    everybody, and two writers erase each other.
    """

    def __init__(self, folder: Path = Path("var/sessions")) -> None:
        self.folder = folder

    def _path(self, session_id: str) -> Path:
        # A session id arrives from a cookie, which is to say from a stranger.
        # Anything that is not the alphabet we generate does not get to name a
        # file on this machine.
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        return self.folder / f"{safe}.json"

    def create(self, case_id: str) -> Session:
        session = Session(case_id=case_id)
        self.save(session)
        log.info("session.started", session=session.id, case=case_id)
        return session

    def get(self, session_id: str) -> Session | None:
        path = self._path(session_id)
        if not session_id or not path.exists():
            return None
        try:
            session = Session.from_record(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError, KeyError) as error:
            log.warning("session.unreadable", session=session_id, error=str(error))
            return None

        if session.expired:
            # A table would have deleted this itself. A directory will not, so
            # the read is where it gets noticed.
            log.info("session.expired", session=session_id)
            return None
        return session

    def save(self, session: Session) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(session.id).write_text(
            json.dumps(session.to_record(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def count(self) -> int:
        return len(list(self.folder.glob("*.json"))) if self.folder.exists() else 0


# The table this process writes to, or nothing, in which case the folder wins.
# Same shape as `MYSTERY_BUCKET`: one variable, read in one place, and a laptop
# that sets neither needs no AWS at all (D-122).
SESSIONS_TABLE = "MYSTERY_SESSIONS_TABLE"

# A DynamoDB item cannot exceed 400 KB. A played session of a hundred and
# thirty two questions came to 119 KB, about nine tenths of a kilobyte per
# statement, so the wall is somewhere near four hundred and forty questions.
# Nobody has come close, and a wall you cannot see is worse than one you can.
ITEM_LIMIT = 400_000
LOUD_AT = 0.75


class DynamoSessions:
    """Sessions in a table, one item each.

    `table` is injectable for the same reason every other boundary's client is:
    the suite passes a dictionary that behaves like a table and never touches a
    network (D-002, D-027, D-118).

    **The record goes in as one JSON string, deliberately.** DynamoDB has its own
    type system and boto3 maps Python onto it, which mostly works and then
    refuses a float, because DynamoDB has no float: it has `Decimal`, and a
    single stray one anywhere in a nested structure fails the write with an
    error that names the type and not the field. A session is written by
    `to_record` and read by `from_record` and is never queried by its contents,
    so there is nothing to gain by exploding it into attributes and one whole
    class of bug to avoid by not doing so.

    Two things stay real attributes. `id`, because it is the key, and `expires`,
    because TTL reads it: a number on the item, in epoch seconds, which DynamoDB
    uses to delete the row itself for free. `Session.expires` has been that shape
    since it was written, for exactly this.
    """

    def __init__(self, table_name: str = "", table=None, region: str | None = None) -> None:
        self.table_name = table_name
        self._table = table
        self._region = region

    @property
    def table(self):
        if self._table is None:
            import boto3

            self._table = boto3.resource(
                "dynamodb", region_name=self._region
            ).Table(self.table_name)
        return self._table

    def create(self, case_id: str) -> Session:
        session = Session(case_id=case_id)
        self.save(session)
        log.info("session.started", session=session.id, case=case_id)
        return session

    def get(self, session_id: str) -> Session | None:
        if not session_id:
            return None
        got = self.table.get_item(Key={"id": session_id})
        item = got.get("Item")
        if not item:
            return None

        try:
            session = Session.from_record(json.loads(item["record"]))
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            log.warning("session.unreadable", session=session_id, error=str(error))
            return None

        # TTL deletes within a day or so of the deadline rather than at it, so an
        # expired item can still be handed back. The check has to stay.
        if session.expired:
            log.info("session.expired", session=session_id)
            return None
        return session

    def save(self, session: Session) -> None:
        record = json.dumps(session.to_record(), ensure_ascii=False)
        size = len(record.encode("utf-8"))
        if size > ITEM_LIMIT * LOUD_AT:
            # Said out loud well before it breaks, because the failure mode is a
            # write that starts refusing mid-game and a notebook that stops
            # keeping up. The escape hatch is one item per statement, keyed by
            # session and round, which needs a wider `Sessions` protocol.
            log.warning(
                "session.large",
                session=session.id,
                bytes=size,
                limit=ITEM_LIMIT,
                rounds=session.transcript.rounds,
                detail="approaching the DynamoDB item ceiling",
            )
        self.table.put_item(
            Item={"id": session.id, "expires": session.expires, "record": record}
        )

    def count(self) -> int:
        """How many sessions exist. A scan, and the only one here.

        Nothing in the game calls this on a page load; it is for a person asking
        how busy the evening was. `Select="COUNT"` returns the number without
        returning the items, so a hundred and twenty kilobyte record does not
        come back over the wire to be thrown away.
        """
        total = 0
        start = None
        while True:
            page = self.table.scan(
                Select="COUNT", **({"ExclusiveStartKey": start} if start else {})
            )
            total += page.get("Count", 0)
            start = page.get("LastEvaluatedKey")
            if not start:
                return total


def sessions() -> "FileSessions | DynamoSessions":
    """Which store this process uses. One variable, read in one place (D-122)."""
    table = os.environ.get(SESSIONS_TABLE, "").strip()
    return DynamoSessions(table) if table else FileSessions()
