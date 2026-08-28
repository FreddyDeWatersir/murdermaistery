"""The raw material one case is built from, drawn fresh for every case.

The last round of feedback was that the casts were repeating, and the cause was
embarrassing: the prompt listed four manners as examples and the model copied
them, because that is what examples are for (D-074). The obvious fix is a longer
list, and it is the wrong fix. A model handed forty options picks its three
favourites and picks the same three next time, which is how you get forty
options and five characters.

So variety is not asked for here, it is dealt (D-075). Every generation draws a
handful of manners, one motive family and two or three intrigues from the seed,
and the model is given only those. It never sees the list, so it cannot have a
favourite, and two cases from different seeds are working from different
material before a word is written.

The entries are deliberately **structural rather than written**. "Answers a
slightly different question from the one asked" is a behaviour that can belong
to a bishop or a bouncer. "Nervous young assistant with a stutter" is a
character, and handing over characters is how every case ends up with the same
five people in different coats.
"""

import random
from dataclasses import dataclass

MANNERS = [
    "answers a slightly different question from the one that was asked",
    "over-explains, then stops abruptly on hearing themselves",
    "is helpful about everything that costs them nothing",
    "keeps score, and would rather trade than give",
    "becomes formal and precise exactly when frightened",
    "makes jokes, and the jokes get worse the closer you get",
    "answers for other people, including people who are present",
    "asks what you have already been told before saying anything",
    "apologises constantly and concedes nothing",
    "treats being questioned as an inconvenience to be managed",
    "is truthful in a way designed to leave the wrong impression",
    "hides behind procedure, job description and what is not their place to say",
    "flatters the questioner and watches to see if it works",
    "contradicts small details on purpose, to find out what you know",
    "speaks in the plural: we, the family, the firm, this house",
    "answers quickly, then revises, then revises again",
    "lets silence sit and waits for the questioner to fill it",
    "keeps returning to how fond the dead man was of them",
    "is genuinely trying to help and genuinely mistaken about half of it",
    "gets angry about small things to avoid the large one",
    "talks about the victim in the present tense and does not notice",
    "answers everything with what somebody else told them",
    "is rehearsed, and it shows most when the question is unexpected",
    "goes vague on times and exact on grievances",
    "will say anything to be liked, including things that are not true",
    "treats every question as an accusation and says so",
    "volunteers other people's business freely and their own never",
    "is calm in a way that costs visible effort",
]

MOTIVES = [
    "the victim was about to take away the thing that made them who they are",
    "an old crime was going to be reopened, and the victim held the thread",
    "the victim had decided to tell somebody something true",
    "money that was never theirs, and an audit that could no longer be delayed",
    "a will that was being changed in the morning",
    "a humiliation the victim had already scheduled in front of other people",
    "the victim had started doing to somebody else what they once did to the killer",
    "a child of theirs the victim was about to ruin",
    "the killer had been paying to keep something quiet and could not pay again",
    "the victim was leaving, and taking with them the only proof of the killer's worth",
    "a promise the victim had made publicly and was about to break privately",
    "the killer had already done something irreversible and the victim had found it",
    "the victim knew the killer's qualification, name or history was a fiction",
    "an inheritance the victim was giving away to somebody undeserving",
    "the victim had been quietly destroying the killer's work for a year",
    "the killer was being sent away, and had run out of places to be sent from",
    "the victim held a letter that would end the killer's marriage",
    "a debt the victim had bought up specifically in order to hold it",
    "the victim was about to hand somebody else the thing the killer had earned",
    "the killer's part in an old death the victim had begun asking about again",
]

INTRIGUES = [
    "two people here are pretending not to know each other",
    "somebody is being blackmailed, and not by the victim",
    "an affair that ended badly, which one of the two has not accepted",
    "somebody has been taking small amounts for years and has never been caught",
    "a forged document that will surface next week whatever happens tonight",
    "two people made an agreement months ago and one of them has broken it",
    "somebody is about to be replaced and is the only person who does not know",
    "an old debt is being called in tonight, quietly, in a corner",
    "somebody is covering for their own child and would let anyone hang for it",
    "two people are competing for the same position and both have been promised it",
    "somebody came here tonight specifically to say something and has not managed it",
    "a rumour about one of them is true, and the wrong person is spreading it",
    "somebody has been reading other people's correspondence",
    "two of them were somewhere else together earlier and cannot say where",
    "somebody's reference or recommendation was invented and is about to be checked",
    "a family matter everyone here knows about and nobody will name",
    "somebody has already been paid to behave in a particular way this evening",
    "one of them is leaving the country next week and has told nobody",
    "an accusation was made last year, withdrawn, and never resolved",
    "two of them are related and it is not public",
    "somebody is protecting a person who is not in the building",
    "one of them has been drinking since the afternoon and is managing it well",
    "somebody lost a great deal of money on the victim's advice",
    "a job was given to the wrong person and everybody knows which",
]


@dataclass(frozen=True)
class Palette:
    manners: list[str]
    motive: str
    intrigues: list[str]

    def brief(self) -> str:
        manners = "\n".join(f"  - {m}" for m in self.manners)
        intrigues = "\n".join(f"  - {i}" for i in self.intrigues)
        return (
            f"MATERIAL FOR THIS CASE\n"
            f"Not a menu to choose from. This is the assignment, and the point of "
            f"it is that the next case gets different material.\n\n"
            f"Manners, one per suspect, in any order you like. Write them as these "
            f"people rather than as the phrases below, and let the manner shape "
            f"what they actually say:\n{manners}\n\n"
            f"The killing comes out of this: {self.motive}\n\n"
            f"These threads also run under the evening, between people who did not "
            f"kill anybody. They are what the other suspects are being evasive "
            f"about, and at least one of them should be the thing that gates the "
            f"killer's motive:\n{intrigues}\n"
        )


def draw(seed: int, setting: str, topology: str, cast_size: int = 5) -> Palette:
    """Deal one case's material.

    Keyed on everything that identifies the case rather than the seed alone, so
    that running seed 0 against four different settings does not produce the
    same four hands.
    """
    rng = random.Random(f"{seed}|{setting}|{topology}")
    return Palette(
        manners=rng.sample(MANNERS, min(cast_size, len(MANNERS))),
        motive=rng.choice(MOTIVES),
        intrigues=rng.sample(INTRIGUES, 3),
    )
