"""Optional generated backdrops: the place, and the rooms in it.

Same contract as `portraits.py` and for the same reason. It is decoration, it
costs money and half a minute, and every failure path falls back to the painted
gradient the page already has. Decoration must never be able to stop a game
starting.

    uv run python -m mystery.web --setting "..." --scenery

**One image: the establishing shot of the place.** It is the page background
from the first moment and every player sees it.

There used to be a picture per room as well, behind the Map, and they are gone
(D-102). The argument for them was that a room you can look at while deciding
whether somebody was really in it is doing work. In practice nobody looked: the
room backdrops were five sixths of the scenery bill and the least noticed thing
in the game. The map earns its keep by showing who is where, not by showing what
the wallpaper is like.

**No people in any of them.** The cast are portraits, the rooms are empty, and a
generated figure standing in a doorway would be a person the case does not
contain, in a room the player is reasoning about.
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog

from mystery.models import Mystery

log = structlog.get_logger()

# Landscape costs half again as much as square. There is one of these per case
# now rather than six (D-102), so scenery has gone from the larger half of the
# art bill to a rounding error on it. It sits under a heavy vignette, which is
# the best possible argument for the cheap tier.
PRICES = {"low": 0.016, "medium": 0.063, "high": 0.250}

STYLE = (
    "Muted noir interior illustration, painterly and flat, restrained "
    "desaturated palette, low warm light and long shadows, deep unlit corners, "
    "quiet and slightly abandoned. Wide establishing shot. Absolutely no people, "
    "no figures, no silhouettes. No text, no lettering, no border."
)


def _setting_prompt(mystery: Mystery, setting: str) -> str:
    return (
        f"{STYLE} The place: {setting}. This is the establishing shot of "
        f"{mystery.title.lower()}, on the evening somebody died there. Show the "
        f"whole space, empty, moments after everyone has left it."
    )


def generate_scenery(
    mystery: Mystery, setting: str, cache_dir: Path, key: str, quality: str = "low"
) -> dict[str, str]:
    """Return {"setting" or place id: relative file path}, missing meaning skip.

    Cached beside the mystery under its cache key, so replaying a seed is free
    and changing the prompt is not. Failures are logged and dropped rather than
    raised: half a house with pictures is a slightly odd-looking game, a crash
    is no game.
    """
    # The docstring above says failures are logged and dropped rather than
    # raised, and until D-123 that promise did not cover the failure most likely
    # to happen: the package not being installed at all. `uv sync --extra aws`
    # removes the `portraits` extra, which is a normal thing to do and took the
    # game down after the case was drafted and paid for (D-123).
    try:
        from openai import OpenAI
    except ImportError:
        log.warning(
            "scenery.no_package",
            detail="openai is not installed. Run: uv sync --extra portraits "
            "--extra aws. Playing without pictures.",
        )
        return {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("scenery.no_key", detail="set OPENAI_API_KEY or drop --scenery")
        return {}

    folder = cache_dir / key
    folder.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    jobs: list[tuple[str, str]] = [("setting", _setting_prompt(mystery, setting))]

    def one(job: tuple[str, str]) -> tuple[str, str] | None:
        name, prompt = job
        target = folder / f"{name}.png"
        if target.exists():
            return name, target.name

        try:
            result = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                # Landscape, because it sits behind a whole screen rather than
                # in a frame beside one.
                size="1536x1024",
                quality=quality,
                n=1,
            )
            target.write_bytes(base64.b64decode(result.data[0].b64_json))
            log.info("scenery.made", scene=name)
            return name, target.name
        except Exception as error:  # noqa: BLE001 - decoration must never break the game
            log.warning("scenery.failed", scene=name, error=str(error))
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(one, jobs))

    return {name: file for pair in results if pair for name, file in [pair]}
