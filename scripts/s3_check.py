"""Prove the storage works against real AWS, then leave nothing behind.

The suite tests `S3Shelf` against a fake, which is the right way to test it: no
network, no credentials, no charges, and it runs in milliseconds. But a fake can
only be wrong in the same way twice, and it cannot tell you that your region is
mismatched, your credentials are stale, your bucket policy says no, or that
boto3 wants an argument you did not pass. That is what this is for. It is run by
hand, against real AWS, and it is not part of `pytest` (D-118).

    set MYSTERY_BUCKET=mystery-cases-...-eu-north-1-an
    set MYSTERY_SESSIONS_TABLE=mystery-sessions
    set MYSTERY_ROTA_TABLE=mystery-rota
    uv run python scripts/s3_check.py

It saves the shipped example case, lists the shelf, loads it back, compares it
with what went in, and then deletes both objects it created.
"""

import os
import sys
import time

sys.path.insert(0, "src")

from mystery.daily import DynamoRota  # noqa: E402
from mystery.daily import rota as pick_rota  # noqa: E402
from mystery.example import OPENING_NIGHT  # noqa: E402
from mystery.gallery import ART_PREFIX, S3Gallery  # noqa: E402
from mystery.gallery import gallery as pick_gallery  # noqa: E402
from mystery.library import CASES, INDEX, S3Shelf, squash  # noqa: E402
from mystery.library import shelf as pick_shelf  # noqa: E402
from mystery.models import Mystery  # noqa: E402
from mystery.session import DynamoSessions  # noqa: E402
from mystery.session import sessions as pick_sessions  # noqa: E402


def _tables(problems: list[str]) -> None:
    """Sessions and the rota, against real DynamoDB, cleaning up after itself."""
    from mystery.interrogation import Statement

    store = pick_sessions()
    if not isinstance(store, DynamoSessions):
        print("Tables: MYSTERY_SESSIONS_TABLE not set, skipping")
        return

    print(f"Table:  {store.table_name}")
    started = time.time()
    session = store.create("a-check-not-a-real-case")
    session.transcript.record(
        Statement(round=1, speaker="ilse", question="where were you", speech="The green room.")
    )
    session.show("ilse", "the_books")
    store.save(session)
    back = store.get(session.id)
    print(f"  session {session.id}  round trip ({time.time() - started:.2f}s)")

    if back is None:
        problems.append("the session did not come back at all")
    else:
        if back.transcript.rounds != 1:
            problems.append("the transcript did not survive the round trip")
        if back.seen_by("ilse") != {"the_books"}:
            problems.append("what was shown did not survive the round trip")
    store.table.delete_item(Key={"id": session.id})

    book = pick_rota()
    if not isinstance(book, DynamoRota):
        print("  MYSTERY_ROTA_TABLE not set, skipping the rota")
        return

    print(f"Table:  {book.table_name}")
    day = "9999-01-01"
    book.release(day)
    first = book.claim(day, "the-ferry")
    second = book.claim(day, "the-orchard")
    print(f"  claim   first={first}  second={second}")

    if first != "the-ferry":
        problems.append("the first claim did not win its own day")
    if second != "the-ferry":
        problems.append(
            "the second claim was not told the winner: the conditional write "
            "is not doing what the whole table is for"
        )
    book.release(day)
    if book.case_for(day) is not None:
        problems.append("release left the day claimed")


def main() -> int:
    store = pick_shelf()
    print(f"Shelf:  {type(store).__name__}")

    if not isinstance(store, S3Shelf):
        print("\n  MYSTERY_BUCKET is not set, so this picked the local folder.")
        print("  Set it to your bucket name and run again.")
        return 2

    print(f"Bucket: {store.bucket}")
    print(f"Region: {os.environ.get('AWS_DEFAULT_REGION') or 'from your aws config'}\n")

    case = Mystery.model_validate(OPENING_NIGHT)
    before = len(store.cards())
    print(f"  {before} case(s) already on the shelf")

    start = time.time()
    saved = store.save(case, "a check, not a real case", "the_lie", 0)
    print(f"  saved   {saved.id}  ({time.time() - start:.2f}s)")

    start = time.time()
    listed = store.cards()
    print(f"  listed  {len(listed)} card(s)  ({time.time() - start:.2f}s)")

    start = time.time()
    back = store.load(saved.id)
    print(f"  loaded  {back.id}  ({time.time() - start:.2f}s)")

    stem = saved.id.rsplit("-", 1)[0]
    shorthand = store.load(stem)
    print(f"  found   {stem!r} -> {shorthand.id}")

    problems = []
    if len(listed) != before + 1:
        problems.append(f"shelf went from {before} to {len(listed)}, expected {before + 1}")
    if saved.id not in {c.id for c in listed}:
        problems.append("the case saved is not in the listing")
    if back.mystery.killer != case.killer:
        problems.append("the case that came back is not the one that went in")
    if back.setting != "a check, not a real case":
        problems.append("the setting did not survive the round trip")

    # The gallery, in the same bucket under its own prefix.
    art = pick_gallery()
    if isinstance(art, S3Gallery):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "probe.png").write_bytes(b"\x89PNG probe")
            sent = art.put(saved.id, "portraits", folder)
        print(f"  art     uploaded {sent} picture(s)")

        listed_art = art.names(saved.id, "portraits")
        link = art.link(saved.id, "portraits", "probe.png")
        print(f"  link    {link[:72]}...")
        if listed_art != {"probe": "probe.png"}:
            problems.append(f"the gallery listed {listed_art}, expected one probe")
        if "X-Amz-" not in link:
            problems.append("the link is not signed, which means the object is public")
        # The check that would have caught D-124. A browser cannot follow the
        # redirect the global endpoint answers with, because the signature is
        # bound to the host, so the link fails while every API call succeeds.
        host = link.split("/")[2]
        if host.endswith(".s3.amazonaws.com"):
            problems.append(
                f"the link is signed against the global endpoint ({host}). A browser "
                f"cannot follow the redirect that answers, so pictures will not load"
            )
        if art.read(saved.id, "portraits", "probe.png") != b"\x89PNG probe":
            problems.append("the picture did not survive the round trip")
        store.client.delete_object(
            Bucket=store.bucket, Key=f"{ART_PREFIX}{saved.id}/portraits/probe.png"
        )

    # Tidy up. `S3Shelf` has no delete because the game never deletes a case, so
    # this reaches past it to the client, which is exactly the sort of thing a
    # throwaway script may do and the application may not.
    for key in (f"{CASES}{saved.id}.json", f"{INDEX}{squash(saved.saved)}__{saved.id}"):
        store.client.delete_object(Bucket=store.bucket, Key=key)
    print(f"  cleaned up 2 objects, shelf back to {len(store.cards())}")

    print()
    _tables(problems)

    if problems:
        print("\nFAILED:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nAll good. The shelf works against real S3.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
