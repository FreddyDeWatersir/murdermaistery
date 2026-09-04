"""Two shelves, one protocol, and a fake bucket (D-118).

Nothing here touches AWS. `FakeS3` is a dictionary that answers the three calls
`S3Shelf` makes, in the shapes boto3 answers them, including the paging that
real S3 does and a naive implementation would never notice.
"""

import json

import pytest

from mystery.example import OPENING_NIGHT
from mystery.library import (
    CASES,
    INDEX,
    Card,
    FileShelf,
    S3Shelf,
    shelf,
    squash,
)
from mystery.models import Mystery

CASE = Mystery.model_validate(OPENING_NIGHT)


class NoSuchKey(Exception):
    pass


class FakeS3:
    """A dict pretending to be a bucket. Paginates at `page_size` so the
    continuation-token loop is actually exercised rather than assumed."""

    def __init__(self, page_size: int = 1000) -> None:
        self.objects: dict[str, bytes] = {}
        self.page_size = page_size
        self.calls: list[str] = []

    class _Exceptions:
        NoSuchKey = NoSuchKey

    exceptions = _Exceptions()

    def put_object(self, Bucket, Key, Body, **kw):
        self.calls.append(f"put {Key}")
        self.objects[Key] = Body if isinstance(Body, bytes) else Body.encode()
        return {}

    def get_object(self, Bucket, Key):
        self.calls.append(f"get {Key}")
        if Key not in self.objects:
            raise NoSuchKey(Key)
        import io

        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, Bucket, Prefix="", ContinuationToken=None):
        self.calls.append(f"list {Prefix}")
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken) if ContinuationToken else 0
        page = keys[start : start + self.page_size]
        end = start + len(page)
        return {
            "Contents": [{"Key": k} for k in page],
            "IsTruncated": end < len(keys),
            "NextContinuationToken": str(end),
        }


def _shelf(page_size: int = 1000) -> tuple[S3Shelf, FakeS3]:
    fake = FakeS3(page_size)
    return S3Shelf("a-bucket", client=fake), fake


# --- the round trip ----------------------------------------------------------


def test_a_case_saved_to_a_bucket_comes_back_whole() -> None:
    store, _ = _shelf()

    saved = store.save(CASE, "a residency", "the_lie", 7)
    back = store.load(saved.id)

    assert back.id == saved.id
    assert back.title == CASE.title
    assert back.setting == "a residency"
    assert back.topology == "the_lie"
    assert back.seed == 7
    assert back.mystery.killer == CASE.killer
    assert len(back.mystery.secrets) == len(CASE.secrets)


def test_saving_writes_the_case_and_a_marker() -> None:
    store, fake = _shelf()

    saved = store.save(CASE, "a residency", "the_lie", 7)

    assert f"{CASES}{saved.id}.json" in fake.objects
    assert f"{INDEX}{squash(saved.saved)}__{saved.id}" in fake.objects
    assert fake.objects[f"{INDEX}{squash(saved.saved)}__{saved.id}"] == b""


def test_the_marker_is_written_after_the_case() -> None:
    """No transaction spans two objects. Failing between them should leave a
    case that is loadable but unlisted, never a listing that cannot be opened."""
    store, fake = _shelf()

    store.save(CASE, "a residency", "the_lie", 7)
    puts = [c for c in fake.calls if c.startswith("put")]

    assert puts[0].startswith(f"put {CASES}")
    assert puts[1].startswith(f"put {INDEX}")


# --- the hot path ------------------------------------------------------------


def test_listing_the_shelf_opens_nothing() -> None:
    """The whole reason `Card` exists (D-081). Three cases on the shelf, and
    `cards` must cost one request and zero reads."""
    store, fake = _shelf()
    for _ in range(3):
        store.save(CASE, "a residency", "the_lie", 7)
    fake.calls.clear()

    found = store.cards()

    assert len(found) == 3
    assert not [c for c in fake.calls if c.startswith("get")], "cards opened a case"
    assert [c for c in fake.calls if c.startswith("list")] == [f"list {INDEX}"]


def test_the_shelf_comes_back_oldest_first() -> None:
    store, _ = _shelf()
    ids = [store.save(CASE, "a residency", "the_lie", n).id for n in range(4)]

    assert [c.id for c in store.cards()] == ids


def test_loading_by_exact_id_is_one_request() -> None:
    store, fake = _shelf()
    saved = store.save(CASE, "a residency", "the_lie", 7)
    fake.calls.clear()

    store.load(saved.id)

    assert fake.calls == [f"get {CASES}{saved.id}.json"]


def test_a_shorthand_still_finds_a_case() -> None:
    """`--case the-brine` for `the-brine-house-k3f9`. It survives the move for
    free: putting the id first so `load` works at all is the same thing that
    makes a prefix search work."""
    store, _ = _shelf()
    saved = store.save(CASE, "a residency", "the_lie", 7)
    stem = saved.id.rsplit("-", 1)[0]

    assert store.load(stem).id == saved.id


def test_an_ambiguous_shorthand_is_refused_rather_than_guessed() -> None:
    store, _ = _shelf()
    for _ in range(2):
        store.save(CASE, "a residency", "the_lie", 7)

    with pytest.raises(FileNotFoundError):
        store.load("opening")


def test_a_missing_case_says_what_is_there() -> None:
    store, _ = _shelf()
    saved = store.save(CASE, "a residency", "the_lie", 7)

    with pytest.raises(FileNotFoundError) as caught:
        store.load("no-such-case")

    assert saved.id in str(caught.value)


# --- the thing a naive implementation gets wrong -----------------------------


def test_a_shelf_bigger_than_one_page_is_listed_whole() -> None:
    """`list_objects_v2` returns at most a thousand keys and a token for the
    rest. Ignoring the token works until the day it does not."""
    store, fake = _shelf(page_size=2)
    ids = [store.save(CASE, "a residency", "the_lie", n).id for n in range(7)]

    assert [c.id for c in store.cards()] == ids


def test_junk_in_the_index_does_not_become_a_card() -> None:
    store, fake = _shelf()
    fake.objects[f"{INDEX}not-a-marker"] = b""

    assert store.cards() == []


# --- the two shelves agree ---------------------------------------------------


def test_both_shelves_write_the_same_bytes(tmp_path) -> None:
    """A case made on a laptop and a case made in the cloud have to be the same
    document, or one of them will fail to open the other's."""
    disk = FileShelf(tmp_path)
    cloud, fake = _shelf()

    on_disk = disk.save(CASE, "a residency", "the_lie", 7)
    in_cloud = cloud.save(CASE, "a residency", "the_lie", 7)

    a = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    b = json.loads(fake.objects[f"{CASES}{in_cloud.id}.json"])

    assert a.keys() == b.keys()
    assert a["mystery"] == b["mystery"]
    assert a["setting"] == b["setting"] == "a residency"
    assert on_disk.title == in_cloud.title


def test_a_file_shelf_satisfies_the_same_protocol(tmp_path) -> None:
    disk = FileShelf(tmp_path)

    saved = disk.save(CASE, "a residency", "the_lie", 7)

    assert [c.id for c in disk.cards()] == [saved.id]
    assert disk.load(saved.id).mystery.killer == CASE.killer
    assert isinstance(disk.cards()[0], Card)


# --- which one you get -------------------------------------------------------


def test_no_bucket_in_the_environment_means_the_folder(monkeypatch) -> None:
    """A laptop, and every test run, must never need AWS."""
    monkeypatch.delenv("MYSTERY_BUCKET", raising=False)

    assert isinstance(shelf(), FileShelf)


def test_an_empty_bucket_variable_is_not_a_bucket(monkeypatch) -> None:
    """Set-but-blank is how a deploy config goes wrong, and it should fall back
    rather than build a client for a bucket named the empty string."""
    monkeypatch.setenv("MYSTERY_BUCKET", "   ")

    assert isinstance(shelf(), FileShelf)


def test_a_bucket_in_the_environment_means_s3(monkeypatch) -> None:
    monkeypatch.setenv("MYSTERY_BUCKET", "mystery-cases-1234-eu-north-1-an")
    chosen = shelf()

    assert isinstance(chosen, S3Shelf)
    assert chosen.bucket == "mystery-cases-1234-eu-north-1-an"


def test_choosing_s3_does_not_build_a_client_or_need_boto3(monkeypatch) -> None:
    """The client is lazy on purpose: importing this module, or picking a shelf,
    must not require boto3 to be installed or credentials to exist."""
    monkeypatch.setenv("MYSTERY_BUCKET", "a-bucket")

    assert shelf()._client is None


# --- reachable from the entry points (D-119) ---------------------------------
#
# The point of this file's second half. `S3Shelf` passing its own tests proves
# nothing about whether the game can ever reach it, and this project's
# characteristic failure is exactly that: a thing written with care, carried
# through the schema, and never wired to the place that needed it. Nine times.


def _no_model(monkeypatch, module) -> None:
    """The whole pipeline with the model swapped for the shipped case.

    Not `--dry-run`: that deliberately keeps nothing (D-120), so a save test
    built on it would pass forever by testing nothing. This goes down the real
    generating path and only replaces the one call that costs money.
    """
    monkeypatch.setattr(
        module, "anthropic_drafter", lambda *a, **kw: (lambda request, complaints: OPENING_NIGHT)
    )


def test_the_cli_saves_through_the_shelf_it_was_given(monkeypatch, tmp_path) -> None:
    """The shelf a process chose has to be the one a case lands in."""
    import mystery.cli as cli
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    monkeypatch.setattr(cli, "pick_shelf", lambda: chosen)
    _no_model(monkeypatch, cli)

    assert cli.main(["--setting", "a residency", "--no-cache"]) == 0
    assert len(list(tmp_path.glob("*.json"))) == 1, "the case went somewhere else"


def test_a_dry_run_keeps_nothing(monkeypatch, tmp_path) -> None:
    """It is the same example case every run. Saving it filled a real bucket
    with copies of it under new ids (D-120)."""
    import mystery.cli as cli
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    monkeypatch.setattr(cli, "pick_shelf", lambda: chosen)

    assert cli.main(["--dry-run"]) == 0
    assert list(tmp_path.glob("*.json")) == []


def test_the_web_server_saves_through_the_shelf_it_was_given(monkeypatch, tmp_path) -> None:
    import mystery.web as web
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    monkeypatch.setattr(web, "pick_shelf", lambda: chosen)
    monkeypatch.setattr(web, "_serve", lambda *a, **kw: 0)
    _no_model(monkeypatch, web)

    assert web.main(["--setting", "a residency"]) == 0
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_the_web_dry_run_keeps_nothing(monkeypatch, tmp_path) -> None:
    import mystery.web as web
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    monkeypatch.setattr(web, "pick_shelf", lambda: chosen)
    monkeypatch.setattr(web, "_serve", lambda *a, **kw: 0)

    assert web.main(["--dry-run"]) == 0
    assert list(tmp_path.glob("*.json")) == []


def test_a_listing_draws_no_seed(monkeypatch, tmp_path, capsys) -> None:
    """`--cases` announced a seed, a shape and an occasion that reached nothing,
    which reads like provenance and is not (D-120)."""
    import mystery.cli as cli
    from mystery.library import FileShelf

    monkeypatch.setattr(cli, "pick_shelf", lambda: FileShelf(tmp_path))
    cli.main(["--cases"])
    printed = capsys.readouterr().out

    assert "Seed" not in printed
    assert "Occasion" not in printed


def test_the_cli_loads_a_case_through_the_shelf(monkeypatch, tmp_path) -> None:
    import mystery.cli as cli
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    saved = chosen.save(CASE, "a residency", "the_lie", 3)
    monkeypatch.setattr(cli, "pick_shelf", lambda: chosen)

    assert cli.main(["--case", saved.id]) == 0


def test_the_cli_lists_the_shelf_it_was_given(monkeypatch, tmp_path, capsys) -> None:
    import mystery.cli as cli
    from mystery.library import FileShelf

    chosen = FileShelf(tmp_path)
    saved = chosen.save(CASE, "a residency", "the_lie", 3)
    monkeypatch.setattr(cli, "pick_shelf", lambda: chosen)

    cli.main(["--cases"])

    assert saved.id in capsys.readouterr().out


def test_a_bucket_in_the_environment_reaches_the_entry_points(monkeypatch) -> None:
    """The end of the wire. With the variable set, the thing the CLI picks up is
    an S3Shelf pointed at that bucket, and it got there without boto3 or
    credentials because the client is still unbuilt."""
    import mystery.cli as cli

    monkeypatch.setenv("MYSTERY_BUCKET", "mystery-cases-1234-eu-north-1-an")
    chosen = cli.pick_shelf()

    assert isinstance(chosen, S3Shelf)
    assert chosen.bucket == "mystery-cases-1234-eu-north-1-an"
    assert chosen._client is None


def test_the_rota_reads_the_shelf_it_was_given(tmp_path) -> None:
    """`waiting` and `todays_case` used to take a folder. A deployed server has
    no folder, so they take a shelf now, and the S3 one has to work."""
    from mystery.daily import FileRota, waiting

    store, _ = _shelf()
    saved = store.save(CASE, "a residency", "the_lie", 1)

    assert [c.id for c in waiting(store, FileRota(tmp_path / 'rota.json'))] == [saved.id]
