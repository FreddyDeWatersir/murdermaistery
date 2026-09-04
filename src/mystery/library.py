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
import os
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


# The last stamp this process handed out. The queue is ordered by stamp, so two
# cases saved inside the same clock tick used to tie and fall back to comparing
# their random suffixes, which is not an order at all. Seconds tied first, and
# milliseconds tied later on a faster machine, which is the lesson: an ordering
# that depends on a clock being finer than the loop above it is a race, and
# chasing resolution loses it twice (D-078, D-081, D-094).
_last: datetime | None = None


def _stamp() -> str:
    """Sortable, compact, unique within this process, and a real timestamp.

    Monotonic rather than merely precise. If the clock has not moved since the
    last call, this returns one millisecond past the previous stamp instead of
    repeating it, so save order is save order whatever the machine's speed. The
    result is still a valid ISO instant, which matters because it is displayed
    and because it sits in a filename that has to sort lexicographically.
    """
    global _last
    now = datetime.now(UTC).replace(microsecond=0) + timedelta(
        milliseconds=datetime.now(UTC).microsecond // 1000
    )
    if _last is not None and now <= _last:
        now = _last + timedelta(milliseconds=1)
    _last = now
    return now.isoformat(timespec="milliseconds")


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
        # first and two cases made the same night have to have an order (D-078,
        # D-081, D-094). `_stamp` guarantees it is later than the last one this
        # process wrote, so a tight loop cannot produce a tie.
        saved=_stamp(),
        mystery=mystery,
    )

    # The name carries the sort key, so listing is ordering and no file has to
    # be opened to know when it was made.
    (folder / f"{squash(case.saved)}__{case.id}.json").write_text(
        json.dumps(payload_of(case), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("library.saved", case=case.id, title=case.title)
    return case


def squash(saved: str) -> str:
    """The timestamp as it appears in a name: no punctuation, still sortable.

    Shared by every shelf, because the sort order of the queue is the order of
    these strings and two shelves that squash differently would disagree about
    which case is next (D-118).
    """
    return saved.replace("-", "").replace(":", "").split("+")[0]


def payload_of(case: SavedCase) -> dict:
    """What actually gets written, on a disk or into an object. One definition,
    so a case saved on a laptop and a case saved in the cloud are the same
    bytes and either can read the other's."""
    return {
        "id": case.id,
        "title": case.title,
        "setting": case.setting,
        "topology": case.topology,
        "seed": case.seed,
        "saved": case.saved,
        "mystery": case.mystery.model_dump(mode="json"),
    }


def case_from(raw: dict) -> SavedCase:
    """The other direction. `.get` with defaults on everything but id, title and
    the mystery itself: cases saved before a field existed still have to open."""
    return SavedCase(
        id=raw["id"],
        title=raw["title"],
        setting=raw.get("setting", ""),
        topology=raw.get("topology", ""),
        seed=raw.get("seed", 0),
        saved=raw.get("saved", ""),
        mystery=Mystery.model_validate(raw["mystery"]),
    )


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

    return case_from(json.loads(path.read_text(encoding="utf-8")))


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


def as_shelf(source: "Shelf | Path | None") -> "Shelf":
    """Whatever a caller had lying around, as a shelf (D-119).

    A `Path` still works because every caller in this project passed one, and
    `daily.py` learned in D-080 that a boundary which breaks its callers on the
    day it lands does not get adopted. `None` means "whatever this process is
    configured for", which is the only answer a deployed server can give.
    """
    if source is None:
        return shelf()
    return FileShelf(source) if isinstance(source, Path) else source


def entries(source: "Shelf | Path | None" = None) -> list[SavedCase]:
    """Every case, opened. The cold path: a person ran a command and is waiting.

    Kept separate from `cards` on purpose. This is the expensive one, and the
    only defence against it creeping back into a page load is that it has a
    different name from the cheap one (D-081).
    """
    store = as_shelf(source)
    found = []
    for card in store.cards():
        try:
            found.append(store.load(card.id))
        except Exception as error:  # noqa: BLE001 - one bad file must not hide the rest
            log.warning("library.unreadable", case=card.id, error=str(error))
    return found


def catalogue(source: "Shelf | Path | None" = None) -> str:
    """The shelf, for the command line."""
    saved = entries(source)
    if not saved:
        return "  Nothing saved yet. Every case you start gets kept here."
    return "\n".join(
        f"  {c.id:<28} {c.saved}  {c.topology or 'the_lie':<16} {c.setting[:40]}"
        for c in saved
    )


# --- shelves ----------------------------------------------------------------
#
# The protocol above has had no implementations, only module functions that the
# CLI and the web server call directly. These are the two implementations, and
# the point of writing the second one is that the first has to keep working
# untouched: a laptop must be able to run this game with no AWS account, no
# credentials and no boto3 installed (D-118).


def s3_client(region: str | None = None):
    """An S3 client that addresses buckets by their **regional** endpoint.

    `boto3.client("s3", region_name=...)` alone signs against the legacy global
    host, `<bucket>.s3.amazonaws.com`, and for anything outside us-east-1 that
    host answers a redirect. boto3 follows it, so every API call this project
    makes worked fine and nothing complained.

    A browser cannot follow it, because a presigned signature is bound to the
    host it was made for. So a link handed to a page 403s while the identical
    operation from Python succeeds, which is a horrible thing to debug and cost
    a real run its pictures (D-124). AWS is explicit for buckets in an account
    regional namespace: use the regional endpoint, the global one is a
    us-east-1 backwards-compatibility shim.

    One place, so the shelf and the gallery cannot disagree about it.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        region_name=region,
        config=Config(s3={"addressing_style": "virtual"}, signature_version="s3v4"),
    )


class FileShelf:
    """A folder. The default, and the only one that runs in the tests."""

    def __init__(self, folder: Path = LIBRARY) -> None:
        self.folder = folder

    def cards(self) -> list[Card]:
        return cards(self.folder)

    def load(self, case_id: str) -> SavedCase:
        return load(case_id, self.folder)

    def save(self, mystery: Mystery, setting: str, topology: str, seed: int) -> SavedCase:
        return save(mystery, setting, topology, seed, self.folder)


# Two prefixes, each shaped for exactly one access pattern (D-118).
#
# S3 is not a filesystem. It is a flat key/value store, the slashes are just
# characters, and the one indexed operation is "list keys starting with X".
# There is no way to search from the right, so a single naming scheme cannot
# serve both of the shelf's reads: `load` knows an id and `cards` wants
# everything in date order.
#
# So the id is a key prefix for `load`, and a second, empty object carries the
# date in its *name* for `cards`. The marker stores nothing at all: writing it
# is how you write to an index when the index is the namespace.
CASES = "cases/"
INDEX = "index/"


class S3Shelf:
    """The same shelf, in a bucket.

    `client` is injectable for the same reason `Drafter` and `Responder` are
    (D-002, D-027): the suite must never touch a network, so the tests pass a
    dictionary that behaves like S3 and the real one is only built when nothing
    was handed in.
    """

    def __init__(self, bucket: str, client=None, region: str | None = None) -> None:
        self.bucket = bucket
        self._client = client
        self._region = region

    @property
    def client(self):
        """Built on first use, so importing this module never needs boto3."""
        if self._client is None:
            self._client = s3_client(self._region)
        return self._client

    def _keys(self, prefix: str) -> list[str]:
        """Every key under a prefix, following the pages.

        `list_objects_v2` returns at most a thousand keys and a token for the
        rest. Code that ignores the token works perfectly until the day there
        are a thousand and one objects, and then quietly stops seeing the newest
        ones, which is a horrible way to find out.
        """
        found: list[str] = []
        token: str | None = None
        while True:
            page = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                **({"ContinuationToken": token} if token else {}),
            )
            found += [item["Key"] for item in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return found
            token = page.get("NextContinuationToken")

    def cards(self) -> list[Card]:
        """One request, no reads. What `Card` was designed for before S3 existed.

        The date could have come from each object's LastModified instead of a
        marker, which would save a write. It is the wrong shortcut: LastModified
        has one second of resolution, and D-094 was precisely about two cases
        made inside the same tick tying and losing their order. The stamp is
        monotonic on purpose, so it has to be the stamp.
        """
        found = []
        for key in self._keys(INDEX):
            name = key[len(INDEX) :]
            stamp, _, case_id = name.partition("__")
            if case_id:
                found.append(Card(id=case_id, saved=stamp))
        return sorted(found, key=lambda c: (c.saved, c.id))

    def load(self, case_id: str) -> SavedCase:
        """One GET when the id is exact, and a prefix listing when it is not.

        The friendly shorthand `--case the-brine` for `the-brine-house-k3f9`
        turns out to be free here: putting the id at the front of the key so
        that `load` works at all is the same thing that makes a prefix search
        work, so the local convenience survives the move without being ported.
        """
        try:
            body = self.client.get_object(Bucket=self.bucket, Key=f"{CASES}{case_id}.json")
            return case_from(json.loads(body["Body"].read()))
        except self.client.exceptions.NoSuchKey:
            pass

        near = self._keys(f"{CASES}{case_id}")
        if len(near) != 1:
            known = ", ".join(c.id for c in self.cards()) or "nothing yet"
            raise FileNotFoundError(f"no saved case called {case_id!r}. Saved: {known}")

        body = self.client.get_object(Bucket=self.bucket, Key=near[0])
        return case_from(json.loads(body["Body"].read()))

    def save(self, mystery: Mystery, setting: str, topology: str, seed: int) -> SavedCase:
        """The case, then the marker. Two writes, in that order, deliberately.

        There is no transaction across two objects. If the second write fails the
        case exists and is loadable by name but is not in the queue, which is a
        case you can still reach. The other order loses the case and leaves a
        marker pointing at nothing, which is a listing that cannot be opened.
        When you cannot have both, fail towards the harmless half.
        """
        case = SavedCase(
            id=mint(mystery.title),
            title=mystery.title,
            setting=setting,
            topology=topology,
            seed=seed,
            saved=_stamp(),
            mystery=mystery,
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"{CASES}{case.id}.json",
            Body=json.dumps(payload_of(case), indent=2, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        self.client.put_object(
            Bucket=self.bucket,
            Key=f"{INDEX}{squash(case.saved)}__{case.id}",
            Body=b"",
        )
        log.info("library.saved", case=case.id, title=case.title, bucket=self.bucket)
        return case


def shelf() -> "FileShelf | S3Shelf":
    """Which shelf this process is using, decided by the environment and nothing
    else (D-118).

    One environment variable, read in one place. No AWS means the folder, which
    is what a laptop and the whole test suite get. This is the only line in the
    project that knows both shelves exist.
    """
    bucket = os.environ.get("MYSTERY_BUCKET", "").strip()
    return S3Shelf(bucket) if bucket else FileShelf()
