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

# What a Normal case should reach. Difficulty will move these (D-186); until it
# exists they are what `--stats` reports against.
NORMAL = {"field": 3, "shortcuts": 0, "motive": 2, "trail": 2, "liars_at_hour": 2}

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
        shortcuts=[
            name for name, found in candidates.items() if name not in hidden and found == {killer}
        ],
    )
