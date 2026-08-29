"""Cases you can come back to.

There has been a cache since D-005 and it does not do this job. That one is keyed
by a hash of the request *and* the prompt (D-035), which is exactly right for
what it is for: not paying twice for the same generation while a prompt is being
developed. It is exactly wrong for keeping a case, because the moment the prompt
changes every key changes, and a case you liked last week is a file named
`a3f9c2e1...json` that nothing will ever ask for again.

So the two are separate things and this is the other one (D-073). A saved case is
the *solved* mystery, under a name made from its title, with the setting and the
shape and the date beside it. Nothing about it depends on the prompt that made
it, and loading one calls no model at all.

Art goes under the case id rather than the request hash for the same reason. A
portrait that cost five cents should outlive an edit to a paragraph of prompt.
"""

import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import structlog

from mystery.models import Mystery

log = structlog.get_logger()

LIBRARY = Path("var/cases")
ART = Path("var/art")


@dataclass(frozen=True)
class Card:
    """What a case is, without what is in it.

    Everything the hot path needs and nothing else (D-081). `waiting()` runs
    when somebody visits the game, and all it has ever wanted per case is the id
    and when it was made. Both of those live in the object's *name*, so a
    listing is one request and no reads at all, rather than one request and
    three hundred.
    """

    id: str
    saved: str

    @property
    def key(self) -> str:
        return f"{self.saved}__{self.id}.json"


def _stamp() -> str:
    """Sortable, compact, and safe in a key on any storage anybody uses."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S")


def mint(title: str) -> str:
    """A case id nobody has to ask permission for.

    `_unique` used to ask "is this name taken?" once per guess, which is free on
    a disk and a network round trip each on anything else, and racy besides: two
    jobs naming a case at the same moment are both told the name is free. Four
    random characters cost nothing and cannot collide.

    Note what the randomness is *for*. A session id is random so that nobody can
    guess somebody else's notebook, which is secrecy. This is random so that two
    writers never choose the same name, which is coordination. Same tool, and
    worth knowing which one you are reaching for.
    """
    return f"{slug(title)}-{secrets.token_hex(2)}"


@dataclass(frozen=True)
class SavedCase:
    id: str
    title: str
    setting: str
    topology: str
    seed: int
    saved: str
    mystery: Mystery

    @property
    def art(self) -> Path:
        """Where this case's portraits and backdrops live, if it has any."""
        return ART / self.id


def slug(title: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return cleaned or "untitled"


class Shelf(Protocol):
    """Where finished cases live.

    Three methods, and the split between the first two is the whole point.
    `cards` is cheap and runs on every page load; `load` is expensive and runs
    once for the case somebody is playing. Anything that blurs those two is the
    bug this interface exists to prevent (D-081).
    """

    def cards(self) -> list[Card]: ...

    def load(self, case_id: str) -> SavedCase: ...

    def save(self, mystery: Mystery, setting: str, topology: str, seed: int) -> SavedCase: ...


def save(
    mystery: Mystery,
    setting: str,
    topology: str,
    seed: int,
    folder: Path = LIBRARY,
) -> SavedCase:
    folder.mkdir(parents=True, exist_ok=True)
    case = SavedCase(
        id=mint(mystery.title),
        title=mystery.title,
        setting=setting,
        topology=topology,
        seed=seed,
        # A timestamp rather than a date, because the buffer is served oldest
        # first and two cases made the same night have to have an order (D-078).
        # Milliseconds, not seconds. Two cases made in the same second had the
        # same sort key, and the queue fell back to comparing random suffixes,
        # which is not an order at all (D-081).
        saved=datetime.now(UTC).isoformat(timespec="milliseconds"),
        mystery=mystery,
    )

    payload = {
        "id": case.id,
        "title": case.title,
        "setting": case.setting,
        "topology": case.topology,
        "seed": case.seed,
        "saved": case.saved,
        "mystery": mystery.model_dump(mode="json"),
    }
    # The name carries the sort key, so listing is ordering and no file has to
    # be opened to know when it was made.
    stamp = case.saved.replace("-", "").replace(":", "").split("+")[0]
    (folder / f"{stamp}__{case.id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("library.saved", case=case.id, title=case.title)
    return case


def _find(case_id: str, folder: Path) -> Path | None:
    """The file holding this case, by exact id or by an unambiguous prefix.

    Prefix matching is what pays for the random suffix in `mint`: nobody wants
    to type `the-brine-house-k3f9`, and `--case the-brine` is enough as long as
    it means one thing.
    """
    if not folder.exists():
        return None

    exact = [p for p in folder.glob(f"*__{case_id}.json")]
    exact += [p for p in folder.glob(f"{case_id}.json")]  # cases saved before D-081
    if exact:
        return exact[0]

    near = sorted(p for p in folder.glob("*.json") if _id_of(p).startswith(case_id))
    return near[0] if len(near) == 1 else None


def _id_of(path: Path) -> str:
    return path.stem.split("__", 1)[1] if "__" in path.stem else path.stem


def load(case_id: str, folder: Path = LIBRARY) -> SavedCase:
    path = _find(case_id, folder)
    if path is None:
        known = ", ".join(c.id for c in cards(folder)) or "nothing yet"
        raise FileNotFoundError(f"no saved case called {case_id!r}. Saved: {known}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    return SavedCase(
        id=raw["id"],
        title=raw["title"],
        setting=raw.get("setting", ""),
        topology=raw.get("topology", ""),
        seed=raw.get("seed", 0),
        saved=raw.get("saved", ""),
        mystery=Mystery.model_validate(raw["mystery"]),
    )


def cards(folder: Path = LIBRARY) -> list[Card]:
    """Every case on the shelf, oldest first, without opening any of them.

    The name carries both fields, so this is a directory listing locally and a
    single paged request on object storage. Cases saved before the naming change
    have no stamp in their name and sort first, which is right: they are the
    oldest things here.
    """
    if not folder.exists():
        return []
    found = [
        Card(id=_id_of(path), saved=path.stem.split("__", 1)[0] if "__" in path.stem else "")
        for path in sorted(folder.glob("*.json"))
    ]
    return sorted(found, key=lambda c: (c.saved, c.id))


def entries(folder: Path = LIBRARY) -> list[SavedCase]:
    """Every case, opened. The cold path: a person ran a command and is waiting.

    Kept separate from `cards` on purpose. This is the expensive one, and the
    only defence against it creeping back into a page load is that it has a
    different name from the cheap one (D-081).
    """
    found = []
    for card in cards(folder):
        try:
            found.append(load(card.id, folder))
        except Exception as error:  # noqa: BLE001 - one bad file must not hide the rest
            log.warning("library.unreadable", case=card.id, error=str(error))
    return found


def catalogue(folder: Path = LIBRARY) -> str:
    """The shelf, for the command line."""
    saved = entries(folder)
    if not saved:
        return "  Nothing saved yet. Every case you start gets kept here."
    return "\n".join(
        f"  {c.id:<28} {c.saved}  {c.topology or 'the_lie':<16} {c.setting[:40]}"
        for c in saved
    )
