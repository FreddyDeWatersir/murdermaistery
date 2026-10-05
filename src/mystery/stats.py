"""Everything the engine has made, measured, without spoiling any of it (D-185).

`--score` measures the generation cache, which holds only drafts that passed.
That corpus cannot say what the gates reject, how often, or what a shelved case
costs once the rejected drafts are counted, and those are the numbers every
change to a gate or a deck is judged by. So this reads three places:

- `var/cases`, the shelf: what can be played.
- `var/rejected`, every draft a gate sent back, kept since D-156.
- `var/sessions` and `var/transcripts` (sessions copied down from the server),
  to say which cases have already been played.

It is read before playing, so it names nothing that spoils a case: no
suspects, no secrets, and no shapes unless asked (`--spoilers`), because a
player who knows the case is "the finder" knows who to look at.

Split by prompt version (D-166), one block each, because a rate measured over
two sets of instructions belongs to neither.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from mystery.critique import _gates_deep, _points_at
from mystery.measures import NORMAL, SHORTCUTS, Measures, measure, position_landed
from mystery.models import Mystery
from mystery.palette import world_named
from mystery.topology import assess

# Measured over the October batch: eighteen drafts by Opus 5, 0.37 to 0.45
# dollars each. Drafts do not record their own price, so cost per shelved case
# is drafts times this, and the report says it is an estimate.
DRAFT_USD = 0.41


@dataclass
class Record:
    """One draft, kept or rejected."""

    source: str  # "shelf" or "rejected"
    cohort: str
    seed: str = ""
    title: str = ""
    shape: str = ""
    world: str = ""
    motive_depth: int = 0
    rival_depth: int = 0
    fired: set[str] = field(default_factory=set)
    reason: str = ""  # why a rejected draft was rejected
    asked: int = 0  # questions asked about this case in local sessions
    case_id: str = ""
    measures: Measures | None = None
    position: str = ""  # where the killer was dealt (D-188), a spoiler
    landed: bool | None = None  # whether the draft put them there


def trail_depths(mystery: Mystery) -> tuple[int, int]:
    """How deep the killer's motive is, and how deep the deepest innocent trail.

    Depth is gates: secrets that must be opened before this one can be. The
    innocent trail counts only damning secrets that point at somebody other
    than the killer or the victim and are not on the road to the motive, which
    is exactly what A24 compares.
    """
    by = {secret.id: secret for secret in mystery.secrets}
    motive = next((s for s in mystery.secrets if s.is_motive), None)
    wanted = _gates_deep(motive, by) if motive else 0

    road: set[str] = set()
    step = motive
    while step is not None and step.id not in road:
        road.add(step.id)
        step = by.get(step.revealed_by) if step.revealed_by else None

    best = 0
    for secret in mystery.secrets:
        if not secret.damning or secret.id in road:
            continue
        if _points_at(secret, mystery) in (mystery.killer, mystery.victim):
            continue
        best = max(best, _gates_deep(secret, by))
    return wanted, best


def _why(complaints: list[str]) -> str:
    """Which gate sent a draft back, in one word."""
    text = " ".join(complaints)
    if "deepest thing pointing" in text:
        return "A24"
    if "never passes through" in text:
        return "A26"
    if not complaints:
        return "unknown"
    return "structure"


def _measure(record: Record, mystery: Mystery) -> Record:
    record.motive_depth, record.rival_depth = trail_depths(mystery)
    try:
        record.measures = measure(mystery, record.shape)
    except Exception:  # noqa: BLE001 - a draft too broken to measure is still counted
        record.measures = None
    record.position = mystery.killer_position
    try:
        record.landed = position_landed(mystery)
    except Exception:  # noqa: BLE001
        record.landed = None
    try:
        record.fired = {a.check for a in assess(mystery, record.shape)}
    except Exception:  # noqa: BLE001 - a draft that breaks a check is still counted
        record.fired = set()
    return record


def collect(var: Path = Path("var")) -> list[Record]:
    """Read the shelf, the rejected drafts and the local sessions."""
    # Keyed by session id, so a session that is both here and copied down from
    # the server is counted once.
    sessions: dict[str, tuple[str, int]] = {}
    for path in [*(var / "sessions").glob("*.json"), *(var / "transcripts").glob("*.json")]:
        try:
            session = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sessions[path.stem] = (session.get("case_id", ""), len(session.get("statements", [])))
    asked: Counter[str] = Counter()
    for case_id, questions in sessions.values():
        asked[case_id] += questions

    records: list[Record] = []
    for path in sorted((var / "cases").glob("*.json")):
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            mystery = Mystery.model_validate(saved["mystery"])
        except Exception:  # noqa: BLE001 - one unreadable file must not hide the rest
            continue
        record = Record(
            source="shelf",
            cohort=mystery.built_with or "before the stamp",
            seed=str(saved.get("seed", "")),
            title=saved.get("title", mystery.title),
            shape=saved.get("topology", ""),
            # Only a world the deck knows; a draft once scribbled its own (D-183).
            world=mystery.world if world_named(mystery.world) else "",
            asked=asked.get(saved.get("id", ""), 0),
            case_id=saved.get("id", ""),
        )
        records.append(_measure(record, mystery))

    for path in sorted((var / "rejected").glob("*.json")):
        try:
            kept = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        complaints = kept.get("complaints", [])
        if isinstance(complaints, str):
            complaints = json.loads(complaints)
        record = Record(
            source="rejected",
            cohort=kept.get("built_with") or "unstamped",
            seed=str(kept.get("seed", "")),
            shape=kept.get("topology", ""),
            reason=_why(complaints),
        )
        try:
            mystery = Mystery.model_validate(kept["draft"])
        except Exception:  # noqa: BLE001 - an unparseable draft is still a draft paid for
            record.reason = "unparseable"
            records.append(record)
            continue
        record.title = mystery.title
        records.append(_measure(record, mystery))
    return records


def _mean(values: list[int]) -> str:
    return f"{sum(values) / len(values):.1f}" if values else "-"


def report(records: list[Record], spoilers: bool = False) -> str:
    """The numbers, one block per prompt version, then the shelf."""
    if not records:
        return "  Nothing on the shelf and nothing rejected yet."

    lines: list[str] = []
    cohorts: dict[str, list[Record]] = defaultdict(list)
    for record in records:
        cohorts[record.cohort].append(record)

    # Newest instructions last, so the number to read is at the bottom.
    for cohort in sorted(cohorts, key=lambda c: (c != "before the stamp", c == "unstamped", c)):
        group = cohorts[cohort]
        shelved = [r for r in group if r.source == "shelf"]
        rejected = [r for r in group if r.source == "rejected"]
        lines.append(f"\n  PROMPT {cohort}")
        if rejected and shelved:
            share = len(shelved) / len(group)
            per = len(group) * DRAFT_USD / len(shelved)
            lines.append(
                f"    drafts {len(group)}   shelved {len(shelved)}   yield {share:.0%}"
                f"   about ${per:.2f} per shelved case"
            )
        else:
            lines.append(f"    shelved {len(shelved)}   rejected {len(rejected)}")
        if rejected:
            why = Counter(r.reason for r in rejected)
            lines.append("    rejected for: " + ", ".join(f"{k} {v}" for k, v in why.most_common()))
        measured = [r for r in group if r.reason != "unparseable"]
        lines.append(
            f"    depth: motive {_mean([r.motive_depth for r in measured])}"
            f" (shelved {_mean([r.motive_depth for r in shelved])}),"
            f" innocent trail {_mean([r.rival_depth for r in measured])}"
            f" (shelved {_mean([r.rival_depth for r in shelved])})"
        )
        scored = [r.measures for r in measured if r.measures is not None]
        if scored:
            no_tricks = sum(1 for m in scored if not m.shortcuts)
            lines.append(
                f"    field {_mean([m.field for m in scored])}"
                f"   shortcuts {_mean([len(m.shortcuts) for m in scored])}"
                f" (none in {no_tricks} of {len(scored)})"
                f"   liars {_mean([m.liars for m in scored])},"
                f" at the murder hour {_mean([m.liars_at_hour for m in scored])}"
            )
            tricks = Counter(name for m in scored for name in m.shortcuts)
            if tricks:
                lines.append(
                    "    shortcuts that work: "
                    + ", ".join(f"{SHORTCUTS[n]} {c}" for n, c in tricks.most_common())
                )
            argued = sum(1 for m in scored if m.argued)
            lines.append(
                f"    gates only arguable (no object): {_mean([m.argued for m in scored])}"
                f" per draft, in {argued} of {len(scored)}"
            )
            normal = sum(1 for m in scored if m.meets())
            lines.append(f"    meets Normal {NORMAL}: {normal} of {len(scored)}")
        dealt = [r for r in measured if r.landed is not None]
        if dealt:
            # Which position a case was dealt is a spoiler; the rate is not,
            # unless it is broken down by position.
            hit = sum(1 for r in dealt if r.landed)
            line = f"    killer landed where dealt: {hit} of {len(dealt)}"
            if spoilers:
                by: dict[str, list[bool]] = defaultdict(list)
                for r in dealt:
                    by[r.position].append(bool(r.landed))
                line += "  (" + ", ".join(
                    f"{k} {sum(v)}/{len(v)}" for k, v in sorted(by.items())
                ) + ")"
            lines.append(line)
        fired = Counter(check for r in measured for check in r.fired)
        if measured and fired:
            rates = "  ".join(
                f"{check} {count / len(measured):.0%}" for check, count in fired.most_common()
            )
            lines.append(f"    checks firing: {rates}")

    shelf = [r for r in records if r.source == "shelf"]
    if shelf:
        lines.append("\n  SHELF, unplayed first, best measured first")
        lines.append(
            f"    {'':<34}  {'':<16}  motive trail field tricks  hour-liars  normal"
        )

        # Unplayed first, then cases that meet Normal, then a wide field with few
        # tricks, which is what the two best-received cases had in common.
        def rank(r: Record) -> tuple:
            m = r.measures or Measures()
            return (r.asked > 0, not m.meets(), -(m.field - len(m.shortcuts)), r.title)

        shelf.sort(key=rank)
        for r in shelf:
            m = r.measures or Measures()
            played = f"played ({r.asked} q)" if r.asked else "unplayed"
            where = r.world or "present day"
            # Which shortcut works is a spoiler ("whose trail is deepest" names
            # the killer), so only the count unless asked.
            extra = f"  {r.shape}  {', '.join(m.shortcuts)}" if spoilers else ""
            lines.append(
                f"    {r.title[:34]:<34}  {where[:16]:<16}  {m.motive:^6} {m.trail:^5}"
                f" {m.field:^5} {len(m.shortcuts):^6}  {m.liars_at_hour:^10}"
                f"  {'yes' if m.meets() else '-':^6}  {played}{extra}"
            )
        lines.append(f"\n    ids: {', '.join(r.case_id for r in shelf if not r.asked)}")
    if not spoilers:
        lines.append("\n  Shapes and which shortcuts work are hidden. --spoilers shows them.")
    return "\n".join(lines)
