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
import json
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

from mystery import measures
from mystery.models import Mystery
from mystery.palette import POSITIONS, commission, killer_position, murder_slot, world_for
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
    # Checked against the published price list on 2026-09-28 (D-171). Opus 5.5
    # is $4/$20 against Opus 5's $5/$25, so a draft is a fifth cheaper for the
    # same work. The older entries stay because drafts made on them are still on
    # the shelf and `--score` reads their logged cost.
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-5": (3.0, 15.0),
}

# What one draft actually costs, from the API's own token counts rather than from
# an estimate. Re-measured across four real drafts on 4 September (D-147): the
# prompt has grown again, and the previous figure was a character count divided
# by 3.8, which undercounted dense markdown by seventy per cent. Thirty five to
# forty one cents a draft, not twenty six. The estimate printed before a run is
# only honest if this is kept up to date with the prompt.
TYPICAL_DRAFT = (17900, 11500)


# Models known to reject `tool_choice={"type": "tool", ...}` (D-173).
#
# The whole model boundary is a forced tool call: the `Mystery` schema is handed
# over as a tool and the model is required to call it, so malformed output is
# rejected by the API before it reaches us (D-002). Opus 5.5 does not support
# that and returns a 400. Fable 5.1 and Mythos 5.1 are reported to do the same.
# They want `output_config.format` instead, which is a migration rather than a
# flag, because the streaming reply parser reads partial tool-call JSON.
#
# A deny list rather than an allow list, deliberately. What is known is which
# models refuse; treating every model not on a hand-written list as broken would
# block the next one that works and would be a claim nobody checked. Listed at
# all because the failure is a 400 in the middle of a paid batch, and the useful
# moment to find out is before the first call.
REJECTS_FORCED_TOOLS = frozenset(
    {
        "claude-opus-5-5",
        "claude-fable-5-1",
        "claude-mythos-5-1",
    }
)


def complaint_about_model(model: str) -> str | None:
    """Why this model cannot draft, or None if nothing is known against it."""
    if model not in REJECTS_FORCED_TOOLS:
        return None
    return (
        f"{model} does not support forced tool calls, which is how this pipeline "
        f"guarantees a valid case (D-173). Use --generator-model claude-opus-5, "
        f"or migrate the boundary to output_config.format."
    )


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


def in_its_world(mystery: Mystery, request: "GenerationRequest") -> Mystery:
    """Stamp which world the case was dealt, and who is coming there (D-182).

    From the deal, not from the draft: the model is told the world and writes in
    it, but whether a case is in Venice is a fact about the request, and the
    page needs it to say who is on the way.
    """
    dealt = world_for(request.seed, request.setting)
    # Always overwritten, including with nothing: whatever the draft put in
    # these two is not a deal, and a present-day case must say so.
    return mystery.model_copy(
        update={
            "world": dealt.key if dealt else "",
            "authority": dealt.authority if dealt else "",
            "killer_position": killer_position(request.seed),
        }
    )


def unname_the_commission(mystery: Mystery) -> Mystery:
    """Take the suspects' names back out of the briefing (D-149).

    D-139 said the opening screen must not name anybody, because a name there
    decides a five-suspect case before the first question. It said so as a
    validator rule, which was the wrong instrument: two drafts out of three came
    back naming somebody, each rejection cost a fresh Opus call, and the model
    kept doing it because the sentence it is asked to write ("they have already
    settled on one name") pulls the name in behind it.

    A rule that rejects is for a fault only the model can fix. This one has one
    right answer and no judgement in it, so it is repaired here instead, for
    nothing, the way the solver repairs a grid rather than sending it back
    (D-029). The validator rule stays as the guarantee.

    The victim is left alone: they are named on every other screen already.
    """
    original = (mystery.commission or "").strip()
    if not original:
        return mystery

    text = original
    # One stand-in per person, so a briefing that mentions somebody twice reads
    # as being about one person rather than two.
    spare = ["one of them", "another of them", "a third of them"]
    taken: dict[str, str] = {}

    # Whatever the victim is called stays on the page (D-167). Sixteen of
    # fifty six cases give a suspect the victim's surname, because a niece, a
    # nephew and a daughter are the most common things in this cast, and
    # replacing that surname rewrote the dead woman's own name in the first
    # sentence the player reads: "Doña Amalia one of them was found at the foot
    # of the river steps". The victim may be named; only the suspects may not.
    dead = next((c for c in mystery.characters if c.id == mystery.victim), None)
    theirs = {word for word in (dead.name.split() if dead else []) if len(word) > 2}

    for character in mystery.characters:
        if character.id == mystery.victim:
            continue
        parts = [word for word in character.name.split() if word not in theirs]
        if not parts:
            # Everything distinguishing about this name belongs to the victim
            # too. Taking it out would take the victim out with it, and leaving
            # it in names nobody the household would not already be thinking of.
            continue
        # Whole name first: replacing word by word turns "Devika Menon" into
        # "one of them that person", which is worse than the name was.
        forms = [character.name, *sorted(parts, key=len, reverse=True)]
        for form in forms:
            if len(form) <= 2:
                continue
            whose = re.compile(rf"\b{re.escape(form)}'s\b")
            plain = re.compile(rf"\b{re.escape(form)}\b")
            if not (whose.search(text) or plain.search(text)):
                continue
            if character.id not in taken:
                taken[character.id] = spare[min(len(taken), len(spare) - 1)]
            text = whose.sub("their", text)
            text = plain.sub(taken[character.id], text)

    text = re.sub(r"\s{2,}", " ", text).strip()
    # A name at the start of a sentence leaves a lower-case stand-in behind it.
    text = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)

    if text == original:
        return mystery
    log.info("mystery.commission_unnamed", named=len(taken))
    return mystery.model_copy(update={"commission": text})


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

The request names the numbers this case is measured on, under WHAT THE CASE IS \
MEASURED ON. They are checked against what you write, and a draft that misses \
one comes back. Everything below is how to write a case that meets them and is \
also worth playing, which no number can see.

Work in this order.

0. Before the cast, decide **what is happening tonight**. The setting names a \
place; it does not name an occasion, and a place with nothing happening in it \
produces the same evening every time. Something is at stake this evening and it \
would have been at stake even if nobody had died: money arrives or does not, a \
decision is announced, somebody is leaving, an inspection lands in the morning, \
a thing that has been put off for a year cannot be put off past tonight. Write \
that first and let the cast follow from it.

**Resist the obvious staffing.** Given a place, the same jobs come to mind every \
time: the owner, the deputy, the one who keeps the books, the loyal old hand, \
the young assistant, the outsider visiting. At least half this cast should be \
people that list would not have produced: somebody who does not work here, \
somebody who used to, somebody present for a reason unrelated to the business \
of the place, somebody whose connection to the victim is personal and old. The \
rooms go the same way. Do not reach for the obvious floor plan either.

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
authority. What kind of person that is, is dealt under MATERIAL FOR THIS CASE: \
work out who that is in *this* building and write them.

1. The cast. Each suspect wants something and each is concealing something. \
Only one of those secrets is the murder. A cast where three people have nothing \
to hide is three cooperative witnesses and one obvious liar, and there is no \
game.

For every character fill in `role`, `gender`, `look`, `wants`, `manner`, \
`voice`, `under_pressure`, and `impressions`.

`role` is one short public phrase: their job here and what they were to the \
victim. "The stage manager, twenty two years in this building." "His \
business partner." "The understudy." It is printed under their name before the \
player has asked anything, so it contains nothing they would hide, and it says \
what somebody is, never what they once did: **no dated events and no years**. \
Every other character repeats this line as background, so an event in it is a \
fact five people believe and the case does not contain. An old event that \
matters goes in `common_ground` or in a secret.

`wants` is the opposite: private, what they are actually after tonight. The \
player never sees it written down and has to work it out.

**Make it something tonight can still change, and something another person \
could imaginably help with or ruin.** The questioner will be told that what this \
person is trying to hold together is one of the ways into them: not the only \
one, and not a lock, but a road. That only works if the want is live. "To not be \
named tomorrow morning as the one who left the valve shut" is live, because the \
person asking will be talking to everybody and then to the police. "To have been \
a better painter" is not: nobody can offer anything against it. Vary how \
reachable they are. Somebody should want a specific thing that could physically \
be handed over, and somebody else should want something no outsider can touch at \
all, so that working out who can be dealt with is itself part of the case.

`gender` is "woman" or "man". `look` is one sentence: roughly how old, build, \
and how they are dressed this evening. Be concrete, and vary it. Not everyone \
is elegant and in their forties. Somebody is over sixty. Somebody is under \
twenty five.

`voice` is how their sentences are shaped, and it is the one thing a player is \
inside for the whole evening. The failure is one person in six costumes, every \
answer the same length and the same rhythm. Take the voice you are dealt and \
make it audible in the first line. Somebody should be short and flat, somebody \
should be tiring, somebody should not finish their sentences, and nobody should \
sound like a narrator.

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

**Do not turn every motive into an announcement.** Left alone, nearly every \
case becomes the same plot: the victim tells the killer, privately, minutes \
before dying, what they are about to do in the morning, and the killer removes \
the deadline. Audits, reports, wills, letters going out on Monday. So keep the \
register of what you were dealt. A motive about **what has already happened** \
does not need the victim to threaten anything: they can say something ordinary, \
or kind, or nothing at all, and the killer acts on years rather than on minutes. \
A motive about **love, jealousy, grief, shame, mercy or conviction** is not \
improved by attaching a document to it. If the dealt motive has no deadline in \
it, do not invent one.

**One thing stays true whatever the register.** The hour after can be hot, but \
it cannot be stupid: every shape needs the killer to have done something \
deliberate afterwards, whether that is a false account, a discovery story, or \
simply standing in the right room looking untroubled. Somebody can kill in a \
moment of rage and spend the next hour thinking clearly. What does not work is \
a killer who is still in pieces at the end of the evening, because there is \
then nothing for the player to take apart.

3. The secrets, and this is the step that decides whether the case is any good. \
The threads listed under MATERIAL FOR THIS CASE are what the innocent suspects \
are busy hiding: turn each one into a secret with a holder, and let them cross \
each other rather than running in parallel.

**The victim is the hub.** Do not give five suspects five unrelated subplots \
with one murder bolted on. At least half the suspects must be concealing \
something that involves the victim.

**Being the hub does not have to mean holding leverage.** A contract, a debt, a \
decision about someone's future: that is the obvious way, and taken every time \
it produces the same evening and the same cast, because a person with leverage \
is an employer and the people around them are staff. A victim can just as \
easily be the hub by being **loved**, by being the only one who knows what \
happened, by being the person everybody has been performing for since they were \
twenty, or by being the one thing four of these people still have in common. \
Read the occasion before deciding which. If nothing at this gathering is \
changing hands, do not invent a ledger so that it can.

**Who lies, how many of them, and what they lie about is decided by SHAPE OF \
THE SOLUTION in the request, not here.** Read the shape first and follow it \
exactly. Several shapes require the killer to tell no lie at all. Where anything \
below assumes a particular pattern of lying, the shape wins.

For every lie give the room and the slot they will claim, which must not be \
where they actually were, plus `covers` (the id of the secret the lie protects) \
and `admits_when` (what would make them drop it). Nobody lies about where they \
were for no reason, and the room they claim needs somebody in it who can say \
they were not there. The innocent lies are the good part: somebody was where \
they should not have been, with someone they should not have been with, going \
through papers that were not theirs. Being caught out is embarrassing rather \
than fatal, and that is exactly why they hold the line for a while.

**Give every innocent lie a way out.** The player must be able to resolve it, \
not merely detect it. Either somebody else knows the secret it covers, so it can \
be heard from a third party, or `admits_when` names a real condition under which \
they will come clean. A lie the player catches and can never get underneath \
teaches them that pressing does not pay, which is the opposite of the point.

**Mark the killer's motive.** The killer holds two secrets: the background that \
made them vulnerable, and the reason they killed. Set `is_motive` to true on the \
second one.

**Somebody else must half know why.** The killer will never say the reason they \
did it, so put at least one other character in the motive's `known_by`: someone \
who saw the argument, was told part of it, or worked out enough of it to repeat. \
The player is asked for the killer *and* the motive at the end, so the motive \
has to be findable.

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

**Entangle them with each other, not only with the dead man.** Asked for a \
victim who is a hub, the obvious move is to give every suspect a secret about \
the victim and stop. The player then questions each person, takes the one thing \
they had, and moves on, because nothing anybody said gave them a reason to go \
from this person to that one.

What a house of suspects should be is a web. The one who keeps the accounts is \
protecting the son. The son is covering for somebody's wife. She knows what the \
solicitor did. **At least three in ten of your secrets must be about another \
suspect**, and every suspect must be tied to at least one other, either by \
holding something about them or by being in somebody's `known_by`. If the player \
learns nothing that leads towards a person, that person is furniture. The old \
business dealt under MATERIAL FOR THIS CASE is the usual thread between them.

**The victim should have been working on all of them, tonight.** Not five old \
grievances: five things happening this evening. He was going to sign something \
away from one of them, had already told another they were finished, was about to \
be told something by a third. A case where five people were each being damaged \
in a different way over one evening produces its own suspects without being \
asked to.

**Build depth as an order of discovery, not as a lock on a box.** The first \
thing is something anybody would let slip. The second is what that first thing \
gives you leverage to ask about. The third is what somebody will only say once \
they know you already have the second. Think about the shape of an evening \
rather than a list of facts: what can be got in the first ten minutes, what is \
only worth asking after that, what nobody would say to a stranger who did not \
already half know it.

**Mark every secret that would put its holder on the list** with `damning: \
true`. Not "they were evasive" and not "they had a grievance": a reader who \
learned only this would write that name down. Money that dies with the victim, \
a threat somebody made out loud, a ruin the victim was about to cause them, a \
thing they were about to lose tonight. The killer's motive is damning by \
definition. Three people the player would genuinely put in the frame is the \
case; one person with a reason is a confirmation.

**The innocent chain has a floor that is not guilt.** Put one more secret \
behind the innocent's damning one, not damning itself, that explains it: what \
they were really doing, who they were protecting, why the thing that looks like \
a reason to kill is a reason to be ashamed instead. The player should be able to \
spend six questions becoming certain about the wrong person and then, on the \
seventh, have the whole structure turn over and still be interesting. A deep \
chain with no floor is not a red herring, it is a second murderer the case \
forgot to convict. Write the innocent chain first, before the killer's: it is \
the one you will otherwise leave until the end and make out of grievances.

**A secret that gates another one must be a thing, not just a fact.** Whenever \
you put `revealed_by` on a secret, the secret it points at has to carry \
`evidence`: the object that proves it and that the player can pick up and put \
in front of somebody. Producing that object is how the player opens the gate, \
and a gate with nothing behind it can only be argued at, which in practice \
means it never opens.

**Name it as an object, not as a conclusion.** A phrase somebody could read off \
a card in an evidence bag: what it physically is, plus the one detail that makes \
it damning. "A bundle of twelve letters in a ribbon, dated February to October" \
is right, and so is "A bone paperknife and a drawer of slit-and-regummed \
envelopes": you can see both, and neither tells you what it proves. "Proof that \
Margit read the post" is wrong, because it is the answer printed on the front of \
the question.

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

**After the killing, that room is empty** until the body is found: nobody goes \
back in and nobody has a scene there. Put the killer's return, the last check, \
the clearing up, anywhere else.

**`exclusive` is about the room, not the scene.** Nobody else is in that place \
at that moment, so two exclusive scenes cannot share a place and a slot. The \
overhearer is **not in the room**: put them in a different place for that slot, \
one they could plausibly hear from, and say in the prose that they heard it \
through a door or from the next room. And **a place is one room**: "the office \
and the corridor outside it" is two places, and you will need both precisely \
when somebody is standing in one listening to the other.

5. The grid. For every character and every slot, the place they were. Put it in \
`placements` as character id, then slot id, then place id. Fill in every cell, \
make every constraint hold in it, and give every constraint its `place` and \
`slot`.

This last step is yours, not a solver's. You are the only part of this system \
that knows *why* anyone is anywhere. Someone slips to the storeroom because of \
the affair; someone takes the critic outside because they want to know what he \
has found out. Place people for reasons, and use `description` on each \
constraint to say what the reason was.

**People stand still.** A gathering is not a corridor. Over five slots a \
suspect should move **once or twice at most**, and every move needs a reason you \
could name. Somebody who never leaves the main room all evening is a good \
character rather than a lazy one: their alibi is other people, and breaking it \
means breaking them. A cast that moves every slot reads as a random walk, which a \
player cannot reconstruct and therefore cannot use.

**How the two of them come to be alone is not always the killer's doing.** \
Left alone, nearly every case has the killer ask, take, bring or follow the \
victim somewhere, which makes every murder premeditated. Solitude has other \
sources and they are better. The victim goes somewhere alone every night of \
their life and everybody knows it. A room empties for two minutes and nobody \
planned that. The killer walks in on them and is not expecting to. The two of \
them were already together for an ordinary reason and it turned. Where the \
dealt motive is about something already done, an engineered meeting is the \
wrong scene: **somebody who has been carrying a thing for eleven years does not \
need a pretext, they need an opportunity.**

- **The victim does not have to own the place.** When the victim is always the \
proprietor, the cast writes itself as the people who work for them. A victim can \
be the youngest person here, or the one with no standing at all, or somebody's \
guest, and the case is more interesting when the person everybody has to talk \
about is not the person who was paying them.
- **The body is not found during the timeline.** The slots cover the evening up \
to and including the murder and its immediate aftermath. Discovery happens after \
the last slot, because everything the player investigates is what people were \
doing before anyone knew. Never write a constraint where someone finds the body.
- Name the killer and the victim in the `killer` and `victim` fields, and set \
`murder` to the id of the constraint where the killing happens. Two scenes between those \
two people are usually better than one, so that which of them is the murder \
cannot be guessed from the outside. Say which. **The earlier one does not have \
to be where the victim says the thing that gets them killed**: the killer may \
have learned it a week ago, or from somebody else in this building, or never \
have learned anything at all because the reason is old. Let the earlier scene be \
whatever those two people would actually have been doing.
- **The murder happens in the slot named under WHEN IT HAPPENS.** If that is not \
the last slot, the evening carries on around a room nobody goes into again, and \
the people who were with the victim earlier are the ones with something to \
explain. Write the rest of the evening as people who do not know yet.
- Fill in `discovery`: who found the body, in which room, and a sentence about \
how. This happened after the last slot and everybody knows it. Without it the \
suspects cannot discuss the death they are being questioned about.
- **Fill in `accounts`: what people say happened in the scenes they were in.**
Two or three scenes are enough. For each one, an account from **every person who
was there**, in their own voice, one or two sentences: what was said, who
started it, what it was about.

The point is that they do not all match. Mark `true` on the ones that are what
happened. For the rest, `honest` decides the kind of wrongness, and this is the
important field: **`honest: true` means the person is certain and simply wrong.**
Not lying, not covering, wrong: about who spoke first, what was actually said,
whether the door was open. With honest error in the room a contradiction
becomes a question instead of an accusation, and working out which of two
sincere people is misremembering is a different and better job than working
out who is lying.

**At least one false account must be honest rather than a lie.** `changes_when`
is what would move them: for a liar, what breaks them; for somebody honestly
mistaken, what would jog it, such as being shown a thing or being told who else
was there. They are relieved when it happens, not caught.

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
- Six to ten constraints.

Names belong to the setting. A gathering in Amsterdam has Dutch names, one in \
Naples has Italian ones. Reaching for the same handful of Anglo-thriller \
surnames every time is the fastest way to make every case feel like the last one.

Ids are short lowercase snake_case. Every id you reference must exist.

---

Here is one case that worked, abridged to its skeleton. It is here for the \
*shape*, not the content. Do not reuse the setting, the names, the theft, the \
transfers, or the lighting box. Build something that holds together the way \
this one does.

**Opening night at an Amsterdam theatre.** Rooms: green room, dressing \
corridor, prop store, lighting box, stage door, with a back passage from the \
stage door to the prop store. Slots: 19:40 half hour call, \
20:00 Act 1, 20:40 Act 1 continued, 21:00 interval, 21:20 Act 2. The murder is \
at the interval.

*The cast, and what each of them is sitting on.* Ilse, the lead, late forties, \
overheard the producer say she was finished after this run and has told nobody. \
Tomas, the director, has been inflating production costs and pocketing the \
difference. Nadia, the understudy, was promised the lead by the producer, who \
then went cold. Wouter, stage manager, twenty two years in this building, has \
been quietly selling theatre equipment. Renske, co-producer, found out her \
partner was moving money out of the company. Bram, the producer, is the victim, \
and the one thing all five have in common.

*The murder.* Wouter. At the half hour call Bram told him he had traced the \
missing equipment and would go to the police after the run. Wouter asked him to \
the prop store at the interval to show him where it all went, and killed him \
there.

*Three people with a reason and the chance.* Wouter. Tomas, told at 20:40 in \
front of the green room that this was his last production here, with money of \
his own to hide, alone in the green room through the interval. And Ilse, who \
says she spent the interval in the dressing corridor and was in fact alone at \
the stage door, on the phone to her agent finding out whether her part was \
already being recast. Each of the three would put a reader's pen on the page.

*Two lies about the murder hour, not one.* Wouter says he spent the interval \
in the dressing corridor, and so does Ilse. Nadia and Renske were both there and \
saw neither of them. A player who catches a lie about the interval has caught \
one of two people, and only one of them did it.

*The other liars.* Renske says she was in the green room at 20:40 and was in \
the lighting box going through Bram's files. Nadia says she was in the dressing \
corridor through Act 1 and was at the stage door with Bram, having it out about \
the promise. Neither killed anybody. A player who finds one of these and stops \
has accused the wrong person with complete confidence, which is the best \
feeling this game can produce.

*Two chains, and the innocent one is deeper.* Renske's transfer printouts open \
the killer's motive: she knew Bram had traced the thefts. The same printouts \
hold a deposit on an autumn contract for Nadia, which is what makes Nadia admit \
the promise and produce his card. The lead he promised her was Ilse's part, and \
only then does Ilse's reason come out. So following whatever goes deepest leads \
to Ilse, and Ilse's floor is a phone call, not a killing. Down the back passage \
she also heard two voices in the prop store, which she can only say once she \
admits where she was.

*The shield.* Pressed hard, Wouter confesses to the theft. He does it with shame \
and relief and it plays like a breakthrough: it explains the evasiveness, the \
keys, the lying, all of it. It is true. It is not the crime.

*The decoy.* Tomas looks like the answer and is meant to. He is innocent.

The shield and the decoy are one way to do it, not the pattern. A killer with \
nothing smaller to surrender, or a house with no obvious suspect at all, is just \
as good, and the position you are dealt for the killer says which this case is.

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
        f"must contain at least two women and at least two men.\n\n"
        f"**Where the killer stands in this house, also not negotiable:** "
        f"{POSITIONS[killer_position(seed)]}. Build the web of secrets so that it is "
        f"true; the killer has been every kind of person except this one too often."
    )


def _material(request: GenerationRequest) -> str:
    return draw_palette(
        request.seed, request.setting, request.topology, request.cast_size
    ).brief()


def _commission(request: GenerationRequest) -> str:
    """What the player was hired for, and whether it is the right question.

    A layer above topology (D-129): the shape says how the truth is hidden, this
    says what the evening is asking. Every case until now asked the same one.
    """
    brief, sound, wrong = commission(request.seed)
    if sound:
        turn = (
            "**This commission is sound.** What they asked you to find out is "
            "the thing that actually happened. The case is hard because the "
            "house is hard, not because the question was wrong."
        )
    else:
        turn = (
            f"**This commission is mistaken, and here is how:** {wrong}. Write "
            f"the case so that the commission is what any reasonable person in "
            f"this house believes, and so that it is wrong. Nobody is lying to "
            f"the player at the door: they are passing on what they think is "
            f"true. The player should be able to get all the way to the end on "
            f"the commission's terms and be wrong, and there must be a way to "
            f"find out before they do."
        )
    return (
        f"WHAT THEY ASKED YOU FOR\n"
        f"The player is told this before they ask anybody anything, and it goes "
        f"in `commission` in your own words, fitted to this house:\n"
        f"  {brief}.\n\n{turn}\n\n"
        f"**Name nobody in it.** The commission may say the household has "
        f"settled on somebody, that a confession has been made, that a doctor "
        f"has already called it an accident. It may not say who. A name in the "
        f"opening screen is an enormous prior on a house of five even when it is "
        f"the wrong one, and when it is the right one there is no case left. "
        f"Which name they have settled on is the first thing the player finds "
        f"out, not the first thing they are told. The victim may be named.\n\n"
        f"**And say nothing about who engaged the player or why they are in "
        f"this building.** That is decided above, under the standing, and the "
        f"two used to contradict each other because both were writing it "
        f"(D-169). The commission is only what the house has already decided "
        f"about the death and what it wants written down."
    )


def _when(request: GenerationRequest) -> str:
    """Which slot the killing happens in, decided here rather than there (D-125).

    Left to the model it was slot four ten times out of twelve and slot five the
    other two, because a story builds to its murder. That regularity is a rule of
    thumb that solves the game, since the killer necessarily lies about the hour
    they killed in.
    """
    n = murder_slot(request.seed, request.slot_count)
    where = {request.slot_count: "the last slot of the evening"}.get(
        n, f"slot {n} of {request.slot_count}, with the evening carrying on after it"
    )
    return (
        f"WHEN IT HAPPENS\n"
        f"The killing happens in **slot {n}**: {where}. Not negotiable, and not "
        f"wherever the story would rather put it. A murder that is always in the "
        f"last hour or two makes the whole case answerable by asking who lies "
        f"about the last hour or two.\n\n"
        f"**This is also the victim's whole life.** They are alive for slots 1 "
        f"to {n} and for no slot after that, so every constraint they appear in "
        f"has to sit in that window, and the murder is one of them. That leaves "
        f"**{n - 1} other {'hour' if n == 2 else 'hours'}** for everything else "
        f"they do tonight. Most scenes with the victim are private, which means "
        f"one per slot.\n\n"
        f"Count it before you write the grid. A case where the victim is wanted "
        f"in more scenes than they have hours is not a case that can be arranged, "
        f"and it gets thrown away. If the number is tight, they are in fewer and "
        f"busier scenes: one room, two people arriving in turn, three things "
        f"settled in the same half hour. What they were doing to the rest of them "
        f"belongs in the secrets, where it costs no time at all. Do not move a "
        f"scene later to make room, because later is after they are dead."
    )


def _gates(n: int) -> str:
    return "one gate" if n == 1 else f"{n} gates"


def _targets(shape: str = "", gate: dict[str, int] | None = None) -> str:
    """The numbers a draft is measured on, said the way they are measured (D-189).

    Built from the gate rather than written out, so the prompt and the check
    cannot drift apart: the old prose asked for "two other people with something
    damning" while the gate counted people with a reason *and* the chance. The
    shortcuts a shape hides from the player are left out, because they are not
    counted against it.
    """
    gate = gate if gate is not None else measures.GATE
    rules: list[str] = []
    if gate["field"]:
        rules.append(
            f"- **At least {gate['field']} suspects with a reason and the chance, the "
            f"killer among them.** A reason is a secret marked `damning`. The chance "
            f"is being alone at the murder hour, or lying about where they were at "
            f"that hour. Fewer, and the player confirms one theory instead of "
            f"choosing between several."
        )
    if gate["motive"]:
        rules.append(
            f"- **The killer's motive sits behind at least {_gates(gate['motive'])}:** "
            f"`revealed_by` on it names another character's secret, which must "
            f"surface first. Otherwise the obvious suspect is the answer."
        )
    if gate["trail"]:
        rules.append(
            f"- **One innocent's trail runs at least {_gates(gate['trail'])} deep, and "
            f"at least as deep as the motive:** a damning secret about somebody "
            f"innocent that {_gates(gate['trail'])} must open in turn, none of them "
            f"on the road to the motive. Otherwise whoever goes deepest is the killer, "
            f"and a player who follows that rule wins without solving anything."
        )
    if gate["liars_at_hour"]:
        rules.append(
            f"- **At least {gate['liars_at_hour']} people lie about where they were at "
            f"the murder hour.** If the shape says the killer tells no lie, they are "
            f"all innocent. A lone liar at that hour is the answer."
        )
    hidden = measures.HIDDEN_BY_SHAPE.get(shape, set())
    asked = [q for name, q in measures.SHORTCUTS.items() if name not in hidden]
    allowed = gate["shortcuts"]
    if allowed < len(asked):
        many = "None" if allowed == 0 else f"At most {allowed}"
        rules.append(
            f"- **{many} of these questions may name the killer and nobody else:** "
            + "; ".join(asked)
            + ". Each needs at least one innocent answer beside the killer, or "
            "it is a way to win without the case."
        )
    if not rules:
        return ""
    return (
        "WHAT THE CASE IS MEASURED ON\n"
        "Checked against what you write, not how you describe it. A draft that "
        "misses one is sent back with the number it missed.\n"
        + "\n".join(rules)
        + "\n\n"
    )


def _user_prompt(request: GenerationRequest) -> str:
    # The shape goes first, and says so (D-151). It used to sit on the fifth line
    # of the request, after the cast size, while the system prompt spent three
    # thousand characters insisting on a pattern of lying that several shapes
    # forbid. A case drew "the killer never lies" and wrote "the killer lies
    # about a room", which is what the loudest instruction asked for.
    return (
        f"SHAPE OF THE SOLUTION\n"
        f"This governs the case. Where anything in the standing instructions "
        f"assumes a different pattern of lying, of alibis or of who is "
        f"protecting what, this wins. Write the case this shape describes, not "
        f"the one the examples describe.\n\n"
        f"{get_topology(request.topology).brief}\n\n"
        f"{_targets(request.topology)}"
        f"Setting: {request.setting}\n"
        f"Cast: {request.cast_size} suspects plus one victim.\n"
        f"Places: {request.place_count} distinct rooms or areas.\n"
        f"Time: {request.slot_count} consecutive slots.\n"
        f"{_when(request)}\n\n"
        f"{_commission(request)}\n\n"
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

    Minus the fields `generate` stamps afterwards (D-182). A schema is an
    instruction: the first case drafted after `world` and `authority` existed
    came back with a paragraph about a snowbound road-house in `world` and a
    sentence about the gendarmerie in `authority`, because a field in the tool
    is a field the model believes it was asked to fill.
    """
    schema = Mystery.model_json_schema()
    for stamped in STAMPED:
        schema.get("properties", {}).pop(stamped, None)
        if stamped in schema.get("required", []):
            schema["required"].remove(stamped)
    return schema


# Written by `generate` after the draft, never by the model.
STAMPED = ("built_with", "world", "authority", "killer_position")


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

    refusal = complaint_about_model(model)
    if refusal:
        raise RuntimeError(refusal)

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

        # Streamed, and not for the user's benefit: nobody watches a draft
        # arrive. The SDK refuses a non-streaming request whose `max_tokens`
        # implies it could run past ten minutes, and raising the ceiling to
        # twenty-four thousand crossed that line (D-148). Streaming is the
        # SDK's own answer to it, and it removes the wall rather than moving it,
        # which matters because a draft already takes three minutes and this
        # prompt has only ever grown.
        with client.messages.stream(
            model=model,
            # The prompt has roughly doubled since this was set, and so has what
            # it asks the model to write: a floor plan, a web of secrets, layers,
            # an investigator. Two drafts in one run came back at exactly 8000
            # output tokens, which is not a coincidence, it is the ceiling: the
            # JSON was cut off mid-object and arrived as "title: Field required"
            # (D-110). Headroom is cheap and a truncated draft costs a whole
            # attempt.
            #
            # Raised again on 4 September (D-147). Real drafts now write ten to
            # thirteen thousand, so sixteen was 1.4x the typical one and the test
            # below said so. A ceiling only costs what is written against it.
            max_tokens=24000,
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
        ) as live:
            response = live.get_final_message()

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

    # So the draft can record which model wrote it (D-171). The prompt hash on
    # its own stopped being enough the moment there were two models to choose
    # between, and a corpus that cannot tell them apart is the D-166 problem
    # again in a different column.
    draft.model = model
    return draft


def prompt_version() -> str:
    """Which instructions are in force, as eight characters (D-166).

    Stamped on every draft so a corpus can be split by the prompt that made it.
    Without it every base rate is measured over drafts from several different
    sets of instructions at once, which is how a check that "fires on 97% of
    cases" turned out to be firing on drafts written before the instruction it
    was checking existed.
    """
    # The targets are instructions too, so a change to the gate is a new version.
    standing = SYSTEM_PROMPT + _targets(gate=measures.NORMAL)
    return hashlib.sha256(standing.encode("utf-8")).hexdigest()[:8]


def _stamp(drafter: "Drafter") -> str:
    """Prompt version and the model that drafted, as stamped on a case (D-166)."""
    wrote_it = getattr(drafter, "model", "")
    return prompt_version() + (f"/{wrote_it.removeprefix('claude-')}" if wrote_it else "")


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


def unbind_the_imaginary(mystery: Mystery) -> Mystery:
    """A scene set in a room that does not exist is an unbound scene (D-156).

    The model writes eight constraints without a map in front of it and
    occasionally sets one in a conservatory it invented two fields earlier. V4
    caught that and threw the draft away, which cost forty cents and a redraft.

    But it has exactly one right answer, which is the test D-149 asks. A
    constraint whose place does not exist is a constraint that does not know its
    place, and finding a place for a scene that does not know one is the
    solver's entire job. So drop the invented room, keep everything else, and
    the constraint goes into the pile the solver was already going to work
    through. Same for an invented slot.

    A constraint naming a **person** who is not in the cast is not repaired and
    never will be, because nobody can know who the model meant. That half of V4
    stays fatal.
    """
    places = {place.id for place in mystery.places}
    slots = {slot.id for slot in mystery.slots}

    freed: list[str] = []
    repaired = []
    for constraint in mystery.constraints:
        update: dict[str, None] = {}
        if constraint.place is not None and constraint.place not in places:
            update["place"] = None
        if constraint.slot is not None and constraint.slot not in slots:
            update["slot"] = None
        if update:
            freed.append(constraint.id)
            constraint = constraint.model_copy(update=update)
        repaired.append(constraint)

    if not freed:
        return mystery

    log.info("mystery.unbound_the_imaginary", scenes=freed)
    return mystery.model_copy(update={"constraints": repaired})


def _what_no_arrangement_fixes(mystery: Mystery, seed: int) -> list[str]:
    """What is still wrong after the free half of the pipeline has tried everything.

    Empty means there is an arrangement of this draft that satisfies the final
    rules, which is the only question worth asking about a draft.

    The proposed gate exists to stop a draft that cannot be saved. It was also
    stopping drafts the solver repairs on its own: V6, two scenes claiming the
    same person at the same hour, is precisely what `_resolve_clashes` unbinds
    and reschedules, and its own docstring claimed no repair existed. Measured
    over the corpus by manufacturing that exact clash in thirty-three drafts,
    the solver fixed thirty-two of them (D-156).

    So the question is not "does the draft satisfy the proposed rules" but "is
    there an arrangement of this draft that satisfies the final ones", and the
    final rules are strictly stronger. Solving is arithmetic and free; a
    redraft is forty cents. Ask the free question first.

    It runs on **every** draft, not only on ones the proposed gate complained
    about, and that is the half D-156 got wrong. A draft can pass the proposed
    rules and still have no valid arrangement at all: V7, nothing involving the
    victim after the murder, is only checked at the final gate, so a model that
    sat the dead man down to a communal meal an hour after killing him produced a
    draft that was cached, returned, and then failed all twenty-four
    arrangements in `web.py` with two paid attempts still unspent. Asking here
    turns that into a redraft (D-157).

    Same seed the caller will use, so what is proved here is what will happen
    there rather than something adjacent to it.
    """
    from mystery.solver import quietly, solve_until_valid

    # Quiet, because this is a question rather than the real solve. `web.py`
    # runs the same arrangement again afterwards and narrates it there, so
    # letting this one speak prints the whole evening twice (D-157).
    with quietly():
        _, _, violations = solve_until_valid(mystery, seed=seed)
    return [v.message for v in violations]


def _keep_the_wreckage(
    cache_dir: Path | None,
    request: GenerationRequest,
    attempt: int,
    raw: Any,
    complaints: list[str],
    built_with: str = "",
) -> None:
    """Write a rejected draft down instead of dropping it (D-156).

    Every measurement of this engine is taken over `var/mysteries`, which holds
    only the drafts that passed. That corpus structurally cannot answer what the
    gate rejects or how often, which is the number that decides whether a gate
    is paying for itself. One evening cost $1.20 for three rejected drafts and
    the only surviving record of them was a terminal window.

    Never fatal: a failed write here must not turn a bad draft into a crash.
    """
    if cache_dir is None:
        return
    try:
        folder = cache_dir.parent / "rejected"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{request.cache_key()}-{attempt}.json").write_text(
            json.dumps(
                {
                    "key": request.cache_key(),
                    "attempt": attempt,
                    "seed": request.seed,
                    "setting": request.setting,
                    "topology": request.topology,
                    "complaints": complaints,
                    # Which instructions wrote it, so a rejection rate can be
                    # split by prompt version like everything else (D-185).
                    "built_with": built_with or prompt_version(),
                    "draft": raw,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
    except OSError as error:  # noqa: BLE001 - keeping the wreckage is best effort
        log.warning("mystery.wreckage_unkept", error=str(error))


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

    inherited: list[str] = []
    if cache_dir is not None:
        cached = cache_dir / f"{request.cache_key()}.json"
        if cached.exists():
            log.info("mystery.cache_hit", key=request.cache_key())
            # Repaired on the way out as well as on the way in (D-149). Drafts
            # cached before the repair existed still have names in the briefing,
            # and a cached case is exactly the one nobody is going to pay to
            # draft again.
            kept = in_its_world(
                unbind_the_imaginary(
                    unname_the_commission(
                        Mystery.model_validate_json(cached.read_text(encoding="utf-8"))
                    )
                ),
                request,
            )
            # A cached draft that cannot be arranged is worse than a cache miss:
            # it is a seed that fails identically forever and never redrafts.
            # Drafts cached before D-157 include some of those. Say so and pay
            # for a new one rather than handing back a case nobody can play.
            broken = _what_no_arrangement_fixes(kept, request.seed)
            short = [] if broken else _below_the_bar(kept, request.topology)
            if not broken and not short:
                return kept
            log.warning(
                (
                    "mystery.cached_draft_unplayable"
                    if broken
                    else "mystery.cached_draft_below_the_bar"
                ),
                key=request.cache_key(),
                problems=broken or short,
                detail="redrafting rather than returning a case that cannot be solved",
            )
            # The first redraft is told why, the same as any other rejection.
            inherited = broken or short

    complaints: list[str] = inherited
    # The draft that came closest while failing only on quality (D-188).
    nearest: tuple[Mystery, list[str]] | None = None

    for attempt in range(1, attempts + 1):
        raw = _unwrap(drafter(request, complaints))

        try:
            # Repaired before it is judged (D-149): a name in the briefing has
            # one right answer and no judgement in it, so it costs nothing here
            # and a fresh Opus call if it goes back to the model.
            mystery = unbind_the_imaginary(unname_the_commission(Mystery.model_validate(raw)))
            mystery = in_its_world(
                mystery.model_copy(update={"built_with": _stamp(drafter)}),
                request,
            )
        except ValidationError as error:
            complaints = [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                for e in error.errors()[:8]
            ]
            log.warning("mystery.unparseable", attempt=attempt, problems=complaints)
            _keep_the_wreckage(cache_dir, request, attempt, raw, complaints, _stamp(drafter))
            continue

        result = validate(mystery, phase="proposed")
        # Kept apart because only one of the two is worth a free second opinion.
        # The solver rearranges a grid; it cannot reach a secret nothing unlocks,
        # so an unwinnable case goes straight back to the model.
        unwinnable = _unreachable(mystery)

        if unwinnable:
            complaints = [v.message for v in result.violations] + unwinnable
        else:
            # The question that actually matters, asked of every draft: is there
            # an arrangement of this one that satisfies the final rules? A draft
            # is accepted on that and nothing else (D-157).
            broken = _what_no_arrangement_fixes(mystery, request.seed)
            if not broken and result.violations:
                log.info(
                    "mystery.repaired_by_solving",
                    attempt=attempt,
                    rules=sorted({v.rule for v in result.violations}),
                    saved_usd=0.38,
                )
            elif broken and not result.violations:
                log.warning("mystery.no_arrangement_works", attempt=attempt, problems=broken)
            seen = [v.message for v in result.violations]
            complaints = seen + [b for b in broken if b not in seen] if broken else []

        if not complaints:
            # Solvable is not the same as worth playing (D-184). These were
            # advisories, printed after the case was already on the shelf.
            complaints = _below_the_bar(mystery, request.topology)
            if complaints:
                if nearest is None or len(complaints) < len(nearest[1]):
                    nearest = (mystery, complaints)
                log.warning("mystery.below_the_bar", attempt=attempt, problems=complaints)

        if not complaints:
            if cache_dir is not None:
                cache_dir.mkdir(parents=True, exist_ok=True)
                (cache_dir / f"{request.cache_key()}.json").write_text(
                    mystery.model_dump_json(indent=2), encoding="utf-8"
                )
            return mystery

        log.warning("mystery.rejected", attempt=attempt, problems=complaints)
        _keep_the_wreckage(cache_dir, request, attempt, raw, complaints, _stamp(drafter))

    if nearest is not None:
        _keep_for_review(cache_dir, request, *nearest)
    raise GenerationFailed(complaints)


def _below_the_bar(mystery: Mystery, shape: str = "") -> list[str]:
    """What a draft must reach, not merely be told about (D-184, D-188).

    The four numbers from D-186 against Normal, plus A26. Each number that
    falls short sends its own sentence back, so the redraft knows what to fix:
    a working shortcut, a field under three, an innocent trail under two gates,
    a lone liar at the murder hour.

    A24 is gone from here. It was relative ("an innocent trail as deep as the
    motive") and the model met it by making the motive shallower (D-186). The
    floors cannot be met by shrinking anything, and "whose trail is deepest" is
    still caught, as a shortcut.

    A26, the evidence is in its holder's hands, stays: cheap to satisfy, fatal
    when it is not.
    """
    from mystery.critique import the_evidence_is_in_the_holders_hands
    from mystery.measures import complaints, measure

    return complaints(measure(mystery, shape)) + [
        advisory.message for advisory in the_evidence_is_in_the_holders_hands(mystery)
    ]


def _keep_for_review(
    cache_dir: Path | None, request: "GenerationRequest", mystery: Mystery, short: list[str]
) -> None:
    """The closest miss, kept when every attempt fell short only on quality (D-188).

    Three drafts that are each playable and each one number short were all
    thrown away, at forty cents a draft. The best of them goes to
    `var/review` with what it missed, to be read and shelved by hand or not.
    """
    if cache_dir is None:
        return
    try:
        folder = cache_dir.parent / "review"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{request.cache_key()}.json").write_text(
            json.dumps(
                {
                    "seed": request.seed,
                    "setting": request.setting,
                    "topology": request.topology,
                    "short": short,
                    "mystery": mystery.model_dump(mode="json"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        log.warning("mystery.kept_for_review", key=request.cache_key(), short=len(short))
    except OSError as error:  # noqa: BLE001 - best effort
        log.warning("mystery.review_unkept", error=str(error))


def _unreachable(mystery: Mystery) -> list[str]:
    """Reasons this case could never be won, said in time to be fixed (D-149).

    The solvability analysis has always been advisory, on the argument that it
    is a necessary condition rather than a sufficient one and a rule built on
    that would eventually throw away a good case. Which is right about most of
    it, and was wrong about this part, because the program already treats these
    as fatal: it prints "This case cannot be solved" and refuses to serve.

    So the case was being thrown away regardless, after every draft had been
    paid for, for a reason the model was never told. A real run ended that way:
    three drafts, a dollar ten, and the third one died because the killer's
    motive was known to nobody but the killer.

    Only the parts that are pure structure and that the solver cannot change:
    which secrets can be reached through the `revealed_by` chain. Whether the
    killer's alibi can be broken depends on the grid, and the grid is the
    solver's to repair, so that stays out of here.
    """
    from mystery.solvable import why_not

    return [
        advisory.message
        for advisory in why_not(mystery)
        if advisory.check in ("S2", "S3", "S4")
    ]


class GenerationFailed(RuntimeError):
    def __init__(self, complaints: list[str]) -> None:
        self.complaints = complaints
        super().__init__(
            "The model could not produce a usable mystery. Last problems:\n"
            + "\n".join(f"  - {c}" for c in complaints)
        )
