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
    murder = mystery.murder_scene
    if murder is None or not murder.is_bound:
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


def everyone_is_load_bearing(mystery: Mystery) -> list[Advisory]:
    """A9: suspects the case would not miss.

    The complaint after the second playtest was that some characters were
    useless. A3 and A8 were already passing them, because they held a secret and
    had a private moment, and were still decoration: nothing in the case ran
    *through* them.

    A character earns their place by being a source. They can break the killer's
    alibi, they hold the secret that gates another secret, somebody else's secret
    is known to them, or the motive is theirs. In the hand-built prototypes every
    single character was at least two of those, which is why every conversation
    went somewhere.
    """
    if mystery.killer is None or not mystery.secrets:
        return []

    useful: set[str] = {mystery.killer}
    useful |= set(analyse_alibi(mystery, derive(mystery)).contradictors)

    gates = {s.revealed_by for s in mystery.secrets if s.revealed_by}
    for secret in mystery.secrets:
        if secret.id in gates or secret.is_motive:
            useful.add(secret.holder)
        useful |= set(secret.known_by)

    return [
        Advisory(
            check="A9",
            message=(
                f"{character.name} is not a source of anything. They cannot break "
                f"the killer's story, they gate nobody's secret, and nobody's secret "
                f"reaches through them. Remove them or give them a thread"
            ),
        )
        for character in mystery.characters
        if character.id not in useful and character.id != mystery.victim
    ]


# How many people besides the killer should lie about where they were. With
# nobody else lying, "who lied" and "who did it" are one question and the
# timeline answers it alone, which is the flaw the second playtest found. Two
# innocent liars means the timeline hands over a shortlist and the secrets have
# to do the rest. More than three and every conversation is a retraction.
INNOCENT_LIARS = 2


def the_killer_is_not_the_only_liar(mystery: Mystery) -> list[Advisory]:
    """A10: does cracking the timeline crack the case?

    This is the structural fix for the complaint that the game ends the moment
    you find out who lied about where they were (D-063). It is a count, and a
    crude one, but the property it stands for is the whole replay value of a
    case: the timeline should narrow the field, not name the answer.
    """
    if mystery.killer is None:
        return []

    innocents = [c for c in mystery.false_claims if c.character != mystery.killer]

    if len(innocents) < INNOCENT_LIARS:
        return [
            Advisory(
                check="A10",
                message=(
                    f"{len(innocents)} innocent people lie about where they were, "
                    f"wanted at least {INNOCENT_LIARS}. With this few, working out "
                    f"who lied is the same as working out who killed him, and every "
                    f"secret in the case is decoration"
                ),
            )
        ]
    return []


def every_lie_has_a_way_out(mystery: Mystery) -> list[Advisory]:
    """A11: can the player resolve an innocent lie, or only detect it?

    A lie that surfaces and never resolves is not a red herring, it is a dead
    end wearing one. The player catches somebody out, presses, gets nothing, and
    learns that pressing does not pay, which is the opposite of what the
    mechanic is for.

    Two exits count. Either the secret it covers is known to somebody else, so
    the player can hear it from a third party, or the liar has a condition under
    which they will admit it themselves. Neither one and the lie is sealed.
    """
    if not mystery.false_claims:
        return []

    secrets = {secret.id: secret for secret in mystery.secrets}
    advisories = []

    for claim in mystery.false_claims:
        if claim.character == mystery.killer:
            continue

        secret = secrets.get(claim.covers)

        if secret is None:
            advisories.append(
                Advisory(
                    check="A11",
                    message=(
                        f"{claim.character!r} lies about where they were and no secret "
                        f"says why. A lie with no reason behind it is noise: the player "
                        f"catches them and finds nothing underneath"
                    ),
                )
            )
            continue

        if not secret.known_by and not claim.admits_when:
            advisories.append(
                Advisory(
                    check="A11",
                    message=(
                        f"{claim.character!r} lies to cover {secret.id!r}, which nobody "
                        f"else knows and which they have no condition for admitting. "
                        f"The player can catch the lie and can never resolve it"
                    ),
                )
            )

    return advisories


def position_alone_does_not_convict(mystery: Mystery) -> list[Advisory]:
    """A12: is there still a mechanical shortcut to the killer?

    The subtle way this whole idea collapses back into one move. Innocent liars
    break by *presence*: somebody saw them where they really were, so their
    story resolves and they are cleared. The killer breaks by *absence*: they
    were alone with the victim and nobody can place them anywhere. So a player
    who notices that asymmetry stops solving the case and starts asking "which
    liar can nobody vouch for", and the secrets go back to being scenery.

    The fix is that at least one innocent must also have been unwitnessed when
    they lied, so the positional test leaves two candidates and the motive has
    to break the tie.
    """
    if mystery.killer is None or not mystery.false_claims:
        return []

    knowledge = derive(mystery)

    def vouched_for(claim) -> bool:
        return any(
            knowledge[c.id].saw(claim.character, claim.slot)
            for c in mystery.characters
            if c.id not in (claim.character, mystery.victim)
        )

    unvouched = [c.character for c in mystery.false_claims if not vouched_for(c)]

    if unvouched == [mystery.killer]:
        return [
            Advisory(
                check="A12",
                message=(
                    "The killer is the only liar nobody can place. A player who asks "
                    "'which of the liars has no witness' is handed the answer without "
                    "touching a motive. At least one innocent should have been alone "
                    "when they lied about where they were"
                ),
            )
        ]
    return []


def the_motive_can_be_found(mystery: Mystery) -> list[Advisory]:
    """A13: can the player ever learn *why*?

    The killer never gives up their own motive (D-066), so the only way it
    reaches the player is somebody else saying it. If nobody else knows, the
    reason for the murder exists in the ground truth and nowhere a player can
    reach, and the best ending in the game is unreachable by design.
    """
    if mystery.killer is None:
        return []

    motive = next(
        (s for s in mystery.secrets if s.holder == mystery.killer and s.is_motive), None
    )
    if motive is None or motive.known_by:
        return []

    return [
        Advisory(
            check="A13",
            message=(
                f"Nobody but the killer knows {motive.id!r}, which is why they did it. "
                f"They will never say it themselves, so the player cannot find the "
                f"motive at all. Somebody has to half know it"
            ),
        )
    ]


def the_cast_is_not_all_one_kind(mystery: Mystery) -> list[Advisory]:
    """A14: is this five of the same person with different jobs?

    Only the countable half of a real problem. Left to itself the generator cast
    men as the killer and the victim every time, and the cast around them
    followed (D-074). Who kills whom is decided from the seed now, because it is
    a property of the *sequence* of cases and no check on one case can see it.
    What one case can be asked is whether anybody in it is anything other than
    the default.
    """
    stated = [c.gender.strip().lower() for c in mystery.characters if c.gender.strip()]
    if len(stated) < len(mystery.characters):
        return [
            Advisory(
                check="A14",
                message=(
                    f"{len(mystery.characters) - len(stated)} of the cast have no "
                    f"stated gender, so their drawn portrait is a guess made from "
                    f"prose"
                ),
            )
        ]

    women = sum(1 for g in stated if g.startswith("w"))
    if women < 2 or len(stated) - women < 2:
        return [
            Advisory(
                check="A14",
                message=(
                    f"{women} women and {len(stated) - women} men. A cast that is "
                    f"nearly all one thing reads as the same person five times, and "
                    f"the second case will read as the first"
                ),
            )
        ]
    return []


# Five suspects, and how many of them a reader would put on the list. Three
# means the player is choosing between real candidates; one means they are
# confirming the only name available (D-106).
MIN_SUSPECTS_WHO_LOOK_GUILTY = 3


def enough_of_them_look_guilty(mystery: Mystery) -> list[Advisory]:
    """A16: more than one person has to look like they did it.

    Guards: the language model, and a gap the existing checks left open. A4 asks
    whether the victim is a hub, and a case can satisfy it with grievances: a
    man who lost money, a woman who wanted a word. Neither reads as a reason to
    kill. A real playtest came back "it was fun and smooth but only one person
    had a legit motive", and every advisory had passed.
    """
    if not mystery.secrets or not mystery.killer:
        return []

    suspects = {c.id for c in mystery.characters if c.id != mystery.victim}
    guilty = {s.holder for s in mystery.secrets if s.damning} & suspects

    if not any(s.damning for s in mystery.secrets):
        return [
            Advisory(
                check="A16",
                message=(
                    "No secret in this case is marked `damning`, so nothing says "
                    "which of these people a reader would suspect. Cases written "
                    "before D-106 look like this"
                ),
            )
        ]

    if len(guilty) < MIN_SUSPECTS_WHO_LOOK_GUILTY:
        return [
            Advisory(
                check="A16",
                message=(
                    f"Only {len(guilty)} of {len(suspects)} suspects hold anything "
                    f"damning: {sorted(guilty)}. The player is not choosing between "
                    f"candidates, they are confirming the only name available. At "
                    f"least {MIN_SUSPECTS_WHO_LOOK_GUILTY} of them need something "
                    f"that would put them on the list on its own"
                ),
            )
        ]

    if mystery.killer not in guilty:
        return [
            Advisory(
                check="A16",
                message=(
                    f"{mystery.killer!r} killed him and holds nothing damning, so "
                    f"the true answer is the one name the evidence never points at"
                ),
            )
        ]

    return []


# A case is layered when a fair share of it is behind something else, and when
# at least one thing is two pulls deep. Both numbers are invented and both are
# now at least visible (D-108).
MIN_SHARE_GATED = 0.4
MIN_DEPTH = 2


def _depth(mystery: Mystery) -> int:
    """The longest chain of gates: how many things must be pulled before the last."""
    by = {secret.id: secret for secret in mystery.secrets}

    def behind(secret_id: str, walked: tuple[str, ...] = ()) -> int:
        secret = by.get(secret_id)
        if secret is None or not secret.revealed_by or secret.revealed_by in walked:
            return 0
        return 1 + behind(secret.revealed_by, (*walked, secret_id))

    return max((behind(s.id) for s in mystery.secrets), default=0)


def the_case_has_a_second_half(mystery: Mystery) -> list[Advisory]:
    """A17: not everything can be available in the first ten questions.

    Guards: the language model, and an advisory that taught it the wrong lesson.
    A5 requires the killer's motive to be gated behind another secret. Five real
    cases in a row came back with **exactly one gate and a depth of one**: six or
    seven secrets available cold and the motive behind one of them. A rule that
    asks for a minimum gets the minimum.

    A playtest of one of those five: a hundred and one questions, everything the
    killer had surrendered in the first nine, and twenty-eight further questions
    that produced nothing at all. Reported back as too easy and not satisfying,
    which is what a case with no second half feels like from the inside.
    """
    secrets = mystery.secrets
    if len(secrets) < 4:
        return []

    gated = [s for s in secrets if s.revealed_by]
    found: list[Advisory] = []
    share = len(gated) / len(secrets)

    if share < MIN_SHARE_GATED:
        found.append(
            Advisory(
                check="A17",
                message=(
                    f"{len(gated)} of {len(secrets)} secrets are behind anything, so "
                    f"{len(secrets) - len(gated)} of them are available cold. The "
                    f"player empties this case in ten questions and the rest of the "
                    f"evening has nothing in it. At least "
                    f"{int(MIN_SHARE_GATED * 100)}% should need something else first"
                ),
            )
        )

    if _depth(mystery) < MIN_DEPTH:
        found.append(
            Advisory(
                check="A17",
                message=(
                    f"No secret is more than {_depth(mystery)} pull deep. Every gate "
                    f"opens straight off something anybody can get in one question, "
                    f"so there is a surface and an answer and nothing between them. "
                    f"One chain at least {MIN_DEPTH} deep is what makes a middle"
                ),
            )
        )

    return found


def they_could_each_have_done_it(mystery: Mystery) -> list[Advisory]:
    """A18: three people the player could build a whole theory around.

    A16 asks how many of them have a reason. That is half a theory. The other
    half is opportunity, and a suspect with a motive and a room full of
    witnesses is not a suspect, they are scenery. What makes an evening
    difficult is two or three *complete* explanations standing up at once, each
    of which accounts for the killing, and the work being to knock them down.

    Guards: the language model, and the gap between "looks guilty" and "could
    have done it".
    """
    scene = mystery.murder_scene
    if not mystery.secrets or scene is None or not scene.is_bound:
        return []
    if not any(s.damning for s in mystery.secrets):
        return []  # A16 already says so, once

    suspects = {c.id for c in mystery.characters if c.id != mystery.victim}
    reasons = {s.holder for s in mystery.secrets if s.damning} & suspects

    together: dict[str, list[str]] = {}
    for who in suspects:
        where = mystery.placements.get(who, {}).get(scene.slot)
        together.setdefault(where or "?", []).append(who)

    # Alone, or with one other person who is equally unable to prove it.
    loose = {who for room in together.values() if len(room) <= 2 for who in room}
    theories = reasons & loose

    if len(theories) < MIN_SUSPECTS_WHO_LOOK_GUILTY:
        return [
            Advisory(
                check="A18",
                message=(
                    f"Only {len(theories)} of them have both a reason and the "
                    f"chance: {sorted(theories)}. {sorted(reasons - loose)} had a "
                    f"reason and cannot have done it, which makes them scenery "
                    f"rather than suspects. The player should be able to build "
                    f"{MIN_SUSPECTS_WHO_LOOK_GUILTY} whole theories and have to "
                    f"knock two of them down"
                ),
            )
        ]
    return []


# How much of the case has to point at somebody other than the dead man. A
# wheel is five spokes and no rim (D-109).
MIN_SHARE_ABOUT_EACH_OTHER = 0.3


def the_cast_is_a_web_not_a_wheel(mystery: Mystery) -> list[Advisory]:
    """A19: they must know things about each other, not only about the victim.

    Guards: the language model, and A4, which asks for the victim to be a hub
    and gets a hub with nothing else in the drawing. Measured across five real
    cases: four of them had one secret or none pointing at another suspect, and
    the one a player actually played had **none**. Four pointed at the dead man
    and three pointed at nobody at all.

    That is why the middle of that evening was empty. Every suspect was a spoke:
    question them, take their spoke, move on. Nothing anybody said gave the
    player leverage on anybody else, so there was no route from the first person
    to the third, and the case was over as soon as the spokes were collected.

    What the tradition does instead is entangle the house. The maid is
    protecting the son, the son is covering for the wife, the wife knows about
    the solicitor, and the fifty pages in the middle are the player working
    along that chain.
    """
    suspects = {c.id for c in mystery.characters if c.id != mystery.victim}
    if len(mystery.secrets) < 4 or len(suspects) < 3:
        return []

    between = [
        s for s in mystery.secrets if s.about in suspects and s.about != s.holder
    ]
    found: list[Advisory] = []

    if len(between) / len(mystery.secrets) < MIN_SHARE_ABOUT_EACH_OTHER:
        found.append(
            Advisory(
                check="A19",
                message=(
                    f"{len(between)} of {len(mystery.secrets)} secrets are about "
                    f"another suspect. The rest point at the dead man or at "
                    f"nobody, which makes this a wheel: five spokes and no rim. "
                    f"The player takes one thing from each person and never has a "
                    f"reason to go from one of them to another. At least "
                    f"{int(MIN_SHARE_ABOUT_EACH_OTHER * 100)}% should be about "
                    f"each other"
                ),
            )
        )

    tied = {s.holder for s in between} | {s.about for s in between}
    tied |= {who for s in mystery.secrets for who in s.known_by if who in suspects}
    islands = sorted(suspects - tied)
    if islands:
        found.append(
            Advisory(
                check="A19",
                message=(
                    f"{islands} are connected to nobody: they hold nothing about "
                    f"another suspect, nobody holds anything about them, and they "
                    f"are not in anybody's `known_by`. Whatever the player learns "
                    f"elsewhere, there is no thread that leads to them"
                ),
            )
        )

    return found


def the_building_hangs_together(mystery: Mystery) -> list[Advisory]:
    """A15: every room reachable from every other, and no room with no doors.

    Guards: the language model. A floor plan is easy to write and easy to write
    badly, and the two failures look nothing alike on the page. A room with no
    `adjacent` at all is a room nobody can walk into. A plan that splits into two
    halves is two buildings, and a player reading the map will believe a route
    exists that does not (D-093).

    An advisory rather than a rule, because nothing mechanical breaks: the case
    still plays, the timeline still holds, and only the map lies. A case is not
    worth throwing away over a missing door.
    """
    places = mystery.places
    if len(places) < 2:
        return []

    doors = {place.id: set(place.adjacent) for place in places}
    if all(not neighbours for neighbours in doors.values()):
        return [
            Advisory(
                check="A15",
                message=(
                    "No place lists any `adjacent`, so there is no floor plan and "
                    "the map can only be a list. Cases drafted before D-093 look "
                    "like this"
                ),
            )
        ]

    found: list[Advisory] = []
    for place in places:
        if not doors[place.id]:
            found.append(
                Advisory(
                    check="A15",
                    message=(
                        f"{place.id!r} has no doors. Nobody can get into it and "
                        f"nobody in it can hear anything"
                    ),
                )
            )

    # Walk from the first room and see how far the building goes.
    start = places[0].id
    seen = {start}
    edge = [start]
    while edge:
        here = edge.pop()
        for other in doors.get(here, ()):
            if other not in seen:
                seen.add(other)
                edge.append(other)

    cut_off = sorted({place.id for place in places} - seen)
    if cut_off:
        found.append(
            Advisory(
                check="A15",
                message=(
                    f"The building is in two pieces: {cut_off} cannot be reached "
                    f"from {start!r} through any door. That is two buildings, and "
                    f"a player reading the map will believe in a route that is not "
                    f"there"
                ),
            )
        )

    return found


ADVISORIES = [
    wandering,
    alibi_breadth,
    everyone_conceals_something,
    everyone_has_an_unwitnessed_moment,
    victim_is_a_hub,
    motive_is_gated,
    killer_lies_about_where_they_were,
    alibi_is_breakable_but_not_trivially,
    everyone_is_load_bearing,
    the_killer_is_not_the_only_liar,
    every_lie_has_a_way_out,
    position_alone_does_not_convict,
    the_motive_can_be_found,
    the_cast_is_not_all_one_kind,
    the_building_hangs_together,
    enough_of_them_look_guilty,
    the_case_has_a_second_half,
    they_could_each_have_done_it,
    the_cast_is_a_web_not_a_wheel,
]


def critique(mystery: Mystery) -> list[Advisory]:
    return [advisory for check in ADVISORIES for advisory in check(mystery)]
