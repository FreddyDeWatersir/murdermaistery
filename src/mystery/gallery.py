"""Where a case's pictures live (D-121).

The third boundary of the same shape as `Shelf`, `Sessions` and `Rota`, and the
one that was quietly missing. `web.py` served portraits straight off the
filesystem, which is fine on a laptop and is nothing on a Lambda: there is no
disk there, so a deployed game would have rendered every face and every room as
a blank.

Two implementations. A folder, which is what a laptop uses and what every test
uses, and a bucket, which is what a deployed one uses.

**The serving question, which is the interesting part.** A portrait here is
about a megabyte and a half, and six of them make a case. Reading those out of
S3 into Python and returning them through the application would put nine
megabytes of image through the compute layer on every cold visit: slow, billed
per millisecond, and pressing against the six megabyte response ceiling for no
reason at all.

So `S3Gallery` does not serve bytes. It hands back a **presigned URL**: a link to
the object with a signature and an expiry baked into the query string, which the
browser fetches straight from S3. The bucket stays private, nothing is public,
and the picture never touches the application. `FileGallery` returns None from
the same method, and the route falls back to reading the file, which is exactly
right on a machine where the file is right there.
"""

import os
from pathlib import Path
from typing import Protocol

import structlog

log = structlog.get_logger()

ART = Path("var/art")

# One hour. Long enough that a page open in a tab keeps working through a game,
# short enough that a link copied out of the page stops being a way in.
LINK_LIFE = 3600

# The one prefix, alongside `cases/` and `index/` in the same bucket. Nothing
# about pictures wants a bucket of their own, and one bucket is one thing to
# secure, one thing to pay for, and one name to get right.
ART_PREFIX = "art/"


class Gallery(Protocol):
    """Three methods, and the split between the last two is the whole point.

    `link` is the cheap answer and the one a deployed game wants: a URL the
    browser can fetch without the application in the middle. `read` is the
    fallback for anything that has the bytes to hand. An implementation answers
    one or the other, never neither.
    """

    def names(self, case_id: str, kind: str) -> dict[str, str]: ...

    def link(self, case_id: str, kind: str, name: str) -> str | None: ...

    def read(self, case_id: str, kind: str, name: str) -> bytes | None: ...

    def put(self, case_id: str, kind: str, folder: Path) -> int: ...


class FileGallery:
    """A folder under `var/art`. The default, and the only one in the tests."""

    def __init__(self, root: Path = ART) -> None:
        self.root = root

    def folder(self, case_id: str, kind: str) -> Path:
        return self.root / case_id / kind

    def names(self, case_id: str, kind: str) -> dict[str, str]:
        """Whatever pictures this case already has.

        Art belongs to the case rather than to the flag that made it, so a saved
        case brings its faces and rooms back without `--art` and without paying
        twice (D-073).
        """
        folder = self.folder(case_id, kind)
        if not folder.exists():
            return {}
        return {path.stem: path.name for path in sorted(folder.glob("*.png"))}

    def link(self, case_id: str, kind: str, name: str) -> str | None:
        """No link. The file is on this machine, so the route reads it."""
        return None

    def read(self, case_id: str, kind: str, name: str) -> bytes | None:
        path = self.folder(case_id, kind) / name
        return path.read_bytes() if path.exists() else None

    def put(self, case_id: str, kind: str, folder: Path) -> int:
        """Already there. Generation writes into this folder in the first place."""
        return 0


class S3Gallery:
    """The same pictures, in the same bucket as the cases, under `art/`."""

    def __init__(self, bucket: str, client=None, region: str | None = None) -> None:
        self.bucket = bucket
        self._client = client
        self._region = region

    @property
    def client(self):
        if self._client is None:
            # The regional endpoint, not the global one. A presigned signature is
            # bound to the host it was made for, so a link built against
            # `s3.amazonaws.com` cannot survive the redirect a browser gets
            # (D-124).
            from mystery.library import s3_client

            self._client = s3_client(self._region)
        return self._client

    def _prefix(self, case_id: str, kind: str) -> str:
        return f"{ART_PREFIX}{case_id}/{kind}/"

    def names(self, case_id: str, kind: str) -> dict[str, str]:
        """One LIST. The same trick as the shelf: the names are the answer, and
        no object has to be opened to find out what is here."""
        found: dict[str, str] = {}
        prefix = self._prefix(case_id, kind)
        token = None
        while True:
            page = self.client.list_objects_v2(
                Bucket=self.bucket,
                Prefix=prefix,
                **({"ContinuationToken": token} if token else {}),
            )
            for item in page.get("Contents", []):
                name = item["Key"][len(prefix) :]
                if name.endswith(".png"):
                    found[name[:-4]] = name
            if not page.get("IsTruncated"):
                return dict(sorted(found.items()))
            token = page.get("NextContinuationToken")

    def link(self, case_id: str, kind: str, name: str) -> str | None:
        """A signed URL the browser fetches straight from S3.

        `generate_presigned_url` is arithmetic, not a request: it signs a string
        locally with the credentials this process already has. It costs nothing,
        takes no network, and works against a bucket with every public-access
        block switched on, because a presigned URL is an authenticated request
        wearing a link's clothes rather than a hole in the policy.
        """
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": f"{self._prefix(case_id, kind)}{name}"},
            ExpiresIn=LINK_LIFE,
        )

    def read(self, case_id: str, kind: str, name: str) -> bytes | None:
        """The fallback nobody should need, kept because a boundary that can only
        answer one way is a boundary that breaks the first time something else
        asks."""
        try:
            got = self.client.get_object(
                Bucket=self.bucket, Key=f"{self._prefix(case_id, kind)}{name}"
            )
        except self.client.exceptions.NoSuchKey:
            return None
        return got["Body"].read()

    def put(self, case_id: str, kind: str, folder: Path) -> int:
        """Push a freshly generated folder of pictures up. Returns how many.

        Generation still writes to disk first, and that is deliberate rather than
        lazy: the image API is the expensive part, the files are the thing worth
        not losing, and a failed upload should cost a retry rather than fifty
        cents of pictures.
        """
        if not folder.exists():
            return 0
        sent = 0
        for path in sorted(folder.glob("*.png")):
            self.client.put_object(
                Bucket=self.bucket,
                Key=f"{self._prefix(case_id, kind)}{path.name}",
                Body=path.read_bytes(),
                ContentType="image/png",
            )
            sent += 1
        if sent:
            log.info("gallery.uploaded", case=case_id, kind=kind, pictures=sent)
        return sent


def gallery() -> "FileGallery | S3Gallery":
    """Same variable as the shelf, on purpose (D-121).

    Pictures and cases belong to the same deployment and there is no sensible
    configuration where one is in a bucket and the other is on a disk. A second
    variable would only be a way to get them out of step.
    """
    bucket = os.environ.get("MYSTERY_BUCKET", "").strip()
    return S3Gallery(bucket) if bucket else FileGallery()
