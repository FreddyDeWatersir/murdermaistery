"""Pictures, in a folder and in a bucket (D-121).

The interesting assertion is that `S3Gallery` hands out a link rather than
bytes. A portrait is about a megabyte and a half; six of them make a case, and
pushing nine megabytes of PNG through the application on every cold visit is
slow, billed per millisecond, and pointless when S3 can serve it directly.
"""

from pathlib import Path

from fastapi.testclient import TestClient
from test_shelf import FakeS3

from mystery.example import OPENING_NIGHT
from mystery.gallery import ART_PREFIX, FileGallery, S3Gallery, gallery
from mystery.models import Mystery

CASE = Mystery.model_validate(OPENING_NIGHT)


class FakeS3Art(FakeS3):
    """The bucket, plus the one call a gallery makes that a shelf does not."""

    def generate_presigned_url(self, op, Params, ExpiresIn):
        self.calls.append(f"sign {Params['Key']}")
        return f"https://s3.example/{Params['Key']}?X-Amz-Expires={ExpiresIn}"


def _art(tmp_path: Path) -> Path:
    folder = tmp_path / "the-case" / "portraits"
    folder.mkdir(parents=True)
    (folder / "ilse.png").write_bytes(b"\x89PNG-ilse")
    (folder / "wouter.png").write_bytes(b"\x89PNG-wouter")
    return folder


# --- a folder ---------------------------------------------------------------


def test_a_folder_lists_what_it_has(tmp_path) -> None:
    _art(tmp_path)

    assert FileGallery(tmp_path).names("the-case", "portraits") == {
        "ilse": "ilse.png",
        "wouter": "wouter.png",
    }


def test_a_folder_has_no_link_and_gives_you_the_bytes(tmp_path) -> None:
    """On this machine the file is right there, so a redirect would be silly."""
    _art(tmp_path)
    store = FileGallery(tmp_path)

    assert store.link("the-case", "portraits", "ilse.png") is None
    assert store.read("the-case", "portraits", "ilse.png") == b"\x89PNG-ilse"


def test_a_folder_put_is_a_no_op(tmp_path) -> None:
    """Generation writes into this folder in the first place."""
    folder = _art(tmp_path)

    assert FileGallery(tmp_path).put("the-case", "portraits", folder) == 0


def test_a_missing_picture_is_none_rather_than_a_crash(tmp_path) -> None:
    assert FileGallery(tmp_path).read("the-case", "portraits", "nobody.png") is None


# --- a bucket ---------------------------------------------------------------


def test_uploading_puts_every_picture_under_the_art_prefix(tmp_path) -> None:
    fake = FakeS3Art()
    folder = _art(tmp_path)

    sent = S3Gallery("a-bucket", client=fake).put("the-case", "portraits", folder)

    assert sent == 2
    assert f"{ART_PREFIX}the-case/portraits/ilse.png" in fake.objects
    assert fake.objects[f"{ART_PREFIX}the-case/portraits/wouter.png"] == b"\x89PNG-wouter"


def test_a_bucket_lists_what_it_has_without_downloading_it(tmp_path) -> None:
    fake = FakeS3Art()
    store = S3Gallery("a-bucket", client=fake)
    store.put("the-case", "portraits", _art(tmp_path))
    fake.calls.clear()

    found = store.names("the-case", "portraits")

    assert found == {"ilse": "ilse.png", "wouter": "wouter.png"}
    assert not [c for c in fake.calls if c.startswith("get")], "listing downloaded a picture"


def test_a_bucket_hands_out_a_signed_link_rather_than_bytes() -> None:
    """The whole point. The picture never touches the application."""
    fake = FakeS3Art()

    link = S3Gallery("a-bucket", client=fake).link("the-case", "portraits", "ilse.png")

    assert link.startswith("https://")
    assert f"{ART_PREFIX}the-case/portraits/ilse.png" in link
    assert "X-Amz-Expires" in link, "a link with no expiry is a public object"
    assert not [c for c in fake.calls if c.startswith("get")], "signing is not a request"


def test_a_link_expires() -> None:
    from mystery.gallery import LINK_LIFE

    fake = FakeS3Art()
    S3Gallery("a-bucket", client=fake).link("the-case", "portraits", "ilse.png")

    assert LINK_LIFE <= 86400, "a link that outlives a session is a leak"
    assert LINK_LIFE >= 600, "a link that dies mid-game is a broken page"


def test_a_bucket_can_still_produce_the_bytes(tmp_path) -> None:
    fake = FakeS3Art()
    store = S3Gallery("a-bucket", client=fake)
    store.put("the-case", "portraits", _art(tmp_path))

    assert store.read("the-case", "portraits", "ilse.png") == b"\x89PNG-ilse"
    assert store.read("the-case", "portraits", "nobody.png") is None


def test_pictures_share_the_bucket_with_cases_and_do_not_collide(tmp_path) -> None:
    """One bucket is one thing to secure and one name to get right. The prefixes
    are what keep the shelf and the gallery out of each other's way."""
    from mystery.library import CASES, INDEX, S3Shelf

    fake = FakeS3Art()
    S3Shelf("a-bucket", client=fake).save(CASE, "a residency", "the_lie", 1)
    S3Gallery("a-bucket", client=fake).put("the-case", "portraits", _art(tmp_path))

    assert [k for k in fake.objects if k.startswith(CASES)]
    assert [k for k in fake.objects if k.startswith(INDEX)]
    assert [k for k in fake.objects if k.startswith(ART_PREFIX)]
    assert S3Shelf("a-bucket", client=fake).cards(), "art broke the shelf listing"


# --- which one you get -------------------------------------------------------


def test_the_gallery_follows_the_same_variable_as_the_shelf(monkeypatch) -> None:
    """There is no sensible deployment where the cases are in a bucket and the
    pictures are on a disk, so a second variable would only be a way to get them
    out of step."""
    monkeypatch.delenv("MYSTERY_BUCKET", raising=False)
    assert isinstance(gallery(), FileGallery)

    monkeypatch.setenv("MYSTERY_BUCKET", "a-bucket")
    assert isinstance(gallery(), S3Gallery)
    assert gallery()._client is None, "picking must not build a client"


# --- through the actual routes ------------------------------------------------


def _served(store, portraits):
    from mystery.solver import solve
    from mystery.web import Case, build_app

    case = Case(solve(CASE, seed=0), id="the-case", portraits=portraits)
    case.gallery = store
    return TestClient(build_app(case, lambda s, q: {"speech": "", "used": [], "refused": False}))


def test_the_route_serves_the_file_when_the_gallery_is_a_folder(tmp_path) -> None:
    _art(tmp_path)
    client = _served(FileGallery(tmp_path), {"ilse": "ilse.png"})

    got = client.get("/portrait/ilse.png")

    assert got.status_code == 200
    assert got.content == b"\x89PNG-ilse"


def test_the_route_redirects_to_s3_rather_than_carrying_the_picture(tmp_path) -> None:
    """A megabyte and a half per portrait, six per case. On a deployment the
    application must not be in the middle of that."""
    fake = FakeS3Art()
    store = S3Gallery("a-bucket", client=fake)
    store.put("the-case", "portraits", _art(tmp_path))
    client = _served(store, {"ilse": "ilse.png"})

    got = client.get("/portrait/ilse.png", follow_redirects=False)

    assert got.status_code == 307, "a link that expires must not be cached as a 301"
    assert "s3.example" in got.headers["location"]
    assert got.content == b"", "the picture went through the application"


def test_a_portrait_nobody_has_is_a_404(tmp_path) -> None:
    client = _served(FileGallery(tmp_path), {})

    assert client.get("/portrait/nobody.png").status_code == 404


# --- a missing optional package is not a crash (D-123) -----------------------


def _without_openai(monkeypatch):
    """Make `import openai` fail the way an uninstalled package does."""
    import builtins

    real = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)


def test_no_openai_installed_gives_no_portraits_rather_than_a_crash(monkeypatch, tmp_path):
    """`uv sync --extra aws` drops the `portraits` extra, which is a normal
    thing to do. It took the game down after the case was drafted and paid for,
    and the docstring had promised for months that failures are logged and
    dropped (D-123)."""
    from mystery.portraits import generate_portraits

    _without_openai(monkeypatch)

    assert generate_portraits(CASE, tmp_path, "portraits") == {}


def test_no_openai_installed_gives_no_scenery_rather_than_a_crash(monkeypatch, tmp_path):
    from mystery.scenery import generate_scenery

    _without_openai(monkeypatch)

    assert generate_scenery(CASE, "a castle", tmp_path, "scenery") == {}


def test_the_warning_says_how_to_fix_it(monkeypatch, tmp_path):
    from structlog.testing import capture_logs

    from mystery.portraits import generate_portraits

    _without_openai(monkeypatch)
    with capture_logs() as logged:
        generate_portraits(CASE, tmp_path, "portraits")

    said = [e for e in logged if e.get("event") == "portraits.no_package"]
    assert said and "uv sync" in said[0]["detail"]


# --- the endpoint the link is signed against (D-124) -------------------------


def test_a_presigned_link_is_signed_against_the_regional_endpoint(monkeypatch) -> None:
    """The bug that showed as "no images" and nothing else.

    `boto3.client("s3", region_name=...)` alone signs against the legacy global
    host `<bucket>.s3.amazonaws.com`. Outside us-east-1 that host answers a
    redirect; boto3 follows it, so every API call worked and the upload check
    passed. A browser cannot follow it, because a presigned signature is bound to
    the host it was made for, so the link 403s while the identical operation from
    Python succeeds.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAFAKE")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "fake")

    store = S3Gallery("mystery-cases-1234-eu-north-1-an", region="eu-north-1")
    link = store.link("a-case", "portraits", "ilse.png")

    host = link.split("/")[2]
    assert host.endswith("s3.eu-north-1.amazonaws.com"), host
    assert not host.endswith(".s3.amazonaws.com"), "signed against the global endpoint"


def test_the_shelf_and_the_gallery_share_one_client_builder() -> None:
    """Two clients that disagree about endpoints is the same bug twice."""
    import inspect

    from mystery.gallery import S3Gallery as G
    from mystery.library import s3_client

    assert "s3_client" in inspect.getsource(G.client.fget)
    assert "addressing_style" in inspect.getsource(s3_client)
