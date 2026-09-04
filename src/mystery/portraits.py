"""Optional generated portraits.

Strictly additive. The game draws serviceable SVG faces with no network and no
key, and this replaces them with generated images when you ask for it and it
works. Every failure path falls back to the drawn version, because a portrait is
decoration and decoration must never be able to stop a game starting.

    uv run python -m mystery.web --setting "..." --portraits

Cached beside the case, so replaying one is free (D-073).

**On cost, having got this badly wrong once (D-082).** A portrait is not five
cents. At the API's default quality it is about seventeen, and a case asks for
five of them alongside six backdrops, so `--art` was quietly costing well over
two dollars a go. The quality is now chosen explicitly rather than inherited,
and the default is the cheap tier, because a portrait that will be feathered
into a dim room does not need the expensive one.
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog

from mystery.models import Mystery

log = structlog.get_logger()

# What a portrait costs at each tier, for the estimate printed before spending
# anything. 1024x1024.
PRICES = {"low": 0.011, "medium": 0.042, "high": 0.167}

STYLE = (
    "Muted noir character portrait, head and shoulders, painterly flat "
    "illustration, restrained desaturated palette, soft directional light, plain "
    "dark background, serious expression, no text, no border."
)


def _prompt(mystery: Mystery, character) -> str:
    """One picture of one person, with the parts that are not negotiable first.

    `gender` leads, and it is stated as a requirement rather than mentioned
    (D-095). It exists for exactly this: D-074 added it because the *drawn* SVG
    faces were inferring gender from the `look` sentence and getting it wrong
    whenever the sentence did not say. That fix reached the drawings and the page
    and never reached this prompt, so the image model was left making the same
    inference from the same sentence, and a woman in the cast came back as a man
    in her portrait.

    `role` is in here too, because a portrait of a foreman of forty years and a
    portrait of a wine journalist should not be interchangeable, and the role is
    public anyway.
    """
    look = character.look or "an adult, dressed for the occasion"
    who = character.gender.strip()
    subject = f"a {who}" if who else "a person"

    lines = [
        STYLE,
        f"The subject is {subject}. This is not optional: the portrait must "
        f"clearly show {subject}.",
        f"Appearance: {look}.",
    ]
    if character.role:
        lines.append(f"They are {character.role.rstrip('.')}.")
    lines.append(
        f"They are at {mystery.title.lower()}, being questioned after a death. "
        f"Their manner is {character.manner or 'guarded'}."
    )
    return " ".join(lines)


def generate_portraits(
    mystery: Mystery, cache_dir: Path, key: str, quality: str = "low"
) -> dict[str, str]:
    """Return {character id: relative file path}, missing entries meaning fall back.

    Failures are logged and dropped rather than raised. Half a cast with images
    and half drawn is a slightly odd-looking game; a crash is no game.
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
            "portraits.no_package",
            detail="openai is not installed. Run: uv sync --extra portraits "
            "--extra aws. Playing without pictures.",
        )
        return {}

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("portraits.no_key", detail="set OPENAI_API_KEY or drop --portraits")
        return {}

    folder = cache_dir / key
    folder.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    def one(character) -> tuple[str, str] | None:
        target = folder / f"{character.id}.png"
        if target.exists():
            return character.id, target.name

        try:
            result = client.images.generate(
                model="gpt-image-1",
                prompt=_prompt(mystery, character),
                size="1024x1024",
                quality=quality,
                n=1,
            )
            target.write_bytes(base64.b64decode(result.data[0].b64_json))
            log.info("portraits.made", character=character.id)
            return character.id, target.name
        except Exception as error:  # noqa: BLE001 - decoration must never break the game
            log.warning("portraits.failed", character=character.id, error=str(error))
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, mystery.characters))

    return {cid: name for pair in results if pair for cid, name in [pair]}
