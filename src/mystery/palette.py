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
    # What the house has already decided about the death, and what it wants
    # written down. **Not who engaged the player and not why they are in the
    # building**: that is STANDINGS, and for a long time six of these eight also
    # answered it, from a separate random stream, so a case could be told it was
    # hired by a frightened letter-writer and also that it was halfway through
    # an unrelated survey (D-169).
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
        "one person in this house will not accept that",
        "the doctor is wrong and the one who will not accept it is right, though "
        "not for the reason they think",
    ),
    (
        "Nobody has said the word murder out loud yet, and what is wanted is "
        "somebody who will ask the questions that would make saying it necessary",
        "one person in the room has already worked it out and is waiting to see "
        "whether you will",
    ),
    (
        "There is a thing in this house that has to be found before the morning, "
        "and the death has put it out of reach",
        "what was being looked for and the killing turn out to be the same story, "
        "which nobody will say out loud",
    ),
    (
        "One of them has already confessed, plainly and without being pressed, "
        "and nobody quite believes it",
        "the confession is false and the confessor knows exactly who they are "
        "covering for",
    ),
    (
        "The insurers, the family or the firm need a version of tonight they can "
        "file, and would rather it were tidy than true",
        "the tidy version and the true one name different people, and you will "
        "have to choose which one to write down",
    ),
    (
        "Everybody has agreed what happened, in detail, within an hour of the "
        "body being found, and they agree a little too well",
        "the agreed account is somebody's careful work and at least two of them "
        "know it is not what they saw",
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
    # --- everything above is one sentence: the victim was about to take
    # something away or say something out loud, and the killer moved first
    # (D-161). Twenty six real motives, twenty four of them that. The registers
    # below are the ones the engine never once produced, and most of them are
    # about what has already happened rather than what is about to.
    "the killer loved the victim and had just been told it was never returned",
    "the victim was taking somebody the killer loves away, and had every right to",
    "the killer loves somebody else here, and the victim was in the way",
    "an affair between two other people, and whose child it makes the killer's",
    "the victim had been quietly cruel to somebody the killer feels responsible for",
    "the killer believed the victim was about to hurt somebody else, with reasons",
    "a grief the victim caused years ago and mentioned lightly tonight",
    "the victim asked the killer to help them die, was refused, and found somebody else",
    "the killer did help somebody die, and the victim had worked out which death",
    "a conviction the killer holds absolutely, which the victim made unactionable",
    "years of protecting the victim from something that turned out never to have existed",
    "an old humiliation the victim has forgotten and the killer thinks about weekly",
    "the victim is still being thanked for a kindness the killer did",
    "the victim simply has the life the killer was meant to have, and said so lightly",
    "the killer had decided against it weeks ago, and the victim undid the decision",
]

# What the innocent suspects are being evasive about. Three are dealt per case
# and the prompt turns each into a secret with a holder, so this is the deck the
# red herrings are made of (D-170).
#
# Weighed by what it would cost the holder if it came out, the old deck of
# twenty four was 3 heavy, 7 damaging and 14 merely awkward, so it could not
# supply a suspect anybody would seriously write down, and the model had to
# invent motive-grade material for the innocents from nothing every time. Split
# into three tiers, with one heavy one guaranteed in every hand.
#
# A motive is a reason to kill and an intrigue is a reason to lie: they stay
# different jobs. What has to match is the *weight*, so that heavy does not mean
# guilty. An evening where all five have life-ending secrets is melodrama; an
# evening where only the killer does is solved in four questions.

# Would end them. A reader who learned only this would write the name down.
WEIGHTY = [
    "somebody here is the parent of somebody else here, and only one of them knows",
    "two of them have been together for years, and one has a family who do not know",
    "one of them let another take the blame for something, and that person is still paying",
    "somebody has been signing another's name for two years and the bank has noticed",
    "somebody is covering for their own child and would let anyone hang for it",
    "somebody has been taking small amounts for years and has never been caught",
    "one of them ended another's marriage, and that is not public",
    "somebody owes money to a person who does not take a late payment kindly",
    "somebody here was told a year ago they are dying and has told nobody",
    "one of them has been drinking or worse since the spring, and another is covering it",
    "one of them wrote the anonymous letter that ruined another, and it worked",
    "somebody here is frightened of a person in this room and will not say which",
    "a forged document that will surface next week whatever happens tonight",
]

# Would damage them. A career, a marriage, a standing in this house.
DAMAGING = [
    "an affair that ended badly, which one of the two has not accepted",
    "somebody's reference or recommendation was invented and is about to be checked",
    "somebody has been reading other people's correspondence",
    "somebody has already been paid to behave in a particular way this evening",
    "an accusation was made last year, withdrawn, and never resolved",
    "somebody lost a great deal of money on the victim's advice",
    "somebody is being blackmailed, and not by the victim",
    "one of them has left the faith the rest still keep, and the family do not know",
    "somebody cannot forgive another for a thing the other does not remember doing",
    "one of them has been waiting twenty years for a thanks that went to somebody else",
]

# Would embarrass them, or is simply nobody's business. A house needs small
# obstructions as well as large ones, or everybody behaves like a murderer.
AWKWARD = [
    "two people here are pretending not to know each other",
    "two people made an agreement months ago and one of them has broken it",
    "an old debt is being called in tonight, quietly, in a corner",
    "two people are competing for the same position and both have been promised it",
    "somebody came here tonight specifically to say something and has not managed it",
    "a rumour about one of them is true, and the wrong person is spreading it",
    "two of them were somewhere else together earlier and cannot say where",
    "a family matter everyone here knows about and nobody will name",
    "one of them is leaving the country next week and has told nobody",
    "two of them are related and it is not public",
    "somebody is protecting a person who is not in the building",
    "one of them has been drinking since the afternoon and is managing it well",
]

INTRIGUES = WEIGHTY + DAMAGING + AWKWARD

# The thing that happened before tonight, that most of them were there for, and
# that nobody has mentioned since (D-109). Dealt separately from the intrigues
# because it does a different job: an intrigue binds two people, this binds the
# room. It is the Sciascia move, and the reason for it is structural rather than
# atmospheric: with every secret pointing at the victim the cast is a wheel, the
# player collects five spokes, and the case has no middle. A shared past is what
# makes them entangled with each other rather than only with the dead man.
OLD_BUSINESS = [
    # Concealment. Every one of these is somebody's guilt, and for a long time
    # the whole deck was (D-168). Kept to half, because a group that covered
    # something up together is a real and useful thing to be; the fault was that
    # it was the only thing this deck could produce, so every cast came out as
    # colleagues managing an exposure.
    "a death here years ago that was recorded as an accident",
    "money that went missing once, was quietly replaced, and never explained",
    "somebody who left suddenly and whose name is not used any more",
    "a fire, a flood or a collapse, and a decision about who was blamed",
    "a letter that was written, read by more people than intended, and destroyed",
    "somebody's illness or breakdown that was managed and never named",
    "a piece of work signed by the wrong person, and everybody was in the room",
    "an accusation made once, withdrawn under pressure, and true",
    "a child, now grown, and an agreement about who was told what",
    "a promise made at a funeral that only half of them have kept",
    # And things a group can share that are nobody's crime. The prompt asks this
    # deck for "what gives them reasons to know about each other rather than only
    # about the victim", and knowing each other has never required having
    # covered something up together.
    "a child they all helped raise for one year",
    "a relationship between two of them that ended here, and everybody knew",
    "a rescue here, and one of them has never been thanked for it",
    "money one of them gave another, quietly, never repaid and never mentioned",
    "a strike or a refusal they all signed, and what it cost each of them",
    "an illness one of them nursed another through, unmentioned since",
    "a prize or a record, and the single name that went on it",
    "a faith, a language or a trade they all left at the same time",
    "a summer they all lived in the same house",
    "a funeral half of them did not attend, for six different reasons",
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
    # --- Everything above is a transaction (D-162). Fourteen of the eighteen
    # are a night when something changes hands: a vote, a sale, a will, an
    # audit, a handover, a season's money being divided. So every case came out
    # as the same evening with different weather, and the cast came out as an
    # employer, a bookkeeper, a technician and an outsider, because that is who
    # attends a transaction. The occasions below have nothing at stake but the
    # people.
    "a walking or climbing week, the last night, weather closing in",
    "a birthday nobody wanted to hold and everybody came to",
    "the night before somebody emigrates, with the house half in boxes",
    "a choir, band or team's twentieth anniversary, in the room they started in",
    "a vigil at a bedside that has gone on four days longer than expected",
    "a language school or summer course, the evening after the last class",
    "a religious festival in a house where only half of them still believe",
    "friends who rented a place together and have discovered they no longer like it",
    "a memorial swim, walk or climb for somebody who died doing it",
    "a dig, survey or field season packing up a week early",
    "a divorce being told to the family, over dinner, as agreed",
    "a christmas or new year nobody could get out of",
    "a group of strangers put together by weather, a delay or a road",
    "the night a long illness is finally named out loud",
]


# Other worlds (D-182). Every region above is the present day, and every occasion
# assumes modern life: a vote, a sale, a funding decision. The model can write
# any century and any planet, and the cases were all the same fifty years.
#
# A world is not a second deck drawn beside WHERE, because the two would not
# agree: Quebec in the reign of Nero is nothing. Each world brings everything
# the present day was quietly supplying. Where and when. Occasions that could
# only happen there. Who is coming instead of the police, since a Roman villa
# has no police and a generation ship has something else. And, for anything
# with machines, why the machines cannot simply answer the question: a station
# with cameras on every door is not a mystery, it is a playback.
#
# Dealt for about three cases in ten, and only when nobody named a setting.
# The rest stay in the present day, which is still a good place for a murder.
#
# `authority` is always plural ("the vigiles", "the wardens") because the page
# says "{authority} are on their way", and it always starts with "the".


@dataclass(frozen=True)
class World:
    key: str
    place: str
    occasions: tuple[str, ...]
    authority: str
    silence: str
    hues: tuple[str, str, str]


WORLD_SHARE = 0.30

WORLDS: list[World] = [
    # --- The ancient and medieval world. No forensics, no records anybody can
    # pull: what happened is what people saw and what they will admit to.
    World(
        "naples-62",
        "a villa above the Bay of Naples in AD 62, the spring after the earthquake, "
        "with cracks still in the frescoes",
        (
            "the night before a will is read aloud in front of the family's freedmen",
            "a dinner to settle a daughter's marriage contract, with the dowry "
            "already spent",
        ),
        "the magistrate's lictors from Puteoli",
        "Nobody here can read a body the way a physician of a later age would. "
        "Slaves see everything and are believed about nothing, which is itself "
        "a thing somebody can use.",
        ("#d4a05a", "#8fa6a0", "#c0584a"),
    ),
    World(
        "alexandria",
        "a scholar's house in Alexandria under the last of the Ptolemies, three "
        "streets from the Library",
        (
            "the night a disputed manuscript is to be copied and returned to "
            "its owner",
            "a symposium held to honour a teacher who is losing his sight",
        ),
        "the city watch of the Macedonian quarter",
        "Writing is rare and expensive, so what is written down is believed, "
        "and whoever holds the pen holds the truth.",
        ("#dcb35e", "#6f9fb8", "#c9604f"),
    ),
    World(
        "asturias-1080",
        "a monastery in the Asturian mountains in the winter of 1080, the pass "
        "closed by snow",
        (
            "the election of a new abbot, the night before the chapter votes",
            "a relic arriving from Compostela, and the pilgrims who carried it "
            "snowed in",
        ),
        "the bishop's men from Oviedo, once the pass opens",
        "Hours are kept by bells and candles, not clocks, and a brother who "
        "was at prayer is believed because doubting him is a sin.",
        ("#b89f6e", "#7f95a8", "#b5584e"),
    ),
    World(
        "venice-1748",
        "a Venetian palazzo during Carnival, 1748, with the masks due off at "
        "midnight",
        (
            "a card party where a family's last ship is being wagered",
            "the night before a daughter is sent to a convent against her will",
        ),
        "the Signori di Notte",
        "Everybody was masked until midnight, so who was where depends on who "
        "recognised whom by their walk, their voice or their shoes.",
        ("#c9a15a", "#7e98c2", "#c2564f"),
    ),
    World(
        "edo-fire-season",
        "a rice merchant's house in Edo in the winter fire season, with the "
        "watch-bell ringing every hour",
        (
            "the night the house's debts are called in by a rival guild",
            "a tea gathering to settle an adoption into the family name",
        ),
        "the magistrate's constables",
        "Rank decides who may speak to whom and who may enter which room, so an "
        "account is as much about who was allowed where as who was there.",
        ("#c7a36c", "#7c9a90", "#b7514a"),
    ),
    World(
        "lahore-road-1630",
        "a caravanserai on the Grand Trunk Road near Lahore in 1630, gates shut "
        "for the night",
        (
            "a merchant caravan waiting out a flood, with a dowry in the strongroom",
            "the night before an imperial tax collector arrives to count the goods",
        ),
        "the kotwal's men from Lahore",
        "Travellers come and go under other names, and the only register is "
        "what the keeper chose to remember.",
        ("#d8a653", "#7aa38c", "#c75e4e"),
    ),
    # --- The last two centuries, somewhere other than a country house.
    World(
        "south-georgia-1912",
        "a whaling station on South Georgia in 1912, the last ship of the season "
        "due in two days",
        (
            "the night the season's oil money is divided among the crews",
            "the manager's farewell before he sails home for good",
        ),
        "the magistrate from the station at Grytviken",
        "No telegraph reaches this far, and every man here has a reason to be "
        "on the next ship rather than a witness.",
        ("#b3ad90", "#86a5b3", "#bb6158"),
    ),
    World(
        "harlem-1926",
        "a Harlem brownstone during a rent party in 1926, the band still playing "
        "at two in the morning",
        (
            "a rent party thrown to save the house from the landlord",
            "the night a poet's first book comes back from the printer",
        ),
        "the precinct detectives",
        "Half the evening was illegal under Prohibition, so nobody wants to be "
        "the one who tells the precinct what they were drinking or where.",
        ("#d0a454", "#8a94c4", "#c85a50"),
    ),
    World(
        "shanghai-1937",
        "the rooms above a jazz club in the Shanghai International Settlement, "
        "November 1937, the guns audible across the river",
        (
            "the night the last boat tickets out are being divided",
            "a farewell for the club's owner, who is selling up in the morning",
        ),
        "the Settlement's municipal police",
        "Everybody here has papers, and half of the papers are false. Who a "
        "person is matters as much as where they were.",
        ("#d2a35c", "#7ca0b6", "#c9534c"),
    ),
    World(
        "polar-1968",
        "a Soviet polar research station in 1968, the supply plane a week late",
        (
            "the night before a report goes to Moscow that will end somebody's "
            "career",
            "a party for the station chief's fiftieth birthday, with the "
            "last of the spirit",
        ),
        "the investigator the Party is sending on the next plane",
        "Everybody watches everybody here, and everybody has been asked to "
        "report on the others, so every account is also a denunciation.",
        ("#b7b39a", "#7ea3bd", "#bf5a55"),
    ),
    World(
        "berlin-1989",
        "a flat in East Berlin on the night of 9 November 1989, the radio saying "
        "the border is open",
        (
            "a family deciding who crosses tonight and who stays with the flat",
            "a going-away dinner for a friend with a travel permit, which is "
            "suddenly worthless",
        ),
        "the Volkspolizei",
        "The Stasi kept files on all of them, so everyone assumes the others "
        "have already been talking, and nobody knows who.",
        ("#b8a47a", "#8898b0", "#c35a52"),
    ),
    # --- Contemporary, but nowhere near a country house.
    World(
        "antarctic-winterover",
        "an Antarctic research base in the last week before the winter-over, "
        "when the last flight leaves",
        (
            "the night the winter-over crew is chosen and the rest fly out",
            "a midwinter dinner held early because somebody is being sent home",
        ),
        "the federal police flying in from the coast",
        "The satellite link is rationed to an hour a day, and the only cameras "
        "point at the instruments, not the people.",
        ("#b9b8a4", "#7fa8c4", "#c05e58"),
    ),
    World(
        "stuck-ship",
        "a container ship anchored at the mouth of a canal, eleventh day waiting "
        "for a slot",
        (
            "the night the owners tell the crew the ship is being sold, crew and all",
            "a birthday on board with the last of the good food",
        ),
        "the port police launch, due at first light",
        "The bridge logs only the ship, not the people on it, and the crew's "
        "phones have had no signal for a week.",
        ("#c6a86a", "#6f9fb0", "#c45a4d"),
    ),
    World(
        "reality-villa",
        "a reality television villa on an island, the night before the live "
        "finale",
        (
            "the last night before the public vote is announced",
            "a producers' party after the cameras are switched off for the night",
        ),
        "the police launch from the mainland",
        "The cameras were switched off at midnight by contract, and every "
        "contestant has spent weeks learning to perform for them.",
        ("#e0a95c", "#76a7c4", "#d05a55"),
    ),
    # --- Futures. Each one says why its machines cannot solve the case, because
    # that is the whole difficulty of writing a murder in a world that watches.
    World(
        "generation-ship",
        "a generation ship in the two hundred and twelfth year of its voyage, "
        "where nobody alive has seen a planet",
        (
            "the night the council votes on whether to change course",
            "a naming day for the first child born in the new decks",
        ),
        "the ship's wardens",
        "The archive failed in year 190 and records have been kept by hand ever "
        "since. Nothing watches the corridors, because there has been nothing to "
        "watch for in living memory.",
        ("#b6a67e", "#7fb0c0", "#c85d57"),
    ),
    World(
        "europa-outpost",
        "a mining outpost under the ice of Europa, the relay to Earth down for a "
        "solar storm",
        (
            "the night the Company's buyout offer has to be answered",
            "a wake for a miner lost in the ice last week",
        ),
        "the Company's inspectors, once the relay is back",
        "The storm wiped the internal cameras, and in pressure suits everybody "
        "looks alike at twenty metres.",
        ("#a9b4a6", "#78aecb", "#c25b58"),
    ),
    World(
        "mars-election",
        "a Martian dome settlement on the night before its first vote on "
        "independence from Earth",
        (
            "the last night of campaigning, both sides under one roof",
            "the dinner at which the Earth governor's successor is chosen",
        ),
        "the Earth-appointed marshals",
        "The dome's monitoring is switched off by law for the election week, to "
        "prove that nobody is watching how anyone votes.",
        ("#d69457", "#8aa3b4", "#c2513f"),
    ),
    World(
        "lagos-2071",
        "a penthouse above the flooded lagoon city of Lagos in 2071",
        (
            "the engagement party of a tech heiress whose company is failing",
            "the launch night of an app that half the room built and one person owns",
        ),
        "the city's private security contractors",
        "Everyone in this room pays for a privacy seal, so their feeds cannot be "
        "opened without a court order that takes a week to get.",
        ("#d8a24d", "#6fb0b8", "#cf5a4c"),
    ),
    World(
        "cryo-waking",
        "a cryonics facility in the Swiss Alps in 2090, on the night the first "
        "patients are woken",
        (
            "the waking of a founder who has been frozen for forty years",
            "the night the board decides whose relatives are woken first",
        ),
        "the cantonal police",
        "The wake halls run without electronics during the protocol, so for "
        "six hours the building knows only what the staff remember.",
        ("#bcb6a0", "#86a8c8", "#c5605c"),
    ),
    World(
        "orbital-hotel",
        "an orbital hotel on its last night before it is deorbited into the sea",
        (
            "the closing party for the staff who ran it for thirty years",
            "the last paying guests, who each bought the final night for a reason",
        ),
        "the orbital authority's shuttle",
        "The hotel's systems are being switched off floor by floor, and "
        "logging was the first thing to go.",
        ("#c9b07a", "#7aa2d0", "#cc5d5a"),
    ),
    World(
        "svalbard-2140",
        "the seed vault on Svalbard in 2140, a generation after the grids failed",
        (
            "the night the keepers vote on whether to open the vault to the south",
            "the handover from one keeper family to the next",
        ),
        "the council riders from Longyearbyen",
        "There has been no electricity for surveillance in forty years. There is "
        "a logbook, and whoever keeps it decides what happened.",
        ("#b4b09c", "#7fa0b8", "#bd5a55"),
    ),
]


def world(seed: int) -> World | None:
    """The other world this seed deals, or None for the present day (D-182).

    Keyed on the seed alone, like `where` and `occasion`, so a case reproduces
    from the number the run prints.
    """
    rng = random.Random(f"world|{seed}")
    if rng.random() >= WORLD_SHARE:
        return None
    return rng.choice(WORLDS)


def world_for(seed: int, setting: str) -> World | None:
    """The world a case is actually in, given the setting it was written from.

    A world only applies when the setting is one of its own occasions, which is
    what `occasion` deals for it. A setting somebody typed in by hand is theirs,
    so a seed that would have dealt Venice does not drag "a board stranded by
    weather" into 1748.
    """
    dealt = world(seed)
    if dealt is not None and setting in dealt.occasions:
        return dealt
    return None


def world_named(key: str) -> World | None:
    return next((w for w in WORLDS if w.key == key), None)


@dataclass(frozen=True)
class Palette:
    manners: list[str]
    voices: list[str]
    motive: str
    intrigues: list[str]
    standing: str = ""
    old_business: str = ""
    where: str = ""
    world: World | None = None

    def _where(self) -> str:
        if self.world is None:
            return (
                f"**Where on earth this house is:** {self.where}. That decides the "
                f"names, the food, the weather, the money and how the building is "
                f"built. Do not write a travel brochure of it and do not make anybody "
                f"a type: it should show mostly in what people are called and what "
                f"they take for granted. **If the setting given below already implies "
                f"a place, that wins and you ignore this line entirely** — and a "
                f"period or a style implies one as surely as a country does. A "
                f"Victorian castle is British, a dacha is Russian, a hacienda is "
                f"Spanish-speaking. Only use the line above when the setting could "
                f"honestly be anywhere."
            )
        w = self.world
        return (
            f"**This case is not in the present day.** It is set in {w.place}. "
            f"That decides everything the present day would otherwise supply: "
            f"what people are called, how they speak, what they eat, what they "
            f"believe, what a room is lit by, what time is told by and what counts "
            f"as proof. **No anachronisms**: nobody says okay in Rome, nobody has a "
            f"phone in 1748, and in a future the technology is part of the world "
            f"rather than decoration. The `slots` are labelled the way this world "
            f"tells the time. Write it as people who live there, not as a costume "
            f"drama about them.\n\n"
            f"**Who is coming.** Wherever these instructions say the police, read "
            f"{w.authority}. They are on their way, they are not here yet, and "
            f"they are not the person asking the questions.\n\n"
            f"**Why this world cannot simply answer the question.** {w.silence} "
            f"Keep to that. A case where a record, a machine or a witness nobody "
            f"can doubt would settle it in one step is not a case."
        )

    def brief(self) -> str:
        manners = "\n".join(f"  - {m}" for m in self.manners)
        voices = "\n".join(f"  - {v}" for v in self.voices)
        intrigues = "\n".join(f"  - {i}" for i in self.intrigues)
        return (
            f"MATERIAL FOR THIS CASE\n"
            f"Not a menu to choose from. This is the assignment, and the point of "
            f"it is that the next case gets different material.\n\n"
            f"{self._where()}\n\n"
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
            f"killer's motive:\n{intrigues}\n\n"
            f"**The first of the three is heavier than the other two.** It is "
            f"dealt from the end of the deck that would end somebody, and it is "
            f"the one to build the innocent's chain on: deep, gated, damning, "
            f"and with a floor underneath it that is not guilt. The other two "
            f"are smaller obstructions, and they should stay small. Five people "
            f"whose lives are all ending tonight is melodrama; one person whose "
            f"life is ending and four with something to be awkward about is a "
            f"house.\n"
        )


def draw(seed: int, setting: str, topology: str, cast_size: int = 5) -> Palette:
    """Deal one case's material.

    Keyed on everything that identifies the case rather than the seed alone, so
    that running seed 0 against four different settings does not produce the
    same four hands.
    """
    rng = random.Random(f"{seed}|{setting}|{topology}")
    dealt = world_for(seed, setting)
    return Palette(
        manners=rng.sample(MANNERS, min(cast_size, len(MANNERS))),
        voices=rng.sample(VOICES, min(cast_size, len(VOICES))),
        motive=rng.choice(MOTIVES),
        # One heavy one, always (D-170). The deck used to be sampled flat, and
        # with fourteen of twenty four merely awkward a hand of three was
        # usually three embarrassments, which cannot carry a rival chain.
        intrigues=[rng.choice(WEIGHTY), *rng.sample(DAMAGING + AWKWARD, 2)],
        standing=rng.choice(STANDINGS),
        old_business=rng.choice(OLD_BUSINESS),
        # Drawn on the seed alone, deliberately. The other decks are keyed on the
        # setting so that one seed against four settings gives four hands; this
        # one must vary even when the setting phrase does not, because the
        # setting phrase is exactly what was dragging every cast to one country
        # (D-111).
        where=(dealt.place if dealt else random.Random(f"where|{seed}").choice(WHERE)),
        world=dealt,
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

    **Not earlier than the third slot** (D-158). Dealing from the second was the
    original rule and it made a quarter of all cases impossible to write: the
    victim can only appear at or before the murder, so a murder at slot 2 of 5
    gives him two hours to exist in, while the request asks for a private scene
    with the killer, usually an earlier one with the same pair, and a victim who
    "should have been working on all of them tonight". Measured over the corpus
    the model writes 3.56 victim scenes and does not reduce that when the murder
    is early, so at slot 2 the draft is born unsatisfiable. Slot 3 of 5 still
    breaks the "who lies about the second to last hour" shortcut, which is what
    this function exists for, and leaves the victim a life.

    The floor is `min(3, slot_count)` so a short evening still returns a legal
    slot rather than an empty range.
    """
    return random.Random(f"murder|{seed}").randrange(
        min(3, slot_count), slot_count + 1
    )


# One palette per region, and the region is drawn from the seed like everything
# else (D-164). Every case looked identical: the same near-black with the same
# gold, whether the evening was a Baltic port or inland Andalusia in the last
# heat of the year. The screen never learned anything about the case.
#
# Derived from the region rather than sampled from the generated backdrop, for
# two reasons. It works with `--art` off, which is most of the time and all of
# the tests; and sampling makes the colour of the evening depend on whether the
# image came out well, which is the one thing about a case nobody can predict.
#
# Ground and text stay fixed everywhere. Only the three accents move, because
# legibility is not a thing to deal from a seed: `warm` is the one that carries
# the case's temperature, `cool` is what the interface uses for its own voice,
# and `bad` is reserved for contradiction and stays roughly red in every set.
PALETTES: dict[str, tuple[str, str, str]] = {
    "Dutch or Flemish": ("#c8b27a", "#7fa9ee", "#d9726b"),
    "Italian north": ("#c9a05c", "#8fa6c4", "#c4655c"),
    "coastal Portugal": ("#d8a15c", "#6fa8b8", "#d0685f"),
    "Scottish borders": ("#b9a878", "#89a2b4", "#c06a62"),
    "inland Andalusia": ("#e0a44e", "#a89466", "#cc5f4e"),
    "Bohemian or Moravian": ("#b39a6a", "#7e93ad", "#b8635c"),
    "Aegean": ("#e3b45e", "#6f9fc4", "#d4685c"),
    "Quebec or the Maritimes": ("#c4a06a", "#7d9dc0", "#c66a63"),
    "Japanese countryside": ("#c2a878", "#7d9b8e", "#b5615a"),
    "Argentine litoral": ("#d9a24e", "#8aa88f", "#c9655b"),
    "Baltic port": ("#b8ad86", "#84a5ae", "#bc6760"),
    "Maghreb coast": ("#dfae5d", "#6f9eb0", "#cf6353"),
    "Kerala or the Konkan": ("#d9a556", "#75a58c", "#c66253"),
    "Anatolian plateau": ("#c9a05a", "#93a17f", "#c2655a"),
    "alpine valley": ("#bfa97a", "#88a0b8", "#bf6a61"),
    "American upper midwest": ("#bda878", "#8098b4", "#c2685f"),
}


def hues(seed: int, world_key: str = "") -> dict[str, str]:
    """The three accents for this case, keyed to the region it is set in.

    A case in another world (D-182) carries its own three, and says which world
    it is in by the key stamped on it, never by re-dealing the seed: a case
    written before worlds existed must not change colour because its seed would
    deal Venice today.

    Falls back to the shipped gold and blue rather than raising, because a
    palette is decoration and a case that cannot be coloured must still be
    playable.
    """
    elsewhere = world_named(world_key) if world_key else None
    if elsewhere is not None:
        warm, cool, bad = elsewhere.hues
        return {"warm": warm, "cool": cool, "bad": bad}
    region = random.Random(f"where|{seed}").choice(WHERE)
    for name, colours in PALETTES.items():
        if region.startswith(name) or name.lower() in region.lower():
            warm, cool, bad = colours
            return {"warm": warm, "cool": cool, "bad": bad}
    return {"warm": "#d9a24e", "cool": "#7fa9ee", "bad": "#e0736b"}


def occasion(seed: int) -> str:
    """What is happening tonight, drawn from the seed.

    Used when nobody passed `--setting`. Keyed the same way as `where`, on the
    seed alone, so that the two together are reproducible from the number the
    run prints and nothing else (D-115). A seed that deals another world gets
    one of that world's own occasions (D-182).
    """
    dealt = world(seed)
    pool = dealt.occasions if dealt is not None else OCCASIONS
    return random.Random(f"occasion|{seed}").choice(pool)
