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
NORMAL = {"field": 3, "shortcuts": 0, "motive": 1, "trail": 2, "liars_at_hour": 2}

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
}

# Some shapes hide a shortcut from the player by construction, so it cannot be
# used even when the ground truth would allow it. Mutual alibi gives the killer
# a false witness for the hour; the wrong hour means nobody knows which hour the
# murder was, so nothing keyed on it is a question a player can ask.
HIDDEN_BY_SHAPE = {
    "mutual_alibi": {"alone", "unplaced_liar"},
    "the_wrong_hour": {"alone", "lies_at_hour", "last_with"},
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
    shortcuts: list[str] = listed(default_factory=list)

    def meets(self, targets: dict[str, int] = NORMAL) -> bool:
        return (
            self.field >= targets["field"]
            and self.killer_in_field
            and len(self.shortcuts) <= targets["shortcuts"]
            and self.motive >= targets["motive"]
            and self.trail >= targets["trail"]
            and self.liars_at_hour >= targets["liars_at_hour"]
        )


def measure(mystery: Mystery, shape: str = "") -> Measures:
    """Everything above, from the ground truth. No model, no solving."""
    from mystery.stats import trail_depths

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
    }
    argued = sum(
        1
        for s in mystery.secrets
        if s.revealed_by and by.get(s.revealed_by) and not by[s.revealed_by].evidence
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
        shortcuts=[
            name for name, found in candidates.items() if name not in hidden and found == {killer}
        ],
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
}


def complaints(m: Measures, targets: dict[str, int] | None = None) -> list[str]:
    """Why a draft misses the targets, one sentence per number (D-188)."""
    targets = targets if targets is not None else GATE
    found = [_FIX[name] for name in m.shortcuts][: max(0, len(m.shortcuts) - targets["shortcuts"])]
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
