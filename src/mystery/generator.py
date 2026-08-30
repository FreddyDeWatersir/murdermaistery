"""Ask a language model for a cast and a set of constraints.

This is the only place in the project that talks to a model. It asks for a cast,
a constraint set, and the timeline grid, because the model is the only component
that knows *why* anyone is anywhere (D-029). The solver then repairs whatever
the model got wrong rather than rebuilding from scratch.

Three things matter about the shape here.

The model boundary is a plain callable, `Drafter`, taking a request and
returning raw JSON. The real one calls Anthropic; tests pass a fake. Every
framework layer that hides this boundary makes it harder to test, which is why
there is no framework (D-002).

Output is schema-forced rather than "please return JSON". The Pydantic schema is
handed to the model as a tool definition and the model is required to call it,
so malformed output is rejected by the API before it reaches us.

Everything is written as UTF-8 explicitly. Windows defaults to cp1252, and a
model will put a c-caron in a surname the first time you look away.

Responses are cached to disk by request hash (D-005). Developing the validator
and solver needs a corpus, not a live model, and a corpus costs money once.
"""

import hashlib
import os
import re
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from mystery.models import Mystery
from mystery.palette import draw as draw_palette
from mystery.topology import DEFAULT as DEFAULT_TOPOLOGY
from mystery.topology import get as get_topology

# Reads .env from the project root if present, so a key can live in a
# gitignored file instead of being re-exported in every new terminal.
load_dotenv()

log = structlog.get_logger()

# Two jobs, two models (D-060).
#
# Drafting happens once per case and settles everything the player will meet:
# whether the cast are people or job titles, whether the secrets interlock,
# whether the grid means anything. One call, a few cents, and every later call
# in the session inherits whatever it decided. It gets the strongest model.
DRAFT_MODEL = "claude-opus-5"

# The suspects answer one question at a time, dozens of times an evening. This
# is where the money actually goes, so it stays a tier down. Override with
# --model if a case is worth the better liar.
VOICE_MODEL = "claude-sonnet-5"

# Dollars per million tokens, input then output. Here so that the log can say
# what a call actually cost rather than leaving it to a bill three weeks later,
# which is the lesson from getting the image prices wrong by a factor of forty
# five (D-082, D-084).
RATES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}

# What one draft actually costs, from the logs. Re-measured after the prompt grew
# (D-110): thirteen thousand in and seven and a half out, against eight and a
# half and six when this was first written. The estimate printed before a run is
# only honest if this is kept up to date with the prompt.
TYPICAL_DRAFT = (13000, 7500)


def cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """What a call cost, in dollars. Zero for a model we have no rate for."""
    rate_in, rate_out = RATES.get(model, (0.0, 0.0))
    return (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000


def draft_estimate(model: str = DRAFT_MODEL, drafts: int = 1) -> float:
    return cost(model, *TYPICAL_DRAFT) * drafts


# The placeholder in every example command in STATE.md and in this module's own
# docstring. Pasted through once and three Opus drafts were spent writing a
# murder set in nothing (D-110). Refusing it costs nothing and the run that
# taught us this cost seventy four cents.
def complaint_about_setting(setting: str) -> str | None:
    """Why this setting cannot be used, or None if it can.

    Not a taste check. The only thing being caught is a setting that carries no
    words: the ellipsis placeholder, an empty string, punctuation on its own.
    """
    words = re.sub(r"[^\w\s]", " ", setting).split()
    if not words:
        return (
            f"--setting {setting!r} is the placeholder, not a setting. "
            "Give the model somewhere to put five people, for example "
            '--setting "the last night of a residency at an old house"'
        )
    if len("".join(words)) < 6:
        return (
            f"--setting {setting!r} is too thin to write a case from. "
            "A phrase, not a word: who is gathered, where, and why tonight."
        )
    return None


class GenerationRequest(BaseModel):
    """What we ask for. Everything the prompt varies on lives here, so the cache
    key is just a hash of this."""

    setting: str
    cast_size: int = 5
    slot_count: int = 5
    place_count: int = 5
    # The id of a shape in the topology library, not a description. What the
    # shape means is a paragraph the generator is given, and it is the only part
    # of the instructions that changes between cases (D-067).
    topology: str = DEFAULT_TOPOLOGY
    seed: int = 0

    def cache_key(self) -> str:
        """A hash of exactly what is about to be sent, and nothing else.

        Without the prompt in the key, editing the prompt changes nothing: every
        previously generated seed keeps returning the draft it produced under the
        old instructions, and you spend an afternoon wondering why your changes
        had no effect. They did. You were reading a cached answer (D-035).

        This used to hash the request plus a couple of the pieces that go into
        the prompt, which meant every new piece was a new chance to forget one.
        The topology brief was nearly missed, the drawn material would have been
        (D-075). Hashing the finished prompt cannot fall behind.
        """
        payload = (SYSTEM_PROMPT + _user_prompt(self)).encode()
        return hashlib.sha256(payload).hexdigest()[:16]


# A Drafter takes a request plus any complaints about its previous attempt, and
# returns the raw dict the model produced. Anything satisfying this can stand in:
# the real API, a fake, a replay of a recorded response.
#
# The complaints argument is what makes generation self-correcting. A model that
# invents a character id, or wraps its answer in a stray key, cannot be fixed by
# the solver: only the model can fix it, so the failure has to travel back to the
# model rather than to the user (D-037).
Drafter = Callable[[GenerationRequest, list[str]], dict[str, Any]]


SYSTEM_PROMPT = """\
You design murder mysteries that are solvable but not obvious. You work the way \
a writer does, from the story outward, and you finish by writing down the \
evening as a grid.

Work in this order.

0. Before the cast, decide **what is happening tonight**. The setting names a \
place; it does not name an occasion, and a place with nothing happening in it \
produces the same evening every time. Something is at stake this evening and it \
would have been at stake even if nobody had died: money arrives or does not, a \
decision is announced, somebody is leaving, an inspection lands in the morning, \
a thing that has been put off for a year cannot be put off past tonight. Write \
that first and let the cast follow from it.

**Resist the obvious staffing.** Given a place, there is a set of jobs that \
comes to mind immediately, and it is the same set every time: the owner, the \
deputy, the one who keeps the books, the loyal old hand of forty years, the \
young assistant, the outsider visiting. Four cases in a row came back with \
exactly those six. At least half this cast should be people that list would not \
have produced: somebody who does not work here, somebody who used to, somebody \
present for a reason unrelated to the business of the place, somebody whose \
connection to the victim is personal and old. The rooms go the same way. Do not \
reach for the obvious floor plan either.

**Title it as a novel would.** Take a phrase out of the case itself, something \
a reader only understands afterwards.

Two failure modes, both seen. The template: "The Last <noun> at <place>", three \
times out of four. And the setting's own noun as a stem, which produced *What \
the Fog Owes Us*, *What the Fog Keeps* and *What the Fog Owes* from one setting \
on three different seeds. Do not build the title out of the most obvious word in \
the setting. Build it out of something only this case contains: a phrase \
somebody says, an object, a number, a name, the thing that was promised.

**The player always arrives after the body has been found.** They did not see \
it happen, they did not see anybody leave, and they have no observation of their \
own from before the discovery. Everything they know, they were told. Never write \
the case around something the questioner personally witnessed.

**Say who is asking the questions.** Fill in `investigator` with the person the \
player is tonight: `role` (what they are, in a few words), `why_here` (the \
reason they were in this building before anybody died, or arrived within the \
hour), and `standing` (what they can and cannot do). They are **never police**. \
They cannot arrest, charge or compel anybody. What they have is a professional \
reason to be asking and somebody's authority behind them that is not legal \
authority. "A detective" is wrong. So is anybody who can compel an answer.

**What kind of person that is, is dealt to you** under MATERIAL FOR THIS CASE \
below, and it is the assignment rather than a suggestion. Work out who that \
description is in *this* building and write them. Asked to invent this freely, \
and shown one worked example, five consecutive cases produced five insurance \
assessors, which is why it is no longer being asked freely.

1. The cast. Each suspect wants something and each is concealing something. \
Only one of those secrets is the murder. A cast where three people have nothing \
to hide is three cooperative witnesses and one obvious liar, and there is no \
game.

For every character fill in `role`, `gender`, `look`, `wants`, `manner`, \
`under_pressure`, and `impressions`.

`role` is one short public phrase: their job here and what they were to the \
victim. "The stage manager, twenty two years in this building." "His \
business partner." "The understudy." This is printed under their name before \
the player has asked anything, so it must contain nothing they would hide.

`wants` is the opposite: private, what they are actually after tonight. The \
player never sees it written down and has to work it out.

`gender` is "woman" or "man". `look` is one sentence: roughly how old, build, \
and how they are dressed this evening. Be concrete, and vary it. Not everyone \
is elegant and in their forties. Somebody is over sixty. Somebody is under \
twenty five.

`manner` and `under_pressure` are how they behave when questioned, and they are \
the whole difference between a witness reciting locations and a person. This \
case arrives with a list of manners, one per suspect, under MATERIAL FOR THIS \
CASE. Use them. They are behaviours rather than characters, so the work is \
yours: decide who gets which, decide what it looks like in *this* person in \
*this* house, and write `manner` and `under_pressure` in your own words rather \
than copying the line. A manner should change what somebody actually says when \
pressed, not sit in a field being true.

`impressions` maps each *other* character's id to what this person thinks of \
them, in a sentence, in their voice. Give every character an impression of the \
victim and of at least two others. This is what makes them worth talking to: \
without it a suspect can only recite where they stood, and a player who asks \
"what did you make of him" gets nothing back.

2. The murder. Who, whom, how, and above all why. The motive comes with the \
case, under MATERIAL FOR THIS CASE, as a situation rather than a plot: make it \
specific to these people, and make it come out of what the killer is \
concealing.

3. The secrets, and this is the step that decides whether the case is any good. \
The threads listed under MATERIAL FOR THIS CASE are what the innocent suspects \
are busy hiding: turn each one into a secret with a holder, and let them cross \
each other rather than running in parallel.

**The victim is the hub.** Do not give five suspects five unrelated subplots \
with one murder bolted on. The victim held something over most of the room: a \
contract, a debt, a piece of knowledge, a decision about someone's future. At \
least half the suspects must be concealing something that involves the victim, \
so that half the cast has a motive and the killer is not the only person with a \
reason to be evasive.

**Gate the killer's motive.** The secret that explains why the killer did it \
must be reachable only after some other character's secret has surfaced. Set \
`revealed_by` on it to the id of that other secret. This is what stops the \
obvious suspect from being the answer.

**Three people lie about where they were, and only one of them is the killer.** \
This is the most important instruction here. If the killer is the only liar, \
then working out who lied is the same as working out who did it, the player \
solves the case from the timeline alone, and every secret you have written is \
decoration. Fill in `false_claims` with three entries: the killer, and two \
innocent people who lied for their own reasons.

For every entry give the room and the slot they will claim, which must not be \
where they actually were, plus `covers` (the id of the secret the lie protects) \
and `admits_when` (what would make them drop it). **`covers` is not optional and \
must name a real secret.** Nobody lies about where they were for no reason. A \
lie with nothing underneath it is the worst thing in the game: the player \
catches it, presses it, spends ten questions on it and finds an empty room, and \
learns from that that pressing does not pay. If you cannot say what a lie \
protects, do not write the lie. The innocent lies are the \
good part: somebody was where they should not have been, with someone they \
should not have been with, going through papers that were not theirs. Being \
caught out is embarrassing rather than fatal, and that is exactly why they hold \
the line for a while.

Every liar must claim a room that had **at least one other person in it at that \
moment**, and the killer's room needs **two**, ideally people who are themselves \
concealing something. An empty room is an unbreakable alibi: nobody can say they \
were not there, the lie never surfaces, and a red herring nobody can detect is a \
wasted character. A witness with nothing to hide is believed instantly and ends \
the game in one question.

**Give every innocent lie a way out.** The player must be able to resolve it, \
not merely detect it. Either somebody else knows the secret it covers, so it can \
be heard from a third party, or `admits_when` names a real condition under which \
they will come clean. A lie the player catches and can never get underneath \
teaches them that pressing does not pay, which is the opposite of the point.

**One innocent liar must also have been alone.** The killer is unwitnessed at \
the murder because they were alone with the victim. If every innocent liar can \
be vouched for by somebody, the player stops thinking and asks "which liar has \
no witness", and the answer is always the killer. Put at least one innocent \
somewhere unobserved when they lied, so that test leaves two candidates and the \
motive has to break the tie.

**Mark the killer's motive.** The killer holds two secrets: the background that \
made them vulnerable, and the reason they killed. Set `is_motive` to true on the \
second one, and gate it with `revealed_by`.

**Somebody else must half know why.** The killer will never say the reason they \
did it, so put at least one other character in the motive's `known_by`: someone \
who saw the argument, was told part of it, or worked out enough of it to repeat. \
Without that the reason for the murder exists nowhere the player can reach, and \
naming it is impossible. The player is asked for the killer *and* the motive at \
the end, so the motive has to be findable.

**Every secret needs a breaking point.** Fill in `breaks_when` with the \
condition under which its holder stops concealing it: confronted with a named \
fact, offered something in return, asked a question they were not braced for, \
told that someone else has already said it. Concealment that never breaks is a \
wall rather than a mystery, and the conditions should differ from character to \
character.

**Write it as a state of affairs, not as a stage direction.** "Once she believes \
somebody else has read the letters" is a condition: any number of things a \
player might say could bring it about, and she is a person who folds when her \
privacy is already gone. "Shown the letters and asked, without preamble, who \
resealed them" is a script, and a script gets played as a password: the player \
does the right thing in the wrong words and nothing happens, which reads as the \
game being broken rather than the character being difficult. Describe what this \
person's resistance is made of and what dissolves it. Never a required gesture, \
a required order of words, or a particular phrasing.

**Entangle them with each other, not only with the dead man.** This is the \
other half of the same failure and it is the deeper one.

Asked for a victim who is a hub, the obvious move is to give every suspect a \
secret about the victim and stop. Five real cases came back that way, and in the \
one somebody played, **not a single secret was about another suspect**. Four \
pointed at the dead man and three pointed at nobody. The player questioned each \
person, took the one thing they had, and moved on, because nothing anybody said \
gave them a reason to go from this person to that one.

What a house of suspects should be is a web. The one who keeps the accounts is \
protecting the son. The son is covering for somebody's wife. She knows what the \
solicitor did. **At least three in ten of your secrets must be about another \
suspect**, and every suspect must be tied to at least one other, either by \
holding something about them or by being in somebody's `known_by`. Nobody is an \
island: if the player learns nothing that leads towards a person, that person \
is furniture.

**The old business binds them.** Under MATERIAL FOR THIS CASE you are dealt a \
thing that happened here before tonight, that most of this cast was present for, \
and that nobody has raised since. Use it. It is what gives them reasons to know \
about each other rather than only about the victim, it is why they each have a \
different reason for not mentioning it, and it means the question the player is \
really answering stops being "who wanted him dead this week" and becomes "what \
happened in this place".

**The victim should have been working on all of them, tonight.** Not five old \
grievances: five things happening this evening. He was going to sign something \
away from one of them, had already told another they were finished, was about to \
be told something by a third. A victim who was busy is a victim who is worth \
asking about, and a case where five people were each being damaged in a \
different way over one evening produces its own suspects without being asked to.

**The case must have a second half.** This is the thing most likely to go wrong \
and it went wrong five times out of five.

Asked to gate the killer's motive behind another secret, the obvious move is to \
gate exactly that and leave everything else lying on the surface. Five cases in \
a row came back with seven secrets, six of them available cold and one gate. A \
player asked a hundred and one questions, was given everything the killer had \
inside nine, and spent the remaining ninety-two finding nothing. They called it \
easy and unsatisfying, and they were describing a case with no middle.

So: **at least four in ten of your secrets need something else to surface \
first**, and at least one chain must be **two deep**: A opens B, and B opens C, \
where C is the thing that matters. Build it as a real order of discovery, not as \
a lock on a box. The first thing is something anybody would let slip. The second \
is what that first thing gives you leverage to ask about. The third is what \
somebody will only say once they know you already have the second.

Think about the shape of an evening rather than a list of facts. What can be got \
in the first ten minutes; what is only worth asking after that; what nobody would \
say to a stranger who did not already half know it.

**At least three of them must look guilty.** Mark every secret that would put \
its holder on the list, on its own, with `damning: true`. Not "they were \
evasive" and not "they had a grievance": a reader who learned only this would \
write that name down. Money that dies with the victim, a threat somebody made \
out loud, a ruin the victim was about to cause them, a thing they were about to \
lose tonight. The killer's motive is damning by definition. **At least two \
other people need one as well**, and it must be false, or a dead end, or about \
somebody who could not have been there.

A case where only the killer has a real reason plays fast and flat: the player \
finds the one person with something and stops. That happened, and it was \
reported back as smooth and not engaging. Grievances are not enough. Three \
people the player would genuinely put in the frame is the target, and only one \
of them did it.

**A secret that gates another one must be a thing, not just a fact.** Whenever \
you put `revealed_by` on a secret, the secret it points at has to carry \
`evidence`: the object that proves it and that the player can pick up and put \
in front of somebody. The ledger pages. The letter of reference. The photograph \
of the loan documents. This is not decoration: producing that object is how the \
player opens the gate, and a gate with nothing behind it can only be argued at, \
which means in practice it never opens at all.

**Name it as an object, not as a conclusion.** A phrase somebody could read off \
a card in an evidence bag: what it physically is, plus the one detail that makes \
it damning. "A bundle of twelve letters in a ribbon, dated February to October" \
is right, and so is "A bone paperknife and a drawer of slit-and-regummed \
envelopes": you can see both, and neither tells you what it proves. "Proof that \
Margit read the post" is wrong, because it is the answer printed on the front of \
the question. The player is holding this thing and deciding who to put it in \
front of, and that decision is only interesting while the object is still a \
thing rather than a label.

Everything else can be `evidence`-free. Most secrets are things people know, \
not things people keep in a drawer, and a case where every secret comes with a \
document reads like an audit.

Do not write a `breaks_when` for the killer's own motive that involves being \
shown anything. They never give that up, to anybody, under any circumstances. \
It reaches the player through somebody else or not at all.

Put all of this in `secrets`, with `holder`, `about`, `summary`, `known_by` for \
anyone else who knows, `revealed_by` where one secret gates another, `evidence` \
on any secret that gates another, and `breaks_when` on every one.

4. The constraints: the things that must be true of the evening. A constraint \
names people who share a place at a moment. Mark it `exclusive` when they must \
be alone with nobody else present. You need, at minimum:
   - the killer and the victim alone together
   - at least two other suspects with a private moment of their own, so a \
missing alibi proves nothing on its own
   - one exchange overheard by exactly one person who was not part of it

**Give the building a floor plan.** Every place lists `adjacent`: the other \
places you can walk to, or hear through a wall, directly from it. Doors, not \
routes: the storeroom is adjacent to the corridor, not to the office at the far \
end of it. Make it a plan somebody could walk through, so no room is cut off \
from the rest, and put the overhearer next door to whatever they overhear. You \
only have to write each door once, from either side.

**After the killing, that room is empty.** Nobody goes back into it, and \
nobody has a scene there, until the body is found. The discovery happens after \
the evening is over, which means nobody found the body during it, which means \
nobody was in the room. Put the killer's return, the last check, the clearing \
up, anywhere else. Two people working next to a corpse and not mentioning it is \
the single fastest way to make a player stop believing the evening.

**`exclusive` is literal and it is about the room, not the scene.** It means \
nobody else is in that place at that moment, full stop. Two exclusive \
constraints cannot share a place and a slot: only one private scene fits in one \
room at one time, however well both of them read.

The overheard exchange is where this goes wrong. The listener is **not in the \
room**. Put them in a different place for that slot, one they could plausibly \
hear from, and say in the prose that they heard it through a door or from the \
next room. A witness placed inside the room is not overhearing, they are \
present, and the two scenes then contradict each other and the case is thrown \
away.

Relatedly, **a place is one room**. Do not write a place called "the office and \
the corridor outside it": that is two places and you will need both of them \
precisely when somebody is standing in one listening to the other.

5. The grid. For every character and every slot, the place they were. Put it in \
`placements` as character id, then slot id, then place id. Fill in every cell.

**People stand still.** At a gathering, most people stay in one room for long \
stretches. A character who visits four rooms in five slots reads as a random \
walk, not a person. Every move a character makes must have a reason you could \
name, and most characters should move once or twice all evening. Someone who \
never leaves the main room the entire time is realistic and useful.

This last step is the one that matters and it is yours, not a solver's. You are \
the only part of this system that knows *why* anyone is anywhere. Someone slips \
to the storeroom because of the affair; someone takes the critic outside because \
they want to know what he has found out. A grid without those reasons reads as \
people wandering at random, and a player reconstructing it learns nothing.

So place people for reasons, and use `description` on each constraint to say \
what the reason was.

Hard requirements on the grid:
- Every character has exactly one place in every slot. No gaps.
- Every constraint you wrote must actually hold in the grid you produce. If you \
say two people were alone together at 21:00, nobody else may be in that room at \
21:00.
- The killer and victim's room must contain only the two of them.
- Bind every constraint: give each one the `place` and `slot` where it happens.
- Do not have anyone in two rooms at once, and do not leave a constraint \
floating without a place and slot.
- **The body is not found during the timeline.** The slots cover the evening up \
to and including the murder and its immediate aftermath. Discovery happens after \
the last slot, because everything the player investigates is what people were \
doing before anyone knew. Never write a constraint where someone finds the body.
- Name the killer and the victim in the `killer` and `victim` fields, and set \
`murder` to the id of the constraint where the killing happens. A good case \
usually has an earlier private scene between those same two people, the one \
where the victim says the thing that gets them killed, so which of the two is \
the murder cannot be guessed from the outside. Say which.
- Fill in `discovery`: who found the body, in which room, and a sentence about \
how. This happened after the last slot and everybody knows it. Without it the \
suspects cannot discuss the death they are being questioned about.
- Fill in `common_ground` with four to six plain sentences: the things about \
this occasion that everybody in the building would say the same way. What the \
gathering is, what happens in the morning, how long people have been here, who \
pays for it. **Every number that matters goes here and nowhere else**: how many \
people live in the house, how many names are on the list, how many years since \
the thing they all remember. Each suspect is given this block verbatim and is \
forbidden to invent a figure that is not in it, because when one of them says \
six and another says nine about the same list the house stops being a real \
place. Write no secret here: this is only what is said out loud at breakfast.

Design rules for a case worth playing:

**Every character must be load-bearing.** Before you finish, go through the cast \
one at a time and ask what the case loses if you delete them. If the answer is \
nothing, they are decoration and the player will waste questions on them and \
feel cheated. Each suspect must be at least two of the following: someone who \
can contradict the killer's story, someone whose secret gates another secret, \
someone who knows a secret that is not theirs (put them in that secret's \
`known_by`), or the holder of the motive.

Weave them together. A knows something about B. B is the only person who can \
undermine C. C's secret is what makes A's behaviour make sense. A cast of five \
separate people with five separate problems is five short conversations that go \
nowhere.

- The killer's alibi must be breakable by combining at least two people's \
testimony, and by no single person's alone.
- The killer's motive should only become visible after some unrelated-looking \
secret has been cracked, so that the obvious suspect is not the answer.
- Six to ten constraints.

Names belong to the setting. A gathering in Amsterdam has Dutch names, one in \
Naples has Italian ones. Reaching for the same handful of Anglo-thriller \
surnames every time is the fastest way to make every case feel like the last one.

Ids are short lowercase snake_case. Every id you reference must exist.

---

Here is one case that worked, abridged to its skeleton. It is here for the \
*shape*, not the content. Do not reuse the setting, the names, the theft, the \
counterweight bar, or the lighting box. Build something that holds together the \
way this one does.

**Opening night at an Amsterdam theatre.** Rooms: stage and wings, green room, \
dressing corridor, prop store, lighting box, stage door. Slots: 19:40 half hour \
call, 20:00 Act 1, 20:40 Act 1 continued, 21:00 interval, 21:20 Act 2.

*The cast, and what each of them is sitting on.* Ilse, the lead, late forties, \
overheard the producer say she was finished after this run and has told nobody. \
Tomas, the director, has been inflating production costs and pocketing the \
difference. Nadia, the understudy, was sleeping with the producer, who promised \
her the part and then went cold. Wouter, stage manager, twenty two years in this \
building, has been quietly selling theatre equipment. Renske, co-producer, found \
out her partner was moving money out of the company. Bram, the producer, is the \
victim, and note what he is: not a nice man who died, but the one thing all five \
have in common. He had leverage over every person in the room. That is what \
makes it a case rather than five separate problems with a corpse in the middle.

*The murder.* Wouter. At the half hour call Bram told him he had traced the \
missing equipment and would go to the police after the run. Wouter asked him to \
the prop store at the interval to show him where it all went, and killed him \
there.

*The lie.* Wouter says he spent the interval in the lighting box running the Act \
2 cue stack. He picked a room he could account for and even logged a cue under \
his initials afterwards to back it up.

*The other liars, which is what makes it a case rather than a quiz.* Renske says \
she was in the green room during the interval. She was in the lighting box going \
through Bram's files, and she will not say so, because saying so means admitting \
what she was looking for. Nadia says she was in the dressing corridor the whole \
of Act 1 and was in fact at the stage door with Bram, having the argument that \
ended it. Both are caught out on the timeline exactly as easily as Wouter is. \
Neither of them killed anybody. A player who finds one of these and stops has \
accused the wrong person with complete confidence, which is the best feeling this \
game can produce.

*Why the lie holds for a while.* Renske was in the lighting box the whole \
interval, so she knows it was empty, and she will not say so, because saying so \
means admitting she was going through Bram's files. Her testimony is gated \
behind cracking her, and she cracks only once the player knows about the money. \
Ilse saw a figure cross toward the prop store and thought it was Wouter by the \
walk, but the corridor was half lit and she will not swear to it. The prop store \
was locked afterwards and only two men held keys, one of them the dead one, but \
a spare has been missing for months and Wouter can say so truthfully. Three \
contradictors, not one of them enough alone, and together conclusive.

*The chain the player has to walk:* learn Bram was moving money, which cracks \
Renske, which empties the lighting box, which turns Ilse's half sighting and the \
key into evidence.

*The shield.* Pressed hard, Wouter confesses to the theft. He does it with shame \
and relief and it plays like a breakthrough: it explains the evasiveness, the \
keys, the lying, all of it. It is true. It is not the crime. Give your killer \
something real to surrender that is smaller than what they did.

*The decoy.* Tomas is the obvious suspect and is meant to be. He was publicly \
told his career here was over, he has money to hide, and he cannot account for \
himself. He is innocent.

Two things that made it feel alive at the table, and both are cheap. Every \
character had a *manner* that survived contact with a hostile question: one \
performed composure while it cost her, one answered exactly what was asked and \
nothing further, one talked too much and buried the useful sentence in the \
middle. And every character had an opinion about every other character, in their \
own voice, which meant a player could ask "what did you make of him" and get a \
person back rather than a timetable.\
"""


def fresh_seed() -> int:
    """A case nobody has seen, and a number that gets it back (D-102).

    `--seed` used to default to zero, which meant every run of the same command
    returned the same evening from the cache: the same six people, the same
    secrets, and, because casting is two bits of the seed, a man killing a man
    every single time. That looked like a biased generator and was a default
    argument.

    Random by default and printed loudly. Determinism was never the thing worth
    keeping; *reproducibility* was, and a seed you can read off the terminal and
    pass back is reproducible. Tests and the solver still pass explicit seeds.
    """
    return secrets.randbelow(1_000_000)


def _casting(seed: int) -> str:
    """Who is the killer and who is the victim, decided here rather than there.

    Left to a model, both came out men every time (D-074). This is not a
    quality judgement about any one case: it is that the same coin lands the
    same way on every seed, and the fix belongs in the one place that knows the
    seed. Two independent bits, so all four combinations happen.
    """
    killer = "a woman" if seed % 2 else "a man"
    victim = "a woman" if (seed // 2) % 2 else "a man"
    return (
        f"Casting, not negotiable: the killer is {killer} and the victim is "
        f"{victim}. Everything else about them is yours. The rest of the cast "
        f"must contain at least two women and at least two men."
    )


def _material(request: GenerationRequest) -> str:
    return draw_palette(
        request.seed, request.setting, request.topology, request.cast_size
    ).brief()


def _user_prompt(request: GenerationRequest) -> str:
    return (
        f"Setting: {request.setting}\n"
        f"Cast: {request.cast_size} suspects plus one victim.\n"
        f"Places: {request.place_count} distinct rooms or areas.\n"
        f"Time: {request.slot_count} consecutive slots.\n"
        f"SHAPE OF THE SOLUTION\n{get_topology(request.topology).brief}\n\n"
        f"{_casting(request.seed)}\n\n"
        f"{_material(request)}\n"
        f"Variation key {request.seed}: use it to take a different angle on this "
        f"setting than you otherwise would. Take it seriously at step 0: a "
        f"different occasion is what makes a different case, and the same place "
        f"on two different nights should not produce the same six people."
    )


def _tool_schema() -> dict[str, Any]:
    """The full Mystery schema, placements included.

    An earlier version stripped `placements` so the model could not touch the
    grid. That was wrong (D-029): the model is the only thing in the pipeline
    that knows *why* anyone is anywhere, and a grid without reasons reads as a
    random walk. It proposes; the solver repairs what breaks.
    """
    return Mystery.model_json_schema()


def anthropic_drafter(
    model: str = DRAFT_MODEL, api_key: str | None = None
) -> Drafter:
    """Build a Drafter backed by the Anthropic API.

    Imported lazily so that the rest of the package, and the whole test suite,
    works with the SDK absent and no key set.
    """
    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found. Put it in a .env file in the project "
            "root as ANTHROPIC_API_KEY=sk-ant-... , or set it in your shell."
        )

    client = anthropic.Anthropic(api_key=key)

    def draft(request: GenerationRequest, complaints: list[str]) -> dict[str, Any]:
        started = time.monotonic()

        content = _user_prompt(request)
        if complaints:
            problems = "\n".join(f"- {c}" for c in complaints)
            content += (
                f"\n\nYour previous attempt was rejected for these reasons:\n"
                f"{problems}\n\nProduce a corrected version. Fix exactly these "
                f"problems and change nothing else."
            )

        response = client.messages.create(
            model=model,
            # The prompt has roughly doubled since this was set, and so has what
            # it asks the model to write: a floor plan, a web of secrets, layers,
            # an investigator. Two drafts in one run came back at exactly 8000
            # output tokens, which is not a coincidence, it is the ceiling: the
            # JSON was cut off mid-object and arrived as "title: Field required"
            # (D-110). Headroom is cheap and a truncated draft costs a whole
            # attempt.
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
            tools=[
                {
                    "name": "emit_mystery",
                    "description": "Return the cast and the constraint set.",
                    "input_schema": _tool_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "emit_mystery"},
        )

        log.info(
            "mystery.drafted",
            model=model,
            attempt_had_complaints=len(complaints),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            usd=round(
                cost(model, response.usage.input_tokens, response.usage.output_tokens), 4
            ),
            seconds=round(time.monotonic() - started, 2),
            setting=request.setting,
        )

        # Truncation announces itself as a schema error three lines later, which
        # is the least useful place to meet it (D-110). Say it here, where the
        # number that proves it is in hand.
        if response.stop_reason == "max_tokens":
            log.warning(
                "mystery.truncated",
                output_tokens=response.usage.output_tokens,
                detail="the draft was cut off at the ceiling and cannot parse. "
                "Raise max_tokens rather than reading the schema errors below",
            )

        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input)

        raise RuntimeError("the model returned no tool call")

    return draft


def _unwrap(raw: dict[str, Any]) -> dict[str, Any]:
    """Undo a degenerate wrapper if the model produced one.

    Observed in the wild: the entire mystery returned under a single key called
    '$PARAMETER_NAME'. Rare, recoverable, and much cheaper to unwrap than to pay
    for another twenty five second call.
    """
    fields = set(Mystery.model_fields)
    if len(raw) == 1 and not (set(raw) & fields):
        inner = next(iter(raw.values()))
        if isinstance(inner, dict) and set(inner) & fields:
            log.warning("mystery.unwrapped", key=next(iter(raw)))
            return inner
    return raw


def generate(
    request: GenerationRequest,
    drafter: Drafter,
    cache_dir: Path | None = None,
    attempts: int = 3,
) -> Mystery:
    """Draft a mystery, retrying with the model's own failures fed back to it.

    Returns a Mystery with a proposed grid and bound constraints, ready for
    `solve`. Raises only when every attempt failed, and the exception carries
    what went wrong on the last one.

    Caching is deliberately after validation: a draft that could not be parsed or
    that named a character who does not exist is not worth keeping, and caching
    it would make the failure permanent for that seed.
    """
    from mystery.validator import validate

    if cache_dir is not None:
        cached = cache_dir / f"{request.cache_key()}.json"
        if cached.exists():
            log.info("mystery.cache_hit", key=request.cache_key())
            return Mystery.model_validate_json(cached.read_text(encoding="utf-8"))

    complaints: list[str] = []

    for attempt in range(1, attempts + 1):
        raw = _unwrap(drafter(request, complaints))

        try:
            mystery = Mystery.model_validate(raw)
        except ValidationError as error:
            complaints = [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in error.errors()[:8]
            ]
            log.warning("mystery.unparseable", attempt=attempt, problems=complaints)
            continue

        result = validate(mystery, phase="proposed")
        if result.ok:
            if cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                (cache_dir / f"{request.cache_key()}.json").write_text(
                    mystery.model_dump_json(indent=2), encoding="utf-8"
                )
            return mystery

        complaints = [v.message for v in result.violations]
        log.warning("mystery.rejected", attempt=attempt, problems=complaints)

    raise GenerationFailed(complaints)


class GenerationFailed(RuntimeError):
    def __init__(self, complaints: list[str]) -> None:
        self.complaints = complaints
        super().__init__(
            "The model could not produce a usable mystery. Last problems:\n"
            + "\n".join(f"  - {c}" for c in complaints)
        )
