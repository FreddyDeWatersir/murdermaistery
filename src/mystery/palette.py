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

# How the words come out, as opposed to what the person does with the question.
#
# Measured across two played cases with different casts, different countries and
# different centuries: 531 and 612 characters per answer, 21.0 and 20.6 words per
# sentence, about two em-dashes per answer in both. That is one person talking in
# twelve costumes, and it is the strongest sameness signal in the product,
# stronger than plot structure, because it is what a player is inside for the
# whole evening (D-127).
#
# `MANNERS` varies behaviour: who deflects, who over-explains. Nothing varied
# register. Everybody was literate, measured and well punctuated. Nobody was
# boring, nobody talked in fragments, nobody was exhausting to listen to.
#
# These are deliberately about **the shape of the sentences**, not about the
# person. A voice here has to sit on any character the manner deck deals: a
# bishop and a bouncer can both talk in short flat sentences.
VOICES = [
    "short flat sentences, rarely more than a dozen words, and no decoration",
    "long winding sentences that arrive somewhere, but not by the direct route",
    "starts sentences and abandons them halfway when a better one occurs",
    "formal and slightly old-fashioned; full clauses, no contractions",
    "very plain, small vocabulary, repeats the same handful of words",
    "talks in questions, half of them not really questions",
    "professional register: the vocabulary of their trade, used on everything",
    "dry, understated, funny in a way that does not announce itself",
    "warm and rambling, with digressions about people not in this house",
    "clipped and impatient; answers in three words when three will do",
    "precise about facts and vague about everything else, in the same breath",
    "hedges constantly: probably, more or less, I think, as far as I know",
    "blunt to the point of rudeness and unbothered by it",
    "nervous overtalking, filling silence with detail nobody asked for",
    "speaks slowly, with pauses you can feel, and means every word",
    "quotes other people constantly, in their voices",
    "sardonic, and the sarcasm is the only place the feeling shows",
    "gentle, apologetic phrasing over completely immovable answers",
]

# What the player was asked to do, as opposed to what turns out to be true.
#
# Topology answers *how is the truth hidden*. This answers *what is this evening
# asking*, which is a layer above it and composes with all seven shapes (D-129).
# Every case so far has asked exactly one question — who killed this person —
# and after four cases the activity is identical whatever the scenery.
#
# The pair is (what you are told, how that can be wrong). The commission is
# stated to the player in the briefing, because being told what you are for is
# not a spoiler; whether it was the right question is the case.
COMMISSIONS = [
    (
        "The household want to know which of them did it, and want it settled "
        "tonight rather than by whoever arrives in the morning",
        "the plain version: nothing about the request misleads anybody",
    ),
    (
        "They have already settled on one name between them, and what is wanted "
        "from you is a confirmation that will hold up in the morning",
        "the name they have settled on is the wrong one, and the reason they all "
        "believe it is somebody's careful work",
    ),
    (
        "A doctor has already called it a fall, or a seizure, or the stairs, and "
        "one person in this house refuses to accept that and sent for you",
        "the doctor is wrong and the one who sent for you is right, though not "
        "for the reason they think",
    ),
    (
        "You did not come about a death at all. You came for a document, a "
        "payment or an object, and the death is standing between you and it",
        "the thing you came for and the death turn out to be the same story, "
        "which nobody will say out loud",
    ),
    (
        "Somebody in this house wrote to you a fortnight ago saying they were "
        "frightened, and would not say of what",
        "the letter was not written by the person who died, and whoever wrote it "
        "is still in the building",
    ),
    (
        "One of them has already confessed, plainly and without being pressed, "
        "and you are here because nobody quite believes it",
        "the confession is false and the confessor knows exactly who they are "
        "covering for",
    ),
    (
        "The insurers, the family or the firm want a version of tonight they can "
        "file, and would rather it were tidy than true",
        "the tidy version and the true one name different people, and you will "
        "have to choose which one to write down",
    ),
    (
        "You were already here on other business when it happened, and are the "
        "only person present whose reason for being here is written down",
        "your own business and the killing turn out to touch, and one of them "
        "knows that before you do",
    ),
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

# The thing that happened before tonight, that most of them were there for, and
# that nobody has mentioned since (D-109). Dealt separately from the intrigues
# because it does a different job: an intrigue binds two people, this binds the
# room. It is the Sciascia move, and the reason for it is structural rather than
# atmospheric: with every secret pointing at the victim the cast is a wheel, the
# player collects five spokes, and the case has no middle. A shared past is what
# makes them entangled with each other rather than only with the dead man.
OLD_BUSINESS = [
    "a death here years ago that was recorded as an accident",
    "money that went missing once, was quietly replaced, and never explained",
    "somebody who left suddenly and whose name is not used any more",
    "a fire, a flood or a collapse, and a decision about who was blamed",
    "a child, now grown, and an agreement about who was told what",
    "a season or a year everyone refers to only by its date",
    "a letter that was written, read by more people than intended, and destroyed",
    "an inspection that was survived by arrangement rather than by merit",
    "somebody's illness or breakdown that was managed and never named",
    "a promise made at a funeral that only half of them have kept",
    "a piece of work signed by the wrong person, and everybody was in the room",
    "an accusation made once, withdrawn under pressure, and true",
]


# Why the player is in the building, and it is dealt for exactly the reason the
# manners are (D-105). Asked to invent somebody with a professional reason and no
# power, and given one worked example, five consecutive cases produced five
# insurance assessors. That is the D-075 failure again: an example is an answer,
# a longer list in the prompt would be a menu with favourites, and the fix that
# already works in this file is to hand over one and never show the rest.
#
# Structural rather than written, like everything else here. "Halfway through an
# unrelated job" belongs to a lighthouse and to a law firm; "the loss adjuster
# from Utrecht" belongs to one case and would be in all of them.
STANDINGS = [
    "halfway through an unrelated professional job here, and now cannot leave",
    "engaged last month by the victim themselves, about something else entirely",
    "acting for one of the guests, not for the house, and everybody knows it",
    "here to inspect, certify or value something, with the paperwork still open",
    "a stranger who works here this week only: a locum, a relief, an agency hire",
    "writing about this place, with permission that nobody has withdrawn yet",
    "family nobody has met, arrived today, with a claim on something",
    "the person who sold or supplied the thing that has become evidence",
    "sent by whoever pays for all this, to find out why it is going wrong",
    "owed money by the house, and here in person about it for the first time",
    "the one who was supposed to be somewhere else tonight and changed plans",
    "an old colleague of the victim, invited for reasons only the victim knew",
]


# Where the house is. Dealt from the seed, and deliberately not derived from the
# setting phrase: four settings in a row that each sounded coastal and northern
# produced four Dutch casts, because the model reads "an old house" or "fog" and
# goes where the phrase points (D-111). The setting says what the occasion is.
# This says where on earth it is happening, and it changes every case.
#
# A region, not a nationality, and never a stereotype: what it buys is the names,
# the food, the weather, the money and the shape of the building. If the setting
# somebody typed names a place outright, that wins and this is ignored.
WHERE = [
    "a Dutch or Flemish town on flat water: brick, wind, bicycles, thin light",
    "the Italian north, in the fog belt between the Po and the hills",
    "coastal Portugal, tile and salt and a long slow decline in the accounts",
    "the Scottish borders or the Northumbrian coast, out of season",
    "inland Andalusia in the last heat of the year",
    "a Bohemian or Moravian town, forest at the edge, everything state-built",
    "the Aegean in the wrong month, a place that empties in September",
    "Quebec or the Maritimes, French and English in the same room",
    "the Japanese countryside, a house that has been in one family too long",
    "the Argentine litoral, Italian surnames and river heat",
    "a Baltic port: Estonian, Latvian or Finnish, and pine everywhere",
    "the Maghreb coast, French-schooled, with the sea on the wrong side",
    "Kerala or the Konkan coast in the last week before the rains",
    "the Anatolian plateau, a long way from any coast at all",
    "an alpine valley on a border, where the surnames come from both sides",
    "the American upper midwest in November, Scandinavian and German by descent",
]


# What has brought them together, and why it has to be tonight. The one input to
# a case that was never dealt: `--setting` defaulted to a fixed string, so every
# case somebody did not name a setting for was a private view at a small art
# gallery, forever (D-115). Paired with WHERE, an occasion here becomes a
# specific evening in a specific country.
#
# Each one has to put a small group under one roof past the point where they can
# leave, and put something at stake in the morning. That is the whole job: the
# stake is what a victim can threaten and what a killer runs out of time about.
OCCASIONS = [
    "the last night of a residency, with the funding decision in the morning",
    "a family gathered to sign the sale of a business none of them agree about",
    "the closing dinner of an inspection that has gone badly for somebody",
    "a wake, on the night before the will is read",
    "a small firm's annual weekend, the year the accounts stopped adding up",
    "the eve of a wedding that half the household is quietly against",
    "a handover: the outgoing and incoming both here, and the books open",
    "the night a long strike is settled, in the building it was about",
    "a reunion of people who were all somewhere else together, twenty years ago",
    "the last service before a place closes for good, staff and owners both",
    "a christening lunch that has run into the evening and not broken up",
    "the night before an auction of everything in the house",
    "a board stranded overnight by weather, with the vote due at nine",
    "the anniversary dinner of the thing nobody mentions",
    "a harvest, a catch or a season's end, with the money being divided",
    "an inheritance being counted, physically, room by room, over one night",
    "the final rehearsal before an opening that several people need to fail",
    "a hospital, hotel or school being handed to new owners at first light",
]


@dataclass(frozen=True)
class Palette:
    manners: list[str]
    voices: list[str]
    motive: str
    intrigues: list[str]
    standing: str = ""
    old_business: str = ""
    where: str = ""

    def brief(self) -> str:
        manners = "\n".join(f"  - {m}" for m in self.manners)
        voices = "\n".join(f"  - {v}" for v in self.voices)
        intrigues = "\n".join(f"  - {i}" for i in self.intrigues)
        return (
            f"MATERIAL FOR THIS CASE\n"
            f"Not a menu to choose from. This is the assignment, and the point of "
            f"it is that the next case gets different material.\n\n"
            f"**Where on earth this house is:** {self.where}. That decides the "
            f"names, the food, the weather, the money and how the building is "
            f"built. Do not write a travel brochure of it and do not make anybody "
            f"a type: it should show mostly in what people are called and what "
            f"they take for granted. **If the setting given below already implies "
            f"a place, that wins and you ignore this line entirely** — and a "
            f"period or a style implies one as surely as a country does. A "
            f"Victorian castle is British, a dacha is Russian, a hacienda is "
            f"Spanish-speaking. Only use the line above when the setting could "
            f"honestly be anywhere.\n\n"
            f"Manners, one per suspect, in any order you like. Write them as these "
            f"people rather than as the phrases below, and let the manner shape "
            f"what they actually say:\n{manners}\n\n"
            f"The killing comes out of this: {self.motive}\n\n"
            f"**What binds them to each other, and not to the dead man:** "
            f"{self.old_business}. Most of this cast was here for it. Nobody has "
            f"raised it since, each of them for a different reason, and it is why "
            f"they know things about each other rather than only about the "
            f"victim.\n\n"
            f"The person asking the questions is {self.standing}. Work out who "
            f"that is in *this* building and write it into `investigator`. It is "
            f"the assignment, not a suggestion, and it is different next time.\n\n"
            f"**And how they each sound**, which is a different question from "
            f"how they behave. Deal these across the cast too, in any order, and "
            f"write it into `voice`. A voice is the shape of the sentences: how "
            f"long, how formal, how finished, how large a vocabulary. It has to "
            f"survive contact with the manner above it, and the two are "
            f"independent — a blunt three-word answerer can be the one who "
            f"answers for everybody else. **Do not give them all the same "
            f"careful literate register.** Somebody here should be tiring to "
            f"listen to:\n{voices}\n\n"
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
        voices=rng.sample(VOICES, min(cast_size, len(VOICES))),
        motive=rng.choice(MOTIVES),
        intrigues=rng.sample(INTRIGUES, 3),
        standing=rng.choice(STANDINGS),
        old_business=rng.choice(OLD_BUSINESS),
        # Drawn on the seed alone, deliberately. The other decks are keyed on the
        # setting so that one seed against four settings gives four hands; this
        # one must vary even when the setting phrase does not, because the
        # setting phrase is exactly what was dragging every cast to one country
        # (D-111).
        where=random.Random(f"where|{seed}").choice(WHERE),
    )


def questions(seed: int) -> int:
    """How long before the police arrive, per case (D-129).

    A single global forty was wrong twice over. It was too tight — two real
    evenings ran to 132 and 106 questions and both were enjoyed — and the cost
    argument leaning on it did not survive being checked: with prompt caching a
    hundred question evening is about fifty four cents, not two euros.

    A cap the player never reaches creates no scarcity, and a cap that always
    bites is just a shorter game. So it is dealt, in a wide band, and said in the
    briefing: most nights there is more time than anybody needs and occasionally
    the cars are much closer than that. The evening having its own clock is a
    property of the case rather than a setting somebody tuned.
    """
    return random.Random(f"clock|{seed}").choice(
        [70, 80, 90, 100, 110, 120, 130, 140, 150, 45, 55]
    )


def commission(seed: int) -> tuple[str, bool, str]:
    """What the player is told they are for, and whether it is true.

    Returns the brief, whether it is sound, and how it is wrong when it is not.
    Roughly two in five are mistaken, which is often enough that the briefing
    cannot be trusted flatly and rare enough that trusting it is not stupid.
    """
    rng = random.Random(f"commission|{seed}")
    brief, wrong = rng.choice(COMMISSIONS)
    sound = rng.random() >= 0.4
    return brief, sound, wrong


def murder_slot(seed: int, slot_count: int = 5) -> int:
    """Which slot the killing happens in, dealt from the seed (D-125).

    Measured across twelve real cases: the murder was in slot four ten times and
    slot five twice. Never earlier. Nothing asked for that; the model writes a
    story and a story builds to its murder, so it lands near the end every time.

    The cost is a rule of thumb that solves the game. The killer lies about the
    slot they killed in, by construction, so "who is lying about the second to
    last hour" walked straight to the killer in ten cases out of twelve. A player
    found it without being told, and said so.

    Dealt uniformly from the second slot onwards. The first is excluded because a
    murder there leaves four fifths of the evening as aftermath, with the room
    sealed by V10, and the case becomes a different game rather than a harder
    one. Everything after that is fair, and **when** it happened stops being
    something the player can assume.
    """
    return random.Random(f"murder|{seed}").randrange(2, slot_count + 1)


def occasion(seed: int) -> str:
    """What is happening tonight, drawn from the seed.

    Used when nobody passed `--setting`. Keyed the same way as `where`, on the
    seed alone, so that the two together are reproducible from the number the
    run prints and nothing else (D-115).
    """
    return random.Random(f"occasion|{seed}").choice(OCCASIONS)
