"""Four numbers that say how a case plays, instead of a dozen yes/no checks (D-186).

The advisories grew one at a time, each from one playtest, and by October three
families of them were asking the same question in different words: is there
more than one suspect (A4, A16, A18, A24), is the motive findable (A5, A13,
S3), and is there a trick that names the killer without the case (A2, A10,
A12, A20). Yes/no can say a case failed; it cannot say by how much, and it
cannot be averaged across a batch to see whether a change moved anything.

So four measurements:

- **Field.** Who has a reason (holds something damning) and who had the chance
  (alone at the murder hour, or lying about where they were then). The field
  is both. A case is a choice between people only when the field is three or
  more and the killer is in it.
- **Depth.** How many gates stand before the killer's motive, and before the
  deepest innocent trail (`stats.trail_depths`).
- **Shortcuts.** Naive questions a player can ask the grid or the secrets that
  return the killer and nobody else. Each one that does is a way to win
  without solving. The target is none.
- **Lies.** How many people lie about where they were, and how many lie about
  the murder hour, where a lone liar is the giveaway (A20).

Checked against the shelf when it was proposed: the two cases with a field of
three and no shortcuts were The Sixteen Kilometres, the best-received case so
far, and The Fourth Jump of the Day.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as listed

from mystery.critique import _gates_deep, _points_at
from mystery.knowledge import derive
from mystery.models import Mystery

# What a Normal case should reach (D-186, motive lowered to 1 by D-187: the best-
# received case had a one-gate motive). Difficulty will move these; until it
# exists they are what `--stats` reports against.
NORMAL = {
    "field": 3,
    "shortcuts": 0,
    "motive": 1,
    "trail": 2,
    "liars_at_hour": 2,
    # Per cent of gates opened by an object, with at least one on the road to
    # the motive and one on the deepest innocent trail (D-193). A third since
    # D-203: objects help, they are not the case.
    "objects": 33,
    # Fewest people who could have moved an object the killer could have moved
    # (D-202). Hard will ask three.
    "movers": 2,
    # Whether the objects must play the roles they were dealt (D-203).
    "dealt_objects": 1,
}

# What the generation gate holds a draft to (D-188). Normal until difficulty is
# an input. Read at call time, so the test suite can open it for the tests that
# are about plumbing rather than about quality.
GATE = dict(NORMAL)

# The questions, as a player would ask them.
SHORTCUTS = {
    "alone": "who was alone at the murder hour",
    "lies_at_hour": "who lies about the murder hour",
    "unplaced_liar": "which liar can nobody place",
    "only_liar": "who lies at all",
    "deepest": "whose trail is deepest",
    "last_with": "who was with the victim the hour before",
    "only_reason": "who has anything damning",
    "only_about_victim": "who has a secret about the victim",
    "found_room": "who says they were where the body was found, at the murder hour",
}

# Some shapes hide a shortcut from the player by construction, so it cannot be
# used even when the ground truth would allow it. Mutual alibi gives the killer
# a false witness for the hour; the wrong hour means nobody knows which hour the
# murder was, so nothing keyed on it is a question a player can ask.
HIDDEN_BY_SHAPE = {
    "mutual_alibi": {"alone", "unplaced_liar"},
    "the_wrong_hour": {"alone", "lies_at_hour", "last_with", "found_room"},
}


@dataclass
class Measures:
    reason: int = 0
    field: int = 0
    killer_in_field: bool = False
    motive: int = 0
    trail: int = 0
    liars: int = 0
    liars_at_hour: int = 0
    # Gates the player can only argue open, because the secret in front has no
    # object to put on the table (S5, retired as a warning in D-188).
    argued: int = 0
    gates: int = 0
    # Whether the road to the motive, and the deepest innocent trail, each have
    # at least one gate opened by an object (D-193). True where there is no gate.
    motive_object: bool = True
    trail_object: bool = True
    shortcuts: list[str] = listed(default_factory=list)
    # For every object move the killer could have made: how many people could
    # have made it (D-202). One is the killer, named by an object.
    movers: list[int] = listed(default_factory=list)
    # How deep the killer's trail and the deepest innocent's go (D-205), so a
    # draft told "the killer's is deepest" is also told by how much.
    killer_depth: int = 0
    innocent_depth: int = 0

    def movers_met(self, targets: dict[str, int] = NORMAL) -> bool:
        return all(n >= targets.get("movers", 0) for n in self.movers)

    def objects_met(self, targets: dict[str, int] = NORMAL) -> bool:
        share = targets.get("objects", 0)
        if not share or not self.gates:
            return True
        opened = self.gates - self.argued
        return opened * 100 >= share * self.gates and self.motive_object and self.trail_object

    def meets(self, targets: dict[str, int] = NORMAL) -> bool:
        return (
            self.objects_met(targets)
            and self.movers_met(targets)
            and
            self.field >= targets["field"]
            and self.killer_in_field
            and len(self.shortcuts) <= targets["shortcuts"]
            and self.motive >= targets["motive"]
            and self.trail >= targets["trail"]
            and self.liars_at_hour >= targets["liars_at_hour"]
        )


@dataclass
class Move:
    """An object leaving a room, and who could have taken it (D-202)."""

    thing: str
    name: str
    room: str
    slot: str
    could: set[str]


def possible_movers(mystery: Mystery) -> list[Move]:
    """Every object move the killer could have made, with everybody who could.

    Who could have taken a thing out of a room is everybody who was in that
    room between the last time somebody other than its mover saw it there and
    the hour it was gone. Not "who was in the room the hour it moved": in the
    Oath, a witness who saw the stylus-case on the bench at collation pinned it
    there an hour before it vanished, and left the killer alone with it (D-198).

    The victim takes nothing. A move the killer could not have made is an
    innocent's business and is not counted here.
    """
    victim, killer = mystery.victim, mystery.killer
    ordered = [s.id for s in sorted(mystery.slots, key=lambda s: s.index)]
    living = {p: rows for p, rows in mystery.placements.items() if p != victim}

    def in_room(room: str, slot: str) -> set[str]:
        return {p for p, rows in living.items() if rows.get(slot) == room}

    moves: list[Move] = []
    for thing in mystery.things:
        for i in range(1, len(ordered)):
            before, after = ordered[i - 1], ordered[i]
            room, then = thing.where.get(before), thing.where.get(after)
            if room is None or then is None or room == then:
                continue
            mover = thing.moved_by.get(after)
            seen = next(
                (j for j in range(i - 1, -1, -1) if in_room(room, ordered[j]) - {mover}),
                -1,
            )
            could = set().union(*(in_room(room, ordered[j]) for j in range(seen + 1, i + 1)))
            if killer in could:
                moves.append(Move(thing.id, thing.name, room, after, could))
    return moves


def mover_complaints(mystery: Mystery, targets: dict[str, int] | None = None) -> list[str]:
    """Objects that name the killer, said so the redraft can fix them (D-202).

    Soft: sent back while there are drafts left, and a case still like this
    after the last one is kept and counted easier, not thrown away.
    """
    least = (targets if targets is not None else GATE).get("movers", 0)
    names = {c.id: c.name for c in mystery.characters}
    places = {p.id: p.name for p in mystery.places}
    labels = {s.id: s.label for s in mystery.slots}
    out = []
    for move in possible_movers(mystery):
        if len(move.could) >= least:
            continue
        who = ", ".join(sorted(names.get(p, p) for p in move.could))
        out.append(
            f"`{move.thing}` leaves {places.get(move.room, move.room)} at "
            f"{labels.get(move.slot, move.slot)}, and only {len(move.could)} "
            f"{'person' if len(move.could) == 1 else 'people'} could have taken it "
            f"({who}), the killer among them; at least {least} must have had the "
            f"chance. Put somebody else through that room between the last time it "
            f"was seen there and then, or let nobody see it there for longer, or do "
            f"not move it at all."
        )
    return out


def measure(mystery: Mystery, shape: str = "") -> Measures:
    """Everything above, from the ground truth. No model, no solving."""
    from mystery.stats import trail_depths

    if shape == "open":
        # The model chose the protection (D-192); hide what that choice hides.
        from mystery.topology import classify

        shape = classify(mystery)
    killer, victim = mystery.killer, mystery.victim
    suspects = [c.id for c in mystery.characters if c.id != victim]
    scene = mystery.murder_scene
    hour = scene.slot if scene else None
    ordered = sorted(mystery.slots, key=lambda s: s.index)
    before = next(
        (ordered[i - 1].id for i, s in enumerate(ordered) if s.id == hour and i > 0), None
    )

    def where(person: str, slot: str | None) -> str | None:
        return mystery.placements.get(person, {}).get(slot) if slot else None

    rooms: dict[str | None, list[str]] = {}
    for person in suspects:
        rooms.setdefault(where(person, hour), []).append(person)
    alone = {p for room in rooms.values() if len(room) == 1 for p in room}

    liars = {c.character for c in mystery.false_claims}
    at_hour = {c.character for c in mystery.false_claims if c.slot == hour}
    knowledge = derive(mystery)
    unplaced = {
        c.character
        for c in mystery.false_claims
        if not any(
            knowledge[o.id].saw(c.character, c.slot)
            for o in mystery.characters
            if o.id not in (c.character, victim)
        )
    }

    by = {s.id: s for s in mystery.secrets}
    reason = {s.holder for s in mystery.secrets if s.damning and s.holder in suspects}
    about_victim = {s.holder for s in mystery.secrets if s.about == victim and s.holder in suspects}
    depth: dict[str, int] = {}
    for secret in mystery.secrets:
        if not secret.damning:
            continue
        who = secret.holder if secret.is_motive else _points_at(secret, mystery)
        if who in suspects:
            depth[who] = max(depth.get(who, 0), _gates_deep(secret, by))
    top = max(depth.values(), default=0)
    deepest = {p for p, d in depth.items() if d == top} if depth else set()

    last_with = {
        p for p in suspects if before and where(p, before) == where(victim, before)
    }

    # By their own account (D-193): where a liar says they were, where anyone
    # else was. The room the body was found in is the one thing about the
    # killing every player is told.
    found = mystery.found_in
    said = {
        p: (mystery.lie_by(p).place if mystery.lie_by(p) and mystery.lie_by(p).slot == hour
            else where(p, hour))
        for p in suspects
    }
    in_found_room = {p for p, room in said.items() if found and room == found}

    opportunity = alone | at_hour
    candidates = {
        "alone": alone,
        "lies_at_hour": at_hour,
        "unplaced_liar": unplaced,
        "only_liar": liars,
        "deepest": deepest,
        "last_with": last_with,
        "only_reason": reason,
        "only_about_victim": about_victim,
        "found_room": in_found_room,
    }
    argued = sum(
        1
        for s in mystery.secrets
        if s.revealed_by and by.get(s.revealed_by) and not by[s.revealed_by].evidence
    )
    def chain(secret) -> list:
        seen, out, step = set(), [], secret
        while step is not None and step.id not in seen:
            seen.add(step.id)
            out.append(step)
            step = by.get(step.revealed_by) if step.revealed_by else None
        return out

    def has_object(secret) -> bool:
        gated = [s for s in chain(secret) if s.revealed_by and by.get(s.revealed_by)]
        return not gated or any(by[s.revealed_by].evidence for s in gated)

    gates = sum(1 for s in mystery.secrets if s.revealed_by and by.get(s.revealed_by))
    motive_secret = next((s for s in mystery.secrets if s.is_motive), None)
    road = {s.id for s in chain(motive_secret)} if motive_secret else set()
    innocent = [
        s
        for s in mystery.secrets
        if s.damning
        and s.id not in road
        and _points_at(s, mystery) not in (killer, victim)
    ]
    deepest_innocent = max((_gates_deep(s, by) for s in innocent), default=0)
    trail_object = not deepest_innocent or any(
        has_object(s) for s in innocent if _gates_deep(s, by) == deepest_innocent
    )

    hidden = HIDDEN_BY_SHAPE.get(shape, set())
    motive, trail = trail_depths(mystery)
    return Measures(
        reason=len(reason),
        field=len(reason & opportunity),
        killer_in_field=killer in (reason & opportunity),
        motive=motive,
        trail=trail,
        liars=len(liars),
        liars_at_hour=len(at_hour),
        argued=argued,
        gates=gates,
        motive_object=has_object(motive_secret) if motive_secret else True,
        trail_object=trail_object,
        shortcuts=[
            name for name, found in candidates.items() if name not in hidden and found == {killer}
        ],
        movers=[len(m.could) for m in possible_movers(mystery)],
        killer_depth=depth.get(killer, 0),
        innocent_depth=max((d for p, d in depth.items() if p != killer), default=0),
    )


# What each failing number tells the drafter, in terms it can act on. The model
# reads these, never the player, so they can be as plain as they need to be.
_FIX = {
    "alone": "The killer is the only suspect alone at the murder hour. Leave at least "
    "one innocent unwitnessed at that hour too, for their own reasons.",
    "lies_at_hour": "The killer is the only person lying about the murder hour. Somebody "
    "innocent must lie about that same hour, for a reason of their own.",
    "unplaced_liar": "The killer is the only liar nobody can place. At least one innocent "
    "must also have been unwitnessed when they lied about where they were.",
    "only_liar": "The killer is the only person who lies about where they were. At "
    "least two innocents must lie too.",
    "deepest": "The killer's trail is the deepest thing in the case, so following "
    "whatever goes deepest finds them. An innocent's damning trail must go at least as "
    "deep, and must not be on the road to the killer's motive.",
    "last_with": "Only the killer was with the victim in the hour before the murder. Put "
    "somebody innocent with the victim in that hour as well.",
    "only_reason": "Only the killer holds anything damning. At least two innocents need "
    "a secret that would put them on the list on its own.",
    "only_about_victim": "Only the killer has a secret about the victim. At least two "
    "innocents need one too.",
    "found_room": "The killer is the only one who, by their own account, was in the room "
    "where the body was found at the murder hour. That room is the one fact about the "
    "killing everybody is told. Either the body was carried out of the room the killer "
    "was in, or the killer gives a different room, or somebody innocent puts themselves "
    "there too.",
}


def complaints(m: Measures, targets: dict[str, int] | None = None) -> list[str]:
    """Why a draft misses the targets, one sentence per number (D-188)."""
    targets = targets if targets is not None else GATE
    def fix(name: str) -> str:
        if name != "deepest":
            return _FIX[name]
        # With the numbers (D-205): three drafts in a row were told only that
        # the killer's was deepest, and made it deeper.
        return (
            f"The killer's trail is {m.killer_depth} gates deep and the deepest "
            f"innocent's is {m.innocent_depth}, so following whatever goes deepest "
            f"finds the killer. Bring one innocent's damning trail to "
            f"{m.killer_depth} gates (level is fine), not on the road to the "
            f"killer's motive."
        )

    found = [fix(name) for name in m.shortcuts][: max(0, len(m.shortcuts) - targets["shortcuts"])]
    if targets["field"] and (m.field < targets["field"] or not m.killer_in_field):
        found.append(
            f"Only {m.field} suspects have both a damning reason and the chance at the "
            f"murder hour (alone then, or lying about where they were). There must be at "
            f"least {targets['field']}, with the killer among them, so the player is "
            f"choosing between whole theories rather than confirming one."
        )
    if m.motive < targets["motive"]:
        found.append(
            "The killer's motive is reachable with no gate in front of it. It must sit "
            "behind at least one other secret."
        )
    if m.trail < targets["trail"]:
        found.append(
            f"The deepest innocent trail is {m.trail} gate(s) deep; it must be at least "
            f"{targets['trail']}: a damning secret about somebody innocent, behind other "
            f"secrets, and not on the road to the killer's motive."
        )
    if not m.objects_met(targets):
        share = targets.get("objects", 0)
        opened = m.gates - m.argued
        found.append(
            f"{opened} of {m.gates} gates open with an object the player can put on the "
            f"table; at least {share}% must, including at least one on the road to the "
            f"killer's motive and one on the deepest innocent trail. A gate opens with an "
            f"object when the secret named in `revealed_by` carries `evidence`."
            + ("" if m.motive_object else " The road to the motive has none.")
            + ("" if m.trail_object else " The deepest innocent trail has none.")
        )
    if m.liars_at_hour < targets["liars_at_hour"]:
        found.append(
            f"Only {m.liars_at_hour} people lie about where they were at the murder hour; "
            f"there must be at least {targets['liars_at_hour']}."
        )
    return found


def ties(mystery: Mystery) -> dict[str, int]:
    """How many other suspects each suspect is tied to through the secrets.

    A tie is a secret one holds about the other, or a secret one holds that the
    other knows. The same web A19 looks for islands in, counted instead.
    """
    victim = mystery.victim
    suspects = {c.id for c in mystery.characters if c.id != victim}
    linked: dict[str, set[str]] = {p: set() for p in suspects}
    for s in mystery.secrets:
        others = {s.about, *s.known_by} & suspects
        for other in others - {s.holder}:
            if s.holder in suspects:
                linked[s.holder].add(other)
                linked[other].add(s.holder)
    return {p: len(o) for p, o in linked.items()}


def position_landed(mystery: Mystery) -> bool | None:
    """Did the killer end up where the deal put them (D-188)?

    None when nothing was dealt, or when the position is not something the
    ground truth can show (a mourner's grief is in the writing, not the web).
    """
    position, killer = mystery.killer_position, mystery.killer
    held = [s for s in mystery.secrets if s.holder == killer]
    degree = ties(mystery)
    if position == "hub":
        return bool(degree) and degree.get(killer, 0) == max(degree.values())
    if position == "outsider":
        return bool(degree) and degree.get(killer, 0) == min(degree.values())
    if position == "clean_hands":
        return all(s.is_motive for s in held)
    if position == "small_sinner":
        return any(
            not s.is_motive and not s.damning and not s.revealed_by for s in held
        )
    return None
