"""Is there a way in, and does it lead anywhere.

Every check in `critique.py` measures one property of a case in isolation. None
of them answers the question the whole project was specified around: can a
player who knows nothing get from the first question to the right answer. A pile
of satisfied local properties does not add up to that, and the gap is not
theoretical (D-068).

The concrete failure it misses is a cycle. Secret A is gated behind B and B is
gated behind A, so neither ever surfaces. Both secrets exist, both have holders,
both have breaking points, every advisory passes, and the case cannot be solved
by anyone. The same shape of bug hides a motive behind a chain whose first link
does not exist.

So this module does the one thing the others do not: it computes a closure.
Start from the secrets a player can get cold, add whatever those unlock, repeat
until nothing changes, and see what is left outside.

**What it can and cannot know.** Gating through `revealed_by` is structure and
is followed exactly. Whether a suspect *actually* gives something up depends on
`breaks_when`, which is a sentence in a prompt and cannot be evaluated here. So
this is a necessary condition, not a sufficient one: a case that fails is
definitely unsolvable, a case that passes is merely not provably broken. That is
worth having anyway. It is the difference between "no rule objected" and "there
is a path".
"""

from dataclasses import dataclass, field

from mystery.critique import Advisory
from mystery.knowledge import analyse_alibi, derive
from mystery.models import Mystery, Secret


@dataclass
class Solvability:
    """What a player could get to, starting from nothing."""

    way_in: list[str] = field(default_factory=list)
    reachable: list[str] = field(default_factory=list)
    sealed: list[str] = field(default_factory=list)
    motive: str | None = None
    motive_is_reachable: bool = False
    alibi_is_breakable: bool = False

    @property
    def winnable(self) -> bool:
        """Both halves of the charge sheet: the person, and the reason."""
        return self.alibi_is_breakable and self.motive_is_reachable


def _can_be_told(secret: Secret, mystery: Mystery) -> bool:
    """Somebody, somewhere, is able to say this out loud.

    Two mouths it can come from: its holder, or anyone who knows it without it
    being theirs. One exception, and it is the reason this function exists: the
    killer never gives up why they did it (D-066), so their motive can only ever
    reach the player second hand.
    """
    if secret.known_by:
        return True
    return not (secret.holder == mystery.killer and secret.is_motive)


def analyse(mystery: Mystery) -> Solvability:
    motive = next(
        (s for s in mystery.secrets if s.holder == mystery.killer and s.is_motive), None
    )

    def unlocked(secret: Secret, known: set[str]) -> bool:
        if not _can_be_told(secret, mystery):
            return False
        if not secret.revealed_by:
            return True
        return secret.revealed_by in known

    # The fixed point. Anything still outside `known` when this stops moving is
    # unreachable however many questions the player asks, which includes every
    # cycle and every chain hanging off a gate that does not exist.
    known: set[str] = set()
    while True:
        found = {s.id for s in mystery.secrets if s.id not in known and unlocked(s, known)}
        if not found:
            break
        known |= found

    analysis = analyse_alibi(mystery, derive(mystery))

    return Solvability(
        way_in=sorted(s.id for s in mystery.secrets if unlocked(s, set())),
        reachable=sorted(known),
        sealed=sorted(s.id for s in mystery.secrets if s.id not in known),
        motive=motive.id if motive else None,
        motive_is_reachable=bool(motive and motive.id in known),
        alibi_is_breakable=not analysis.claim_holds and analysis.breakable,
    )


def why_not(mystery: Mystery) -> list[Advisory]:
    """The solvability findings, in the same shape as every other check.

    These are advisories rather than validator rules on purpose. The analysis is
    structural and the game is not: a case this module calls unwinnable really
    is unwinnable, but the reverse does not hold, and a rule that fails a case
    on a necessary-condition argument would eventually throw away a good one.
    What it does buy is that an unplayable case is now loud rather than silent.
    """
    if not mystery.secrets:
        return []

    report = analyse(mystery)
    found: list[Advisory] = []
    summaries = {s.id: s.summary for s in mystery.secrets}

    if not report.way_in:
        found.append(
            Advisory(
                check="S1",
                message=(
                    "There is no way in. Every secret in the case is gated behind "
                    "another one, so the player's first question can never land and "
                    "nothing at all opens"
                ),
            )
        )

    for secret_id in report.sealed:
        found.append(
            Advisory(
                check="S2",
                message=(
                    f"{secret_id!r} can never surface: {summaries.get(secret_id, '')!r}. "
                    f"Its gate is unreachable, missing, or part of a loop. It is in the "
                    f"ground truth and nowhere a player can get to"
                ),
            )
        )

    if report.motive and not report.motive_is_reachable:
        found.append(
            Advisory(
                check="S3",
                message=(
                    f"The motive {report.motive!r} cannot be reached, so the best "
                    f"ending in the game is unreachable. The player can name the "
                    f"killer and can never say why"
                ),
            )
        )

    for claim in mystery.false_claims:
        if claim.covers and claim.covers not in report.reachable:
            found.append(
                Advisory(
                    check="S4",
                    message=(
                        f"{claim.character!r} lies to cover {claim.covers!r}, which can "
                        f"never surface. The player catches the lie and can never find "
                        f"out what it was for"
                    ),
                )
            )

    return found


def report(mystery: Mystery) -> str:
    """A few lines for the terminal, because this is the thing worth reading
    before spending an evening on a case."""
    r = analyse(mystery)
    lines = [
        f"Way in:      {', '.join(r.way_in) or 'NOTHING'}",
        f"Reachable:   {len(r.reachable)} of {len(mystery.secrets)} secrets",
        f"Sealed:      {', '.join(r.sealed) or 'none'}",
        f"Alibi:       {'breakable' if r.alibi_is_breakable else 'NOT BREAKABLE'}",
        f"Motive:      {'findable' if r.motive_is_reachable else 'NOT FINDABLE'}",
        f"Winnable:    {'yes' if r.winnable else 'NO'}",
    ]
    return "\n".join(lines)
