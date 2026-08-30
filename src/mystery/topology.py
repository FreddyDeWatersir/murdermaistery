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


THE_FRAME = """\
The killer's protection is that **somebody else looks guilty**, and the killer \
themselves does not lie about anything.

Give the killer no entry in `false_claims`. They do not need one. Their account \
of the evening is entirely true, which is why pressing them produces nothing and \
why the player keeps going back to somebody else.

That somebody else is the framed suspect, and the case against them should be \
better than the case against the killer. At least two pieces of evidence point \
at them: an object of theirs in the wrong room, a debt, a threat somebody \
overheard, an hour they cannot account for. Each one is **true and innocent**, \
and each has an explanation nobody has asked them for, because the explanation \
is humiliating or involves somebody they are protecting.

The killer arranged some of it and got lucky with the rest. Do not make them a \
master planner; a person who moved one thing and let the rest happen is more \
frightening and much easier to believe.

The player solves this by noticing the case is **too complete**. Real guilt is \
ragged. Give the framed suspect one explanation that, once heard, retroactively \
makes every other piece of evidence look thin.\
"""


THE_FINDER = """\
The person who found the body **is the one who put it there**, and their \
protection is the story of finding it.

Set `discovery.finder` to the killer. Everyone in the building has accepted \
their account of the discovery, because nobody questions the person who raised \
the alarm, and the player will not either until something forces them to.

The discovery story must be **wrong in one checkable place**. They say they came \
in at the end of the evening and found him; somebody can put them in that room \
earlier, or the state of the room contradicts the order they describe, or a \
thing they say they did not touch has their handling all over it. One seam, not \
three: a discovery story with three holes was never believed by anybody.

Everything else about the evening is honest, including the killer's account of \
where they were the rest of the time. The lie is a single event, told once, at \
the moment it was most useful.

The pleasure of this shape is that the one piece of testimony the game hands the \
player as common knowledge, before they have asked anybody anything, is the lie.\
"""


THE_CONSPIRACY = """\
**All of them are lying about the same thing, and it is not the murder.**

Every suspect appears in `false_claims` naming the same room at the same hour, \
and none of them was there. What they are covering is real, shared, serious, and \
has nothing to do with the death: money they all took, a fire they all caused, a \
patient or a client or a student they all failed and agreed never to discuss, an \
affair the whole department protected. Put its id in `covers` for every one of \
them, and make that secret a real one with a real holder.

**The way in is the seam.** Five people who agreed a story do not agree on the \
details. At least two of them must place a third person differently *within* the \
shared account, so the story cracks under comparison rather than under pressure. \
The player's notebook already catches two people disagreeing about where somebody \
stood; that is the crack, and you are writing it deliberately.

**And each of them still has their own secret**, unconnected to the conspiracy \
and not gated behind it. That is what gives the player a first foothold: you pull \
a private thread, it gives you leverage on one person, and that person is the one \
who lets the shared story go.

The shape of the evening is: the player breaks the conspiracy, feels they have \
solved it, and finds they have solved the wrong crime. The killer is inside the \
group lie, using it as somewhere to stand, and their own guilt has to be found \
all over again from a cast who have now stopped lying and still cannot be \
trusted.\
"""


THE_WRONG_HOUR = """\
**Nobody lies about where they were. The lie is when it happened.**

Everyone in the building believes the death happened at a particular hour, and \
they are wrong by one slot. Write that belief into `discovery.summary` as \
something the finder saw and reasonably concluded: he was alive at the toast and \
cold when I found him; the machine was still running and it stops after twenty \
minutes; his glass was full and he never left a full glass.

The killer's alibi **for the believed hour is completely true**. Witnesses, \
corroboration, the lot. Give them no entry in `false_claims`. Pressing them about \
that hour is time thrown away, and it should feel like it. For the hour the \
murder actually happened they have nothing, and nobody has thought to ask.

**Somebody must be able to correct the time**, and it must be reachable: a person \
who heard something at the earlier hour and did not understand what it was, a \
machine log, a phone call, a delivery, a light that was already off. Make it a \
secret with `evidence` so the player can put it in front of people, because the \
whole second half of this case is going back to everyone with the real hour and \
watching what changes.

This is the only shape where nobody is lying to the player. Their opponent is an \
inference everybody made in good faith, including them.\
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



# --- the frame ---------------------------------------------------------------


def the_killer_tells_no_lie(mystery: Mystery) -> list[Advisory]:
    """F1: in a frame, the killer's account is true.

    The whole shape is that pressing the killer produces nothing, because there
    is nothing there. A killer who also lies about where they stood is the plain
    shape with extra scenery, and A6 will have cheerfully approved it, because
    A6 wants the killer to lie.
    """
    if mystery.killer and mystery.lie_by(mystery.killer):
        return [
            Advisory(
                check="F1",
                message=(
                    f"{mystery.killer!r} tells a false claim, and in a frame they "
                    f"should not. Their protection is that somebody else looks "
                    f"guilty, not that their own story is wrong. As written this "
                    f"is the plain shape wearing a frame"
                ),
            )
        ]
    return []


def somebody_else_is_carrying_it(mystery: Mystery) -> list[Advisory]:
    """F2: there has to be a framed suspect, and they need a way out.

    Two people lying is not a frame. A frame is somebody the evidence points at
    who can be cleared, and clearing them is the act the shape exists for. The
    proxy for "the evidence points at them" is that they hold or are named by
    more than one secret; the proxy for "can be cleared" is that those secrets
    are reachable.
    """
    if not mystery.killer:
        return []

    weight: dict[str, int] = {}
    for secret in mystery.secrets:
        if secret.holder != mystery.killer:
            weight[secret.holder] = weight.get(secret.holder, 0) + 1

    carrying = [who for who, n in weight.items() if n >= 2]
    if not carrying:
        return [
            Advisory(
                check="F2",
                message=(
                    "Nobody is carrying enough to be framed. One suspect other "
                    "than the killer needs at least two things pointing at them, "
                    "each true, each innocent, each with an explanation nobody "
                    "has asked for"
                ),
            )
        ]
    return []


# --- the finder --------------------------------------------------------------


def the_finder_is_the_killer(mystery: Mystery) -> list[Advisory]:
    """W1: the shape is one sentence and this is it."""
    if mystery.discovery is None:
        return [
            Advisory(
                check="W1",
                message=(
                    "There is no discovery, so there is no finding story, so there "
                    "is nothing for this shape to be about"
                ),
            )
        ]
    if mystery.discovery.finder != mystery.killer:
        return [
            Advisory(
                check="W1",
                message=(
                    f"The body was found by {mystery.discovery.finder!r} and the "
                    f"killer is {mystery.killer!r}. In this shape they are the "
                    f"same person: the protection *is* the finding story"
                ),
            )
        ]
    return []


def the_finding_story_has_a_seam(mystery: Mystery) -> list[Advisory]:
    """W2: somebody has to be able to contradict the discovery.

    The player is handed the discovery as common knowledge before asking anybody
    anything. If nothing in the case can dispute it, the one lie in the evening
    is also the one thing the game has told them is true.
    """
    if mystery.discovery is None or mystery.killer is None:
        return []

    scene = mystery.murder_scene
    if scene is None or not scene.is_bound:
        return []

    witnesses = [
        c.id
        for c in mystery.characters
        if c.id not in (mystery.killer, mystery.victim)
        and mystery.placements.get(c.id, {}).get(scene.slot) == scene.place
    ]
    nearby = [
        c.id
        for c in mystery.characters
        if c.id not in (mystery.killer, mystery.victim)
        and mystery.placements.get(c.id, {}).get(scene.slot)
        in {p.id for p in mystery.places if scene.place in p.adjacent}
    ]
    if not witnesses and not nearby:
        return [
            Advisory(
                check="W2",
                message=(
                    f"Nobody was in or next door to {scene.place!r} when it "
                    f"happened, so nothing can contradict the finding story and "
                    f"the one lie in this case cannot be caught. Put somebody "
                    f"within earshot"
                ),
            )
        ]
    return []


# --- the conspiracy ----------------------------------------------------------


def they_are_all_covering_one_thing(mystery: Mystery) -> list[Advisory]:
    """C1: the same secret, or it is not a conspiracy.

    Three people lying about three different things is an ordinary case and the
    general advisories already like it. The shape is that the lie is shared.
    """
    covers = [claim.covers for claim in mystery.false_claims if claim.covers]
    liars = len(mystery.false_claims)

    if liars < 3:
        return [
            Advisory(
                check="C1",
                message=(
                    f"Only {liars} people lie. A conspiracy that two people are "
                    f"in is a secret; this shape wants the room"
                ),
            )
        ]
    if len(set(covers)) > 1:
        return [
            Advisory(
                check="C1",
                message=(
                    f"The liars cover {len(set(covers))} different things: "
                    f"{sorted(set(covers))}. In this shape they are all covering "
                    f"the same one, and that is what makes the group lie a group"
                ),
            )
        ]
    return []


def the_shared_lie_is_not_the_murder(mystery: Mystery) -> list[Advisory]:
    """C2: break the conspiracy and you have solved the wrong crime.

    If the thing they are all covering is the motive, then cracking the group
    lie ends the case, and the whole point of this shape is that it does not.
    """
    covers = {claim.covers for claim in mystery.false_claims if claim.covers}
    motive = next((s for s in mystery.secrets if s.is_motive), None)

    if motive and motive.id in covers:
        return [
            Advisory(
                check="C2",
                message=(
                    f"The shared lie covers {motive.id!r}, which is the motive. "
                    f"Then breaking the conspiracy solves the murder, and this "
                    f"shape exists so that it does not: they are covering "
                    f"something real that has nothing to do with the death"
                ),
            )
        ]
    return []


def somebody_has_a_thread_of_their_own(mystery: Mystery) -> list[Advisory]:
    """C3: the first foothold.

    With the whole cast inside one lie there is nobody outside it to tell you
    about it, which is the obvious hole in this shape. The answer is that the
    conspiracy is not the only thing any of them is hiding: each still has a
    private secret, ungated, and pulling one of those is what gives the player
    leverage on somebody who will then let the shared story go.
    """
    covers = {claim.covers for claim in mystery.false_claims if claim.covers}
    private = [
        s
        for s in mystery.secrets
        if s.id not in covers and not s.revealed_by and not s.is_motive
    ]

    if len(private) < 2:
        return [
            Advisory(
                check="C3",
                message=(
                    "Almost everything in this case is the conspiracy or behind "
                    "it, so there is no way in: nobody outside the group lie can "
                    "tell the player about the group lie. Give at least two of "
                    "them a private secret of their own that opens cold"
                ),
            )
        ]
    return []


# --- the wrong hour ----------------------------------------------------------


def nobody_lies_about_the_hour(mystery: Mystery) -> list[Advisory]:
    """H1: the killer's account is true, and that is the trap.

    This shape and the frame are cousins: in both the killer is honest. The
    difference is what the player is fighting. Here it is not another suspect,
    it is an inference the whole house made in good faith.
    """
    if mystery.killer and mystery.lie_by(mystery.killer):
        return [
            Advisory(
                check="H1",
                message=(
                    f"{mystery.killer!r} lies about where they were. In this "
                    f"shape they do not have to: their alibi for the hour "
                    f"everybody believes is true, and the murder was an hour "
                    f"earlier. A lie here collapses it into the plain shape"
                ),
            )
        ]
    return []


def the_real_hour_can_be_established(mystery: Mystery) -> list[Advisory]:
    """H2: something has to correct the time, and it has to be producible.

    Otherwise the player is asked to doubt a time with nothing to doubt it
    with, which is not a deduction, it is a guess. `evidence` is required
    because the second half of this case is carrying the correction back to
    everybody and watching what changes.
    """
    if not mystery.secrets:
        return []

    producible = [s for s in mystery.secrets if s.evidence]
    if not producible:
        return [
            Advisory(
                check="H2",
                message=(
                    "No secret in this case carries an object. The correction to "
                    "the time of death has to be a thing the player can put in "
                    "front of people, because that is the whole second half of "
                    "this shape"
                ),
            )
        ]
    return []


def the_killer_is_free_at_the_believed_hour(mystery: Mystery) -> list[Advisory]:
    """H3: their alibi for the wrong hour must be real and witnessed.

    The discriminator against the plain shape. If the killer is alone at the
    hour everybody suspects, the player suspects them immediately, and the case
    is not about time at all.
    """
    scene = mystery.murder_scene
    if scene is None or not scene.is_bound or not mystery.killer:
        return []

    order = sorted(mystery.slots, key=lambda s: s.index)
    at = {slot.id: i for i, slot in enumerate(order)}
    when = at.get(scene.slot)
    if when is None or when + 1 >= len(order):
        return [
            Advisory(
                check="H3",
                message=(
                    "The murder is in the last slot, so there is no later hour "
                    "for the house to believe in. This shape needs the believed "
                    "hour to come after the real one"
                ),
            )
        ]

    believed = order[when + 1].id
    where = mystery.placements.get(mystery.killer, {}).get(believed)
    company = [
        c.id
        for c in mystery.characters
        if c.id not in (mystery.killer, mystery.victim)
        and mystery.placements.get(c.id, {}).get(believed) == where
    ]
    if not company:
        return [
            Advisory(
                check="H3",
                message=(
                    f"{mystery.killer!r} is alone at {believed!r}, the hour the "
                    f"house believes in. Then they are the obvious suspect from "
                    f"the first question and nobody has to think about time. "
                    f"Put witnesses with them"
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
        Topology(
            id="the_frame",
            name="The case that is too complete",
            blurb="the killer never lies, and somebody else looks guilty",
            brief=THE_FRAME,
            checks=[the_killer_tells_no_lie, somebody_else_is_carrying_it],
        ),
        Topology(
            id="the_finder",
            name="The one who raised the alarm",
            blurb="whoever found the body put it there",
            brief=THE_FINDER,
            checks=[the_finder_is_the_killer, the_finding_story_has_a_seam],
        ),
        Topology(
            id="the_conspiracy",
            name="The wrong crime, solved",
            blurb="all of them lie about the same thing, and it is not the murder",
            brief=THE_CONSPIRACY,
            checks=[
                they_are_all_covering_one_thing,
                the_shared_lie_is_not_the_murder,
                somebody_has_a_thread_of_their_own,
            ],
        ),
        Topology(
            id="the_wrong_hour",
            name="The lie that is a clock",
            blurb="nobody lies about where; the house is wrong about when",
            brief=THE_WRONG_HOUR,
            checks=[
                nobody_lies_about_the_hour,
                the_real_hour_can_be_established,
                the_killer_is_free_at_the_believed_hour,
            ],
        ),
    ]
}

DEFAULT = "the_lie"


def drawn(seed: int) -> str:
    """Which shape this seed gets (D-103).

    From the seed rather than from a fresh coin, so `--seed 483102` still
    returns the case it returned before: the shape is part of what a seed
    means, exactly like the casting bits. Sorted, so the mapping does not
    silently change the next time a shape is added to the middle of the list.
    """
    return sorted(LIBRARY)[seed % len(LIBRARY)]


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
