"""Optional generated portraits.

Strictly additive. The game draws serviceable SVG faces with no network and no
key, and this replaces them with generated images when you ask for it and it
works. Every failure path falls back to the drawn version, because a portrait is
decoration and decoration must never be able to stop a game starting.

    uv run python -m mystery.web --setting "..." --portraits

Costs roughly five cents a case at current prices and adds twenty to thirty
seconds to generation, since the five are requested in parallel. Cached beside
the mystery, so replaying a seed is free.
"""

import base64
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from mystery.models import Mystery

log = structlog.get_logger()

STYLE = (
    "Muted noir character portrait, head and shoulders, painterly flat "
    "illustration, restrained desaturated palette, soft directional light, plain "
    "dark background, serious expression, no text, no border."
)


def _prompt(mystery: Mystery, character) -> str:
    look = character.look or "an adult, dressed for the occasion"
    return (
        f"{STYLE} The subject: {look}. "
        f"They are a guest at {mystery.title.lower()}, being questioned after a "
        f"death. Their manner is {character.manner or 'guarded'}."
    )


def generate_portraits(mystery: Mystery, cache_dir: Path, key: str) -> dict[str, str]:
    """Return {character id: relative file path}, missing entries meaning fall back.

    Failures are logged and dropped rather than raised. Half a cast with images
    and half drawn is a slightly odd-looking game; a crash is no game.
    """
    from openai import OpenAI

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
