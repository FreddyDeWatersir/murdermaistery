"""Quality advisories: the things that make a mystery bad without making it invalid.

The validator answers "is this broken". This answers "is this any good", and the
two are not the same question. The solver's first grid passed every rule and read
as five people wandering at random; the first real generated case was valid and
had a character finding a body halfway through the evening they were meant to be
under investigation for.

Nothing here fails a mystery. Advisories are reported and looked at, because most
of them are judgement calls with a threshold someone invented in four seconds
(D-025). What they buy is that the judgement calls become *visible and countable*
instead of being discovered by squinting at output.

Each advisory names a threshold and says why it was chosen, so that when one turns
out to be wrong there is something to argue with.
"""

from dataclasses import dataclass

from mystery.knowledge import analyse_alibi, derive
from mystery.models import Mystery

# A character who changes room more often than this reads as a random walk rather
# than a person at a party. Chosen by looking at the hand-built prototypes, where
# nobody moved more than twice in five slots and one character never moved at all.
MAX_MOVES_PER_CHARACTER = 2

# How many people should lack an alibi at the moment of the murder. One is the
# killer wearing a sign. Everyone is noise. Two to four means a missing alibi is
# suspicious without being conclusive, which is the entire genre.
ALIBI_GAP_RANGE = (2, 4)


@dataclass(frozen=True)
class Advisory:
    check: str
    message: str


def count_moves(mystery: Mystery, character: str) -> int:
    """How many times this character changes room across the evening."""
    ordered = sorted(mystery.slots, key=lambda s: s.index)
    trail = [mystery.placements.get(character, {}).get(slot.id) for slot in ordered]
    return sum(1 for a, b in zip(trail, trail[1:], strict=False) if a != b and b is not None)


def wandering(mystery: Mystery) -> list[Advisory]:
    """A1: characters who move too much to be believable."""
    return [
        Advisory(
            check="A1",
            message=(
                f"{character.name} changes room {count_moves(mystery, character.id)} "
                f"times in {len(mystery.slots)} slots. People at a gathering mostly "
                f"stay put, and a player cannot reconstruct a random walk"
            ),
        )
        for character in mystery.characters
        if count_moves(mystery, character.id) > MAX_MOVES_PER_CHARACTER
    ]


def alibi_breadth(mystery: Mystery) -> list[Advisory]:
    """A2: how many people were alone when the murder happened.

    Too few and the killer is the only person who cannot account for themselves.
    Too many and having no alibi means nothing at all.
    """
    murder = next(
        (
            c
            for c in mystery.constraints
            if c.is_bound
            and mystery.killer in c.people
            and mystery.victim in c.people
        ),
        None,
    )
    if murder is None:
        return [
            Advisory(
                check="A2",
                message=(
                    "No bound constraint puts the killer and the victim together, "
                    "so the murder itself is not in the timeline"
                ),
            )
        ]

    alone = [
        character.id
        for character in mystery.characters
        if character.id not in (mystery.victim,)
        and len(
            mystery.who_is_in(
                mystery.placements.get(character.id, {}).get(murder.slot, ""), murder.slot
            )
        )
        <= 1
    ]

    low, high = ALIBI_GAP_RANGE
    count = len(alone) + 1  # the killer, alone with the victim, counts

    if count < low:
        return [
            Advisory(
                check="A2",
                message=(
                    f"Only {count} character(s) lack an alibi at the murder. The "
                    f"killer is the obvious answer to the first question anyone asks"
                ),
            )
        ]
    if count > high:
        return [
            Advisory(
                check="A2",
                message=(
                    f"{count} characters lack an alibi at the murder. If nobody can "
                    f"account for themselves, a missing alibi carries no information"
                ),
            )
        ]
    return []


def everyone_conceals_something(mystery: Mystery) -> list[Advisory]:
    """A3: suspects with nothing to hide.

    The single most important property from playtesting. A suspect with nothing
    to conceal is a cooperative witness, and a cast of cooperative witnesses plus
    one liar is not a game.

    This used to look at exclusive constraints, which predated the secrets layer
    and was measuring the wrong thing: it reported characters as having nothing
    to hide while they were holding a documented secret. Two separate properties
    were tangled together and they are now separate advisories.
    """
    holders = {secret.holder for secret in mystery.secrets}

    return [
        Advisory(
            check="A3",
            message=(
                f"{character.name} conceals nothing, so there is nothing to "
                f"interrogate them about and no reason for them to be evasive"
            ),
        )
        for character in mystery.characters
        if character.id not in holders and character.id != mystery.victim
    ]


def everyone_has_an_unwitnessed_moment(mystery: Mystery) -> list[Advisory]:
    """A8: suspects who were in company for the entire evening.

    Holding a secret is not enough on its own. A character who was visibly in a
    crowded room from start to finish cannot have done anything, so their secret
    is colour rather than suspicion, and a player learns nothing by pressing
    them.
    """
    alone_at_some_point = set()

    for character in mystery.characters:
        for slot in mystery.slots:
            where = mystery.placements.get(character.id, {}).get(slot.id)
            if not where:
                continue
            # The victim does not count as company. Standing with a corpse is
            # not an alibi, and it is precisely the killer's unwitnessed moment.
            company = mystery.who_is_in(where, slot.id) - {mystery.victim}
            if len(company) == 1:
                alone_at_some_point.add(character.id)
                break

    return [
        Advisory(
            check="A8",
            message=(
                f"{character.name} is in company for the whole evening, so whatever "
                f"they are hiding, they had no opportunity and pressing them "
                f"cannot go anywhere"
            ),
        )
        for character in mystery.characters
        if character.id not in alone_at_some_point and character.id != mystery.victim
    ]


# What fraction of the suspects should be concealing something about the victim.
# In a case that works the victim is the hub: he had leverage over most of the
# room, so half the cast has a motive and the killer is not the only person with
# a reason to be evasive. Below this the cast is a set of unrelated subplots
# with one murder bolted on.
MIN_SUSPECTS_WITH_A_STAKE_IN_THE_VICTIM = 0.5


def victim_is_a_hub(mystery: Mystery) -> list[Advisory]:
    """A4: does anyone other than the killer have a reason to fear the victim?

    The failure this catches is the one that separates a generated case from a
    written one. Give a model five suspects and it will hand back five parallel
    subplots, an affair here, an embezzlement there, each self-contained, and
    only one of them touching the person who died. Then the killer is the only
    character with a motive and the case solves itself.
    """
    if mystery.victim is None:
        return []
    if not mystery.secrets:
        return [
            Advisory(
                check="A4",
                message=(
                    "The case has no secrets at all, so nobody has a motive and "
                    "there is nothing to conceal under questioning"
                ),
            )
        ]

    suspects = [c.id for c in mystery.characters if c.id != mystery.victim]
    if not suspects:
        return []

    invested = {
        secret.holder
        for secret in mystery.secrets
        if secret.about == mystery.victim and secret.holder in suspects
    }
    share = len(invested) / len(suspects)

    if share < MIN_SUSPECTS_WITH_A_STAKE_IN_THE_VICTIM:
        return [
            Advisory(
                check="A4",
                message=(
                    f"Only {len(invested)} of {len(suspects)} suspects conceal "
                    f"anything to do with the victim. The rest are unrelated "
                    f"subplots, so the killer is the only person with a motive"
                ),
            )
        ]
    return []


def motive_is_gated(mystery: Mystery) -> list[Advisory]:
    """A5: is the killer's motive reachable straight away?

    In both hand-built prototypes the killer only became a suspect after some
    unrelated-looking secret had been cracked. That gating is what makes the
    obvious suspect the wrong answer.
    """
    if mystery.killer is None:
        return [
            Advisory(
                check="A5",
                message="No killer is named, so the case has no solution to check",
            )
        ]
    if not mystery.secrets:
        return []

    # A killer typically holds two secrets about the victim: the background that
    # made them vulnerable, and the reason they killed. Taking the first match
    # flagged the background and reported a gated motive as ungated on two real
    # cases. Prefer the one explicitly marked, fall back to any gated one.
    candidates = [
        s for s in mystery.secrets if s.holder == mystery.killer and s.about == mystery.victim
    ]
    motive = next(
        (s for s in candidates if s.is_motive),
        next((s for s in candidates if s.revealed_by), candidates[0] if candidates else None),
    )

    if motive is None:
        return [
            Advisory(
                check="A5",
                message=(
                    "The killer conceals nothing about the victim, so the case has "
                    "no motive to discover"
                ),
            )
        ]

    if motive.revealed_by is None:
        return [
            Advisory(
                check="A5",
                message=(
                    f"The killer's motive ({motive.id!r}) is not gated behind any "
                    f"other secret, so it is visible from the first round of "
                    f"questions and the obvious suspect is the answer"
                ),
            )
        ]
    return []


def killer_lies_about_where_they_were(mystery: Mystery) -> list[Advisory]:
    """A6: does the killer have a false story at all?

    Without one there is nothing to catch them in, and the contradiction tracker,
    which is both the gameplay and the evaluation layer, has nothing to track.
    """
    if mystery.killer is None:
        return []

    claim = mystery.false_claim
    if claim is None:
        return [
            Advisory(
                check="A6",
                message=(
                    "Nobody makes a false claim about where they were. The killer "
                    "has nothing to lie about and there is nothing to catch"
                ),
            )
        ]

    truth = mystery.placements.get(claim.character, {}).get(claim.slot)
    if truth == claim.place:
        return [
            Advisory(
                check="A6",
                message=(
                    f"{claim.character!r} claims to have been in {claim.place!r} at "
                    f"{claim.slot!r}, which is exactly where they were. The lie is "
                    f"not a lie"
                ),
            )
        ]
    return []


def alibi_is_breakable_but_not_trivially(mystery: Mystery) -> list[Advisory]:
    """A7: the rule this whole project was specified around.

    From the original brief: the killer's alibi must be falsifiable from combined
    testimony but not from any single one. Until knowledge derivation existed
    this was unwritable, and A2 was standing in for it by counting people without
    alibis, which is a much cruder thing.

    Two failure modes, opposite to each other. Too few contradictors and the lie
    is unbreakable, so the case is unsolvable. One unimpeachable contradictor and
    the player asks that person a single question and it is over.
    """
    if mystery.false_claim is None:
        return []

    analysis = analyse_alibi(mystery, derive(mystery))
    if analysis.claim_holds:
        return []

    advisories = []

    if not analysis.breakable:
        advisories.append(
            Advisory(
                check="A7",
                message=(
                    f"Only {len(analysis.contradictors)} character(s) could "
                    f"contradict the killer's story. An alibi that cannot be broken "
                    f"by combining testimony makes the case unsolvable"
                ),
            )
        )

    if analysis.settled_by_one:
        advisories.append(
            Advisory(
                check="A7",
                message=(
                    f"{', '.join(analysis.credible)} can contradict the killer and "
                    f"has nothing of their own to hide, so one question to them "
                    f"settles the case. Every witness against the killer should be "
                    f"compromised by a secret of their own"
                ),
            )
        )

    return advisories


ADVISORIES = [
    wandering,
    alibi_breadth,
    everyone_conceals_something,
    everyone_has_an_unwitnessed_moment,
    victim_is_a_hub,
    motive_is_gated,
    killer_lies_about_where_they_were,
    alibi_is_breakable_but_not_trivially,
]


def critique(mystery: Mystery) -> list[Advisory]:
    return [advisory for check in ADVISORIES for advisory in check(mystery)]
