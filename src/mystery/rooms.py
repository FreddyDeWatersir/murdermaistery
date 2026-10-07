"""Rooms: several groups at once, one login each (D-208).

A room is a login name, the case it plays and one shared game. Caddy checks
the password and tells the game who logged in (`X-Remote-User`); the game
serves that login its room and nobody else's. Each room keeps its game under
its own name in the session store, so a restart, an update or a reboot picks
every evening up where it was.

The list lives in `var/rooms.json`. `mysteryctl room ...` edits it and the
Caddy password file together, and restarts the game.

    python -m mystery.rooms add marco the-oath-and-the-snow-d1f4-it
    python -m mystery.rooms remove marco
    python -m mystery.rooms fresh marco
    python -m mystery.rooms list
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOMS = Path("var/rooms.json")
SESSIONS = Path("var/sessions")
NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")


def session_id(user: str) -> str:
    """The game a room keeps, by name, so it survives a restart."""
    return f"room-{user}"


def read(path: Path = ROOMS) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("rooms", {})


def write(rooms: dict[str, dict[str, str]], path: Path = ROOMS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rooms": rooms}, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    from mystery.library import shelf

    args = list(sys.argv[1:] if argv is None else argv)
    what = args.pop(0) if args else "list"
    rooms = read()

    if what == "list":
        if not rooms:
            print("  No rooms yet.")
        for user, room in sorted(rooms.items()):
            print(f"  {user:16} {room['case']}")
        return 0

    if what in ("add", "remove", "fresh") and not args:
        print(f"  Which room? python -m mystery.rooms {what} NAME")
        return 1
    user = args[0]
    if not NAME.match(user):
        print("  A room name is 2 to 32 lowercase letters, digits, - or _.")
        return 1

    if what == "add":
        if len(args) < 2:
            print("  Which case? python -m mystery.rooms add NAME CASE_ID")
            return 1
        case_id = args[1]
        shelf().load(case_id)  # raises with the list of cases when it is not there
        rooms[user] = {"case": case_id}
        write(rooms)
        print(f"  Room {user!r} plays {case_id}.")
        return 0

    if what == "remove":
        rooms.pop(user, None)
        write(rooms)
        print(f"  Room {user!r} removed. Its game is kept until it expires.")
        return 0

    if what == "fresh":
        (SESSIONS / f"{session_id(user)}.json").unlink(missing_ok=True)
        print(f"  Room {user!r} starts a fresh game on the next restart.")
        return 0

    print("  add NAME CASE_ID | remove NAME | fresh NAME | list")
    return 1


if __name__ == "__main__":
    sys.exit(main())
