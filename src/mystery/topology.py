"""The shapes a case can have, and the checks that come with each.

Every case generated so far has had the same skeleton: the killer lies about
where they were, and the player catches them out. Better prose does not fix
that. The second case is the same puzzle in different clothes, however good the
clothes are, and a player who has solved one has solved the pattern (D-067).

A topology is the *shape of the solution*: what the killer's protection is, and
therefore what the player has to take apart. It carries two things.

`brief` is the paragraph the generator is given, and it is the only part of the
prompt that changes between shapes. Everything else about writing a good case,
the hub victim, the gated motive, the load-bearing cast, holds regardless.

`checks` are advisories that only make sense for this shape. A mutual alibi case
where nobody corroborates anybody is not a mutual alibi case, and no general
advisory would notice, because the general ones do not know what was asked for.
This is the same split as the validator and the critique module: correctness is
universal, quality is contextual (D-031).

Adding a shape means adding an entry here. That is the point of the file.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from mystery.critique import Advisory, critique
from mystery.knowledge import derive
from mystery.models import Mystery
from mystery.solvable import why_not

Check = Callable[[Mystery], list[Advisory]]


@dataclass(frozen=True)
class Topology:
    id: str
    name: str
    blurb: str
    brief: str
    checks: list[Check] = field(default_factory=list)


# --- the shapes -------------------------------------------------------------


THE_LIE = """\
The killer's protection is a **false account of where they were**. They name a \
room they were not in, at the moment of the murder, and the case is taken apart \
by establishing that they were somewhere else.

This is the plainest shape and it lives or dies on the witnesses. The room they \
name must hold at least two other people, all of them concealing something of \
their own, because a witness with nothing to hide is believed at once and ends \
the game in a single question.\
"""


MUTUAL_ALIBI = """\
The killer's protection is **a person, not a room**. Somebody swears they were \
together, and that person is lying.

Write it this way. The killer names a room and an hour, and one other character \
tells the same story: same room, same hour, the two of them together. Both of \
them appear in `false_claims`, both claiming that room at that slot, and neither \
of them was there.

The corroborator is not an accomplice and did not help kill anybody. They lie \
for a reason of their own, and the reason is what the player is actually hunting: \
they are being paid, they are frightened of the killer, they are in love with \
them, they owe them something that would ruin them if it came out, or they were \
themselves somewhere they cannot admit to and the killer's story is a convenient \
place to hide. Put that reason in `covers` as usual.

Two things make this shape work. The corroborator must be **catchable \
independently**: somebody else must be able to place them elsewhere at that \
hour, so the player can break the alibi from their side rather than the killer's. \
And the corroborator must be **worth talking to about something else**, so the \
player finds them for another reason and only then notices the story is too neat.

The pleasure of this one is that the alibi is not weak. It is a person looking \
you in the eye. It breaks when you work out what they are getting.\
"""


FALSE_CONFESSION = """\
Somebody who did not do it **says they did**, and they are convincing.

Set `false_confessor` to that character's id. They are not the killer. Under \
real pressure, late rather than early, they will say they killed the victim, and \
they will have a reason that holds together: they are protecting somebody, they \
believe they caused the death some other way, or they have decided their own life \
is finished anyway and this ends the questioning.

Their confession must be **wrong in a checkable way**. The player can catch it \
because the timeline does not support it: they were somewhere else, seen by \
somebody, at the moment it happened. A confession that cannot be disproved is not \
a twist, it is a coin flip.

The killer still lies about where they were, exactly as in the plain shape, and \
still has a motive gated behind another secret. The confession sits on top: it is \
the wrong ending, offered to the player, gift-wrapped, at the moment they are \
most tired of asking questions.

Give the confessor an impression of the person they are protecting that is warmer \
than they will admit to, because that is the only clue that survives contact with \
a player who wants to believe them.\
"""


# --- the checks that only make sense for one shape --------------------------


def _lies_at(mystery: Mystery, slot: str, place: str) -> list[str]:
    return [
        claim.character
        for claim in mystery.false_claims
        if claim.slot == slot and claim.place == place
    ]


def somebody_vouches_for_the_killer(mystery: Mystery) -> list[Advisory]:
    """T1: a mutual alibi case needs a mutual alibi.

    Without a corroborator this is the plain shape wearing a different name, and
    no general advisory would notice, because none of them knows what was asked
    for.
    """
    lie = mystery.false_claim
    if lie is None:
        return []

    others = [c for c in _lies_at(mystery, lie.slot, lie.place) if c != mystery.killer]

    if not others:
        return [
            Advisory(
                check="T1",
                message=(
                    "Nobody backs the killer's story. This was asked for as a mutual "
                    "alibi and it is an ordinary false claim: there is no person to "
                    "break, only a room"
                ),
            )
        ]
    return []


def the_corroborator_can_be_broken(mystery: Mystery) -> list[Advisory]:
    """T2: the person vouching must be catchable from their own side.

    The whole appeal of this shape is that the player can come at the alibi
    through the corroborator instead of the killer. If nobody can place the
    corroborator anywhere else, the two stories prop each other up forever.
    """
    lie = mystery.false_claim
    if lie is None:
        return []

    knowledge = derive(mystery)
    advisories = []

    for who in _lies_at(mystery, lie.slot, lie.place):
        if who == mystery.killer:
            continue

        seen_elsewhere = any(
            knowledge[c.id].saw(who, lie.slot)
            for c in mystery.characters
            if c.id not in (who, mystery.victim)
        )
        in_the_room = [
            c.id
            for c in mystery.characters
            if c.id not in (who, mystery.victim, mystery.killer)
            and knowledge[c.id].movements.get(lie.slot) == lie.place
        ]

        if not seen_elsewhere and not in_the_room:
            advisories.append(
                Advisory(
                    check="T2",
                    message=(
                        f"{who!r} vouches for the killer and nobody can place them "
                        f"anywhere at that hour. The two stories hold each other up "
                        f"and the player has no way in from either side"
                    ),
                )
            )

    return advisories


def the_confessor_is_not_the_killer(mystery: Mystery) -> list[Advisory]:
    """T3: the obvious failure, and worth a check because it is silent."""
    if mystery.false_confessor is None:
        return [
            Advisory(
                check="T3",
                message=(
                    "Nobody confesses. This was asked for as a false confession and "
                    "there is nothing to disbelieve"
                ),
            )
        ]

    if mystery.false_confessor == mystery.killer:
        return [
            Advisory(
                check="T3",
                message=(
                    "The killer is the one confessing, which is not a false "
                    "confession, it is the end of the game"
                ),
            )
        ]
    return []


def the_confession_can_be_disproved(mystery: Mystery) -> list[Advisory]:
    """T4: somebody must be able to place the confessor away from the murder.

    A confession the player cannot check is not a twist. It is a coin flip
    between two people who both say they did it.
    """
    confessor = mystery.false_confessor
    if confessor is None or confessor == mystery.killer or mystery.killer is None:
        return []

    murder_slot = mystery.murder_slot
    if murder_slot is None:
        return []

    knowledge = derive(mystery)
    witnesses = [
        c.id
        for c in mystery.characters
        if c.id not in (confessor, mystery.victim)
        and knowledge[c.id].saw(confessor, murder_slot)
    ]

    if not witnesses:
        return [
            Advisory(
                check="T4",
                message=(
                    f"Nobody saw {confessor!r} during the murder, so their confession "
                    f"cannot be disproved. The player has to take it or leave it on "
                    f"feel alone"
                ),
            )
        ]
    return []


LIBRARY: dict[str, Topology] = {
    t.id: t
    for t in [
        Topology(
            id="the_lie",
            name="The false account",
            blurb="the killer lies about which room they were in",
            brief=THE_LIE,
        ),
        Topology(
            id="mutual_alibi",
            name="The alibi that is a person",
            blurb="somebody swears they were with the killer, and is lying",
            brief=MUTUAL_ALIBI,
            checks=[somebody_vouches_for_the_killer, the_corroborator_can_be_broken],
        ),
        Topology(
            id="false_confession",
            name="The wrong ending, offered",
            blurb="an innocent confesses, convincingly, and can be disproved",
            brief=FALSE_CONFESSION,
            checks=[the_confessor_is_not_the_killer, the_confession_can_be_disproved],
        ),
    ]
}

DEFAULT = "the_lie"


def get(topology_id: str) -> Topology:
    try:
        return LIBRARY[topology_id]
    except KeyError:
        known = ", ".join(sorted(LIBRARY))
        raise KeyError(f"unknown topology {topology_id!r}. Known: {known}") from None


def catalogue() -> str:
    """One line per shape, for the command line."""
    return "\n".join(f"  {t.id:<18} {t.blurb}" for t in LIBRARY.values())


def assess(mystery: Mystery, topology_id: str = DEFAULT) -> list[Advisory]:
    """Everything worth saying about one case, in one call.

    Three kinds, and the order is deliberate. The general advisories are about
    craft. The topology's own checks are about whether this is the shape that
    was asked for. The solvability findings come last because they are the ones
    that mean the case cannot be played at all (D-068), and last is where a
    person looks.
    """
    return (
        critique(mystery)
        + [a for check in get(topology_id).checks for a in check(mystery)]
        + why_not(mystery)
    )
