"""One case a day, decided in advance.

The obvious design is a job that wakes at three in the morning and generates
today's mystery. It is wrong in a way that only shows up at three in the
morning: when the call fails, or comes back unwinnable, there is nobody awake
and no case at nine (D-078).

So the job does not make *today's* case. It keeps a **buffer** topped up, and
today's case is drawn from what is already sitting there. A failed run costs
nothing except a slightly shorter queue, and there are three or four days of
slack before anybody notices something is wrong. Which is the point: it turns an
outage into a warning rather than an incident.

Two ideas, kept apart on purpose.

**The shelf** is `library.py`, which already stores solved cases as JSON under
names. Nothing here duplicates it.

**The rota** is this module: which case was served on which day, and therefore
which of the shelf's cases have not been used yet. It is one small file, read
often and written once a day, while a case is a large file read once and cached.
That split is what keeps the per-request cost near zero.

The day is UTC. Not because anybody lives there, but because "today" has to be
decided in exactly one place or it drifts by a day depending on who is asking.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import structlog
from mystery.library import LIBRARY, Card, SavedCase, cards

log = structlog.get_logger()

ROTA = Path("var/rota.json")

# How many unplayed cases to keep waiting. Four is a working week of slack: the
# generator can fail four nights running before a player notices, which is far
# longer than it takes anybody to read a log.
BUFFER = 4


def today() -> str:
    """The one place the current day is decided."""
    return datetime.now(UTC).date().isoformat()


class Rota(Protocol):
    """Which case ran on which day, and who gets to decide.

    One method does the interesting work. `claim` means "today's case is this
    one, unless somebody has already said otherwise, in which case tell me what
    they said". Whoever arrives first wins and everybody else is told the
    winner's answer.

    That shape exists because of what happens on a machine that runs many copies
    of this code at once (D-079). The old version read a file, added a day, and
    wrote the whole file back, which has two problems. Two writers overlapping
    means one silently erases the other's entry, since every write rewrites the
    entire history. And nothing said the *choice* had to be deterministic: it
    happened to be, so two containers happened to agree, and the first person to
    add a random pick would have broken it with nothing failing loudly.

    `claim` removes both. Each day is its own record, so writers never touch each
    other, and agreement is enforced rather than hoped for.
    """

    def claim(self, day: str, case_id: str) -> str: ...

    def release(self, day: str) -> None: ...

    def case_for(self, day: str) -> str | None: ...

    def used(self) -> set[str]: ...


@dataclass
class FileRota:
    """The local one: a JSON file, and the honesty to say what it cannot do.

    A file has no conditional write. This implementation re-reads immediately
    before writing, which narrows the window without closing it, and that is
    fine: the only way to get two writers here is to run two servers against one
    directory on one laptop, and if you are doing that you have chosen it.
    """

    path: Path = ROTA

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get("served", {})
        except (json.JSONDecodeError, OSError) as error:
            # A corrupt rota must not take the game down. The worst case is a
            # case served twice, which nobody will die of.
            log.warning("rota.unreadable", error=str(error))
            return {}

    def claim(self, day: str, case_id: str) -> str:
        served = self._read()
        if day in served:
            return served[day]

        served[day] = case_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"served": served}, indent=2), encoding="utf-8")
        return case_id

    def release(self, day: str) -> None:
        """Forget a day, so it can be claimed again.

        The only caller is the repair path: a day whose case has been deleted
        off the shelf points at nothing, and `claim` will not overwrite it
        because that is the whole point of `claim`. Rare, and loud when it
        happens.
        """
        served = self._read()
        if served.pop(day, None) is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"served": served}, indent=2), encoding="utf-8")

    def case_for(self, day: str) -> str | None:
        return self._read().get(day)

    def used(self) -> set[str]:
        return set(self._read().values())


def waiting(folder: Path = LIBRARY, rota: Rota | Path | None = None) -> list[Card]:
    """Cases on the shelf that have never been anybody's day, oldest first.

    Cards rather than cases (D-081). This runs whenever somebody visits, and it
    has never needed anything but the id and the date. It used to open every
    case on the shelf to get them, which is nothing on a laptop with five and
    three hundred network round trips on object storage with three hundred.
    """
    used = _rota(rota).used()
    return [card for card in cards(folder) if card.id not in used]


def _rota(rota: Rota | Path | None) -> Rota:
    """A path is still accepted, because every caller in the project passes one
    and a boundary that breaks its callers on day one does not get adopted."""
    if rota is None:
        return FileRota()
    return FileRota(rota) if isinstance(rota, Path) else rota


def todays_case(
    day: str | None = None, folder: Path = LIBRARY, rota: Rota | Path | None = None
) -> SavedCase | None:
    """The case for today, drawn from the buffer the first time it is asked for.

    Deliberately not "generate one if there is none". This function is called by
    the thing serving players, and a web request must never be the thing that
    decides to spend a minute and some money on a model. When the buffer is
    empty this returns None and the caller says so, which is the honest failure
    and the one that gets noticed.
    """
    from mystery.library import load

    day = day or today()
    book = _rota(rota)

    already = book.case_for(day)
    if already:
        try:
            return load(already, folder)
        except FileNotFoundError:
            # The record points at a case that is no longer on the shelf. Let go
            # of the day so it can be claimed again, rather than serving nothing
            # for ever because of one deleted file.
            log.warning("rota.case_missing", day=day, case=already)
            book.release(day)

    queue = waiting(folder, book)
    if not queue:
        log.error("rota.empty", day=day, detail="nothing left to serve. Run --fill")
        return None

    # Propose the front of the queue, and take whatever answer comes back. If
    # somebody else claimed the day a millisecond ago, theirs is the case, and
    # this is the line that makes two servers agree without either knowing the
    # other exists.
    settled = book.claim(day, queue[0].id)
    if settled != queue[0].id:
        log.info("rota.lost_the_race", day=day, ours=queue[0].id, theirs=settled)

    log.info("rota.served", day=day, case=settled, left=len(queue) - 1)
    try:
        # The one expensive read in the whole path, for the one case being
        # played, which is the shape D-081 was after.
        return load(settled, folder)
    except FileNotFoundError:
        log.error("rota.claimed_case_missing", day=day, case=settled)
        return load(queue[0].id, folder) if settled != queue[0].id else None


def shortfall(
    folder: Path = LIBRARY, rota: Rota | Path | None = None, want: int = BUFFER
) -> int:
    """How many cases the job should generate tonight. Zero most nights."""
    return max(0, want - len(waiting(folder, rota)))
