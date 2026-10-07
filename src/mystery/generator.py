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
import random
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from mystery import measures
from mystery.models import Mystery
from mystery.palette import (
    LIES,
    OBJECT_ROLES,
    POSITIONS,
    body_moved,
    commission,
    earlier_lie,
    innocent_lies,
    killer_position,
    murder_slot,
    object_hand,
    scene_object,
    world_for,
)
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
            "moved_body": body_moved(request.seed, request.topology),
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


SKELETON_PROMPT = """\
You design murder mysteries that are solvable but not obvious. This is the \
first of two stages. Here you build the **skeleton**: who these people are to \
each other, what happened, who is hiding what, which secret opens which, who \
lies, and where everybody was. A second stage writes the voices, the manners \
and the scenes on top of it, and cannot change anything you decide here.

The skeleton is everything a case is judged on. The request names the numbers \
it is measured on, under WHAT THE CASE IS MEASURED ON, and they are checked \
against what you write before anybody writes a line of dialogue. A skeleton \
that misses one comes back to you with your own previous version, so you can \
mend it rather than start again.

Material under MATERIAL FOR THIS CASE that is about how people sound and \
behave (manners, voices, the title, the questioner's standing) is for the \
second stage. Read it, because it tells you who these people are, but do not \
write it now. WHAT THEY ASKED YOU FOR is written there too, and what it asks \
has to be what actually happened in the case you build.

Work in this order.

0. **The premise first.** Write `premise`: one paragraph, plain and complete, \
of what happened in this place and why. Who killed whom, for what, how the \
others are tangled in it, what each innocent is really hiding and why it looks \
worse than it is. This is the story the structure has to tell, and the second \
stage writes from it. Nobody else ever reads it, so hide nothing in it.

Before the cast, decide **what is happening tonight**. The setting names a \
place; it does not name an occasion, and a place with nothing happening in it \
produces the same evening every time. Something is at stake this evening and it \
would have been at stake even if nobody had died: money arrives or does not, a \
decision is announced, somebody is leaving, an inspection lands in the morning, \
a thing that has been put off for a year cannot be put off past tonight.

**Resist the obvious staffing.** Given a place, the same jobs come to mind every \
time: the owner, the deputy, the one who keeps the books, the loyal old hand, \
the young assistant, the outsider visiting. At least half this cast should be \
people that list would not have produced: somebody who does not work here, \
somebody who used to, somebody present for a reason unrelated to the business \
of the place, somebody whose connection to the victim is personal and old. The \
rooms go the same way. Do not reach for the obvious floor plan either.

**The player always arrives after the body has been found.** They did not see \
it happen and have no observation of their own from before the discovery. \
Never build the case around something the questioner personally witnessed.

1. The cast. `characters` is everybody, **the victim included**: every suspect \
and then the victim, one entry each, with `id`, `name`, `role` and `gender` \
("woman" or "man"). Each suspect wants something and each is concealing \
something. Only one of those secrets is the murder.

`role` is one short public phrase: their job here and what they were to the \
victim. "The stage manager, twenty two years in this building." "His business \
partner." It is printed under their name before the player has asked anything, \
so it contains nothing they would hide, and it says what somebody is, never \
what they once did: **no dated events and no years**. An old event that matters \
goes in a secret.

Names belong to the setting. A gathering in Amsterdam has Dutch names, one in \
Naples has Italian ones. Reaching for the same handful of Anglo-thriller \
surnames every time is the fastest way to make every case feel like the last one.

2. The murder. Who, whom, how, and above all why. The motive comes with the \
case, under MATERIAL FOR THIS CASE, as a situation rather than a plot: make it \
specific to these people, and make it come out of what the killer is \
concealing.

**Do not turn every motive into an announcement.** Left alone, nearly every \
case becomes the same plot: the victim tells the killer, privately, minutes \
before dying, what they are about to do in the morning, and the killer removes \
the deadline. So keep the register of what you were dealt. A motive about \
**what has already happened** does not need the victim to threaten anything, \
and the killer acts on years rather than on minutes. A motive about **love, \
jealousy, grief, shame, mercy or conviction** is not improved by attaching a \
document to it. If the dealt motive has no deadline in it, do not invent one.

**One thing stays true whatever the register.** The hour after can be hot, but \
it cannot be stupid: every shape needs the killer to have done something \
deliberate afterwards, whether that is a false account, a discovery story, or \
simply standing in the right room looking untroubled. A killer still in pieces \
at the end of the evening leaves the player nothing to take apart.

3. The secrets, and this is the step that decides whether the case is any good. \
The threads listed under MATERIAL FOR THIS CASE are what the innocent suspects \
are busy hiding: turn each one into a secret with a holder, and let them cross \
each other rather than running in parallel.

**The victim is the hub.** At least half the suspects must be concealing \
something that involves the victim. **Being the hub does not have to mean \
holding leverage.** Taken every time, leverage produces the same evening, \
because a person with leverage is an employer and the people around them are \
staff. A victim can just as easily be the hub by being **loved**, by being the \
only one who knows what happened, by being the person everybody has been \
performing for, or by being the one thing four of these people still have in \
common. If nothing at this gathering is changing hands, do not invent a ledger.

**Who lies, how many of them, and what they lie about is decided by SHAPE OF \
THE SOLUTION in the request, not here.** Read the shape first and follow it \
exactly. Several shapes require the killer to tell no lie at all. Where anything \
below assumes a particular pattern of lying, the shape wins.

For every lie give the room and the slot they will claim, which must not be \
where they actually were, and `covers`: the id of the secret the lie protects. \
Nobody lies about where they were for no reason, and the room they claim needs \
somebody in it who can say they were not there. The innocent lies are the good \
part, and the kinds they come in are dealt in the request: being caught out is \
embarrassing rather than fatal, which is why they hold the line. Give every \
innocent lie a way out: somebody else in the `known_by` of the secret it covers, \
or a condition the second stage can write for them to come clean.

**Mark the killer's motive.** The killer holds two secrets: the background that \
made them vulnerable, and the reason they killed. Set `is_motive` to true on the \
second one. **Somebody else must half know why:** put at least one other \
character in the motive's `known_by`. The killer never says it, and the player \
is asked for the motive at the end.

**Entangle them with each other, not only with the dead man.** What a house of \
suspects should be is a web. The one who keeps the accounts is protecting the \
son. The son is covering for somebody's wife. She knows what the solicitor did. \
**At least three in ten of your secrets must be about another suspect**, and \
every suspect must be tied to at least one other, by holding something about \
them or by being in somebody's `known_by`. The old business dealt under \
MATERIAL FOR THIS CASE is the usual thread between them. **The victim should \
have been working on all of them, tonight**: five things happening this evening, \
not five old grievances.

**Ages and the old business are numbers.** Give every person, the victim too, \
an `age`. Somebody is over sixty; somebody is under twenty five. Put the old \
business dealt under MATERIAL FOR THIS CASE in `history`: `what` happened, \
exactly how many `years_ago`, and who of the people here was there \
(`present`), each with `age_then` (their `age` now minus the years, to the \
year), `stage` (child up to twelve, youth thirteen to nineteen, adult from \
sixteen; it must fit `age_then`), `role` (what they were there, in a few \
words) and `known: false` if the house does not know they were there. The \
questioner may be there too, as `"investigator"`. Anybody not in `present` \
was not there. A number of people never stands in for their names: if the \
story says "four of us", the four are in `present`.

**Build depth as an order of discovery, not as a lock on a box.** The first \
thing is something anybody would let slip. The second is what that first thing \
gives you leverage to ask about. The third is what somebody will only say once \
they know you already have the second.

**Mark every secret that would put its holder on the list** with `damning: \
true`. Not "they were evasive" and not "they had a grievance": a reader who \
learned only this would write that name down. The killer's motive is damning by \
definition. Three people the player would genuinely put in the frame is the \
case; one person with a reason is a confirmation.

**The innocent chain has a floor that is not guilt.** Put one more secret \
behind the innocent's damning one, not damning itself, that explains it: what \
they were really doing, who they were protecting, why the thing that looks like \
a reason to kill is a reason to be ashamed instead. A deep chain with no floor \
is a second murderer the case forgot to convict. Build the innocent chain \
first, before the killer's.

**The gates that matter most open with a thing, not a fact.** When the secret \
named in `revealed_by` carries `evidence`, the player opens the gate by putting \
that object in front of somebody; without it they can only argue. The targets \
say how many, and which roads must have one. **Name it as an object, not as a \
conclusion**: "a bundle of twelve letters in a ribbon, dated February to \
October", not "proof that Margit read \
the post". Everything else can be `evidence`-free; most secrets are things \
people know, not things kept in a drawer.

**And say why the gate opens.** On every secret with `revealed_by`, write \
`how_it_opens`: one sentence on why having the first thing makes this one come \
out. "Shown the transfer printouts, Nadia sees the deposit he put down for her \
and stops pretending there was no promise." A gate with no reason behind it is \
a lock nobody can find the key to, and the second stage writes each holder's \
breaking point from this sentence.

Put all of this in `secrets`, with `holder`, `about`, `summary` (one plain \
sentence of what it is), `known_by`, `revealed_by`, `how_it_opens`, `evidence`, \
`is_motive` and `damning`.

4. The constraints: the things that must be true of the evening. A constraint \
names people who share a place at a moment, with a `description` that says why \
they were there. Mark it `exclusive` when they must be alone. You need, at \
minimum:
   - the killer and the victim alone together
   - at least two other suspects with a private moment of their own, so a \
missing alibi proves nothing on its own
   - one exchange overheard by exactly one person who was not part of it

**Give the building a floor plan.** Every place lists `adjacent`: the other \
places you can walk to, or hear through a wall, directly from it. Doors, not \
routes. Make it a plan somebody could walk through, and put the overhearer next \
door to whatever they overhear. You only have to write each door once.

**After the killing, that room is empty** until the body is found. **`exclusive` \
is about the room, not the scene**: two exclusive scenes cannot share a place \
and a slot. The overhearer is **not in the room** they overhear. And **a place \
is one room**: "the office and the corridor outside it" is two places.

5. The grid. For every character and every slot, the place they were, in \
`placements` as character id, then slot id, then place id. Fill in every cell, \
make every constraint hold in it, and give every constraint its `place` and \
`slot`. You are the only part of this system that knows *why* anyone is \
anywhere, so place people for reasons.

**People stand still.** Over five slots a suspect should move **once or twice \
at most**, and every move needs a reason you could name. Somebody who never \
leaves the main room is a good character: their alibi is other people.

**How the two of them come to be alone is not always the killer's doing.** \
Left alone, nearly every case has the killer ask, take, bring or follow the \
victim somewhere, which makes every murder premeditated. The victim goes \
somewhere alone every night of their life and everybody knows it. A room \
empties for two minutes and nobody planned that. The two of them were already \
together for an ordinary reason and it turned. **Somebody who has been carrying \
a thing for eleven years does not need a pretext, they need an opportunity.**

- **The victim does not have to own the place.** A victim can be the youngest \
person here, or the one with no standing at all, or somebody's guest.
- **The body is not found during the timeline.** Discovery happens after the \
last slot. Never write a constraint where someone finds the body.
- Name the killer and the victim in `killer` and `victim`, and set `murder` to \
the id of the constraint where the killing happens. Two scenes between those \
two are usually better than one. **The earlier one does not have to be where \
the victim says the thing that gets them killed.**
- **The murder happens in the slot named under WHEN IT HAPPENS.** The rest of \
the evening carries on around a room nobody goes into again.
- Fill in `discovery`: who found the body, in which room, and a sentence about \
how, after the last slot.
- `things` are objects whose whereabouts matter, with where each one is in each \
slot, and the `role` each was dealt under THE OBJECTS. A secret's `evidence` is \
something its holder could actually produce. Objects help a player build the \
picture and open secrets, and no object names the killer on its own: object, \
then a fact, then testimony, then a person.

Design rules:

**Every character must be load-bearing.** Each suspect must be at least two of: \
someone who can contradict the killer's story, someone whose secret gates \
another, someone who knows a secret that is not theirs, or the holder of the \
motive. The killer's alibi must be breakable by combining at least two people's \
testimony, and by no single person's alone. Six to ten constraints. Ids are \
short lowercase snake_case, and every id you reference must exist.

---

Here is one case that worked, abridged to its skeleton. It is here for the \
*shape*, not the content. Do not reuse the setting, the names, the theft, the \
transfers, or the lighting box.

**Opening night at an Amsterdam theatre.** Rooms: green room, dressing \
corridor, prop store, lighting box, stage door, with a back passage from the \
stage door to the prop store. Slots: 19:40 half hour call, 20:00 Act 1, 20:40 \
Act 1 continued, 21:00 interval, 21:20 Act 2. The murder is at the interval.

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
already being recast.

*Two lies about the murder hour, not one.* Wouter says he spent the interval \
in the dressing corridor, and so does Ilse. Nadia and Renske were both there and \
saw neither of them. A player who catches a lie about the interval has caught \
one of two people, and only one of them did it.

*The other liars.* Renske says she was in the green room at 20:40 and was in \
the lighting box going through Bram's files. Nadia says she was in the dressing \
corridor through Act 1 and was at the stage door with Bram, having it out about \
the promise. Neither killed anybody.

*Two chains, and the innocent one is deeper.* Renske's transfer printouts open \
the killer's motive: she knew Bram had traced the thefts. The same printouts \
hold a deposit on an autumn contract for Nadia, which is what makes Nadia admit \
the promise and produce his card. The lead he promised her was Ilse's part, and \
only then does Ilse's reason come out. So following whatever goes deepest leads \
to Ilse, and Ilse's floor is a phone call, not a killing. Down the back passage \
she also heard two voices in the prop store, which she can only say once she \
admits where she was.

*The shield.* Pressed hard, Wouter confesses to the theft. It is true. It is \
not the crime. *The decoy.* Tomas looks like the answer and is meant to. He is \
innocent. The shield and the decoy are one way to do it, not the pattern: a \
killer with nothing smaller to surrender, or a house with no obvious suspect at \
all, is just as good, and the position you are dealt for the killer says which \
this case is.\
"""

PROSE_PROMPT = """\
You write the people in a murder mystery whose structure is already fixed. \
This is the second of two stages. The first built the skeleton, which you are \
given as THE CASE, ALREADY DECIDED: who these people are, what happened, who is \
hiding what, which secret opens which, who lies, where everybody was. It has \
passed every check and it is final. You add what a player spends the evening \
inside: how people sound, what they want, what breaks them, what they say \
happened.

**You cannot change the skeleton, so do not try.** Write only the fields in your \
tool, keyed by the ids the skeleton uses. Anything that contradicts it, a \
person in a room the grid does not put them in, a secret somebody does not \
hold, is a mistake the player will catch. Read `premise` first: it is the story \
the structure tells, and everything you write has to be true to it.

Use what is dealt under MATERIAL FOR THIS CASE for this stage: the manners, the \
voices, the title form and the questioner's standing.

**The player always arrives after the body has been found.** Everything they \
know, they were told.

**`title`** takes the form dealt under MATERIAL FOR THIS CASE.

**`investigator`** is the person the player is tonight: `name` (the name the \
household calls them by, the same one the premise uses), `role` (what they are, \
in a few words), `why_here` (the reason they were in this building before \
anybody died, or arrived within the hour), and `standing` (what they can and \
cannot do). They are **never police**: they cannot arrest, charge or compel \
anybody. What kind of person that is, is dealt: work out who that is in *this* \
building. Whatever the dealt standing, **not an insurer's assessor or adjuster**: \
left alone, every other case comes back with one.

**If the killer tells two lies**, the earlier one's `admits_when` says what \
brings them to own up to being there, and that they do it with something \
true about another person's secret, which points away from them. The lie \
about the murder hour is never admitted.

**`commission`** is what the player is told before the first question, as the \
request describes under WHAT THEY ASKED YOU FOR.

**For every suspect** (`characters`, by id): `look`, `wants`, `manner`, \
`voice`, `under_pressure` and `impressions`. For the victim, `look` only.

`look` is one sentence that opens with their `age` from the skeleton, in \
words ("Sixty-one, long and stooped…"), then build, and how they are dressed \
this evening. Be concrete, and vary it.

`wants` is private: what they are actually after tonight. **Make it something \
tonight can still change, and something another person could imaginably help \
with or ruin.** The questioner will be told that what this person is trying to \
hold together is one of the ways into them, which only works if the want is \
live. "To not be named tomorrow morning as the one who left the valve shut" is \
live. "To have been a better painter" is not. Vary how reachable they are: \
somebody should want a thing that could physically be handed over, and \
somebody else something no outsider can touch at all.

`voice` is how their sentences are shaped, and it is the one thing a player is \
inside for the whole evening. The failure is one person in six costumes, every \
answer the same length and the same rhythm. Take the voice you are dealt and \
make it audible in the first line. Somebody should be short and flat, somebody \
should be tiring, somebody should not finish their sentences, and nobody should \
sound like a narrator.

`manner` and `under_pressure` are how they behave when questioned. The manners \
are dealt, one per suspect: decide who gets which, decide what it looks like in \
*this* person, and write it in your own words. A manner should change what \
somebody actually says when pressed, not sit in a field being true.

`impressions` maps each *other* character's id to what this person thinks of \
them, in a sentence, in their voice: the victim and at least two others. This \
is what makes them worth talking to.

**For every secret** (`secrets`, by id): `breaks_when`, the condition under \
which its holder stops concealing it. Where the skeleton says `how_it_opens`, \
the breaking point grows out of that sentence. The conditions should differ \
from person to person. **Write it as a state of affairs, not as a stage \
direction.** "Once she believes somebody else has read the letters" is a \
condition. "Shown the letters and asked, without preamble, who resealed them" is \
a script, and a script gets played as a password: the player does the right \
thing in the wrong words and nothing happens. Describe what this person's \
resistance is made of and what dissolves it. The killer's own motive gets no \
breaking point that involves being shown anything: they never give it up, and \
it reaches the player through somebody else.

**For every lie** (`lies`, by character and slot): `admits_when`, what would \
make them drop it, written the same way. An innocent who is caught should have \
a road out: being caught out is embarrassing rather than fatal, and that is \
why they hold the line for a while.

**`accounts`: what people say happened in the scenes they were in.** Two or \
three scenes are enough, by the skeleton's constraint ids. For each one, an \
account from **every person who was there**, in their own voice, one or two \
sentences: what was said, who started it, what it was about. The point is that \
they do not all match. Mark `true` on the ones that are what happened. For the \
rest, **`honest: true` means the person is certain and simply wrong**, about who \
spoke first, what was said, whether the door was open. With honest error in the \
room a contradiction becomes a question instead of an accusation. **At least one \
false account must be honest rather than a lie.** `changes_when` is what would \
move them; they are relieved when it happens, not caught.

**`common_ground`**: four to six plain sentences that everybody in the building \
would say the same way. What the gathering is, what happens in the morning, how \
long people have been here, who pays for it. **Every number that matters goes \
here and nowhere else**, because each suspect is forbidden to invent a figure \
that is not in it. Write no secret here: this is only what is said out loud at \
breakfast. When the old business in `history` comes up, name who was there \
(only the `known` ones) and how old they were, never a count instead of names.

Two things make a case feel alive at the table, and both are cheap. Every \
character has a manner that survives contact with a hostile question. And every \
character has an opinion about every other character, in their own voice, so \
that "what did you make of him" gets a person back rather than a timetable.\
"""

# Two stages since D-191: the skeleton, gated on everything, then the prose on
# top of a skeleton that has passed. The single-call path in `generate` is kept
# for fakes and `--dry-run`, which hand back a whole case at once; it is never
# sent to a model any more, and gets both prompts so its cache key moves with
# either of them.
SYSTEM_PROMPT = SKELETON_PROMPT + "\n\n---\n\n" + PROSE_PROMPT


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
    if gate.get("objects"):
        rules.append(
            f"- **At least {gate['objects']}% of the gates open with an object**, and at "
            f"least one on the road to the killer's motive and one on the deepest "
            f"innocent trail. A gate opens with an object when the secret named in "
            f"`revealed_by` carries `evidence`. Not every secret needs one, but a "
            f"case the player can only argue open is a case of talk."
        )
    if gate.get("other_lies"):
        rules.append(
            f"- **At least {gate['other_lies']} lie is about an hour other than the "
            f"murder's**, before it or after it: a visit, an errand, what somebody "
            f"did once it was over. Lies that all sit on the murder hour make that "
            f"hour the whole puzzle."
        )
    if gate.get("window"):
        rules.append(
            f"- **When the victim died is a window, not an hour.** By what people "
            f"first say, she could have died in at least {gate['window']} hours: the "
            f"last hour anybody admits being with her, to the murder, and the hours "
            f"after it in which nobody admits going into the room she is found in. "
            f"`discovery.summary` and `commission` say when she was last seen and "
            f"when found, never the hour of death as a fact."
        )
    if gate.get("hidden_visits"):
        rules.append(
            f"- **At least {gate['hidden_visits']} innocent was with her inside that "
            f"window and says they were elsewhere**, for a secret of their own: a "
            f"debt, an argument, an affair, a favour asked. A hidden visit. Each one "
            f"that comes out moves \"last seen alive\" later, so narrowing the hour "
            f"is progress the player earns."
        )
    if gate.get("movers"):
        rules.append(
            f"- **No object names the killer.** If the killer could have moved a "
            f"thing out of a room, at least {gate['movers']} people must have had the "
            f"chance: everybody in that room between the last time somebody else saw "
            f"it there and the hour it was gone. An object narrows the field or "
            f"confirms a fact; it never points at one person."
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


def _shape(request: GenerationRequest) -> str:
    """The shape's paragraph. For the open experiment, its examples in an order
    of the seed's, so the first one listed is not the one always picked (D-192)."""
    brief = get_topology(request.topology).brief
    if request.topology != "open":
        return brief
    lines = brief.split("\n")
    at = [i for i, line in enumerate(lines) if line.startswith("- ")]
    shuffled = random.Random(f"open|{request.seed}").sample([lines[i] for i in at], len(at))
    for i, line in zip(at, shuffled, strict=True):
        lines[i] = line
    return "\n".join(lines)


def _body(request: GenerationRequest) -> str:
    """Where the body is found, dealt (D-193)."""
    if not body_moved(request.seed, request.topology):
        return (
            "**The body is found where it fell**: `discovery.place` is the room of the "
            "murder scene.\n\n"
        )
    return (
        "**The body was moved, and that is dealt too.** The killing happens in one "
        "room; in the same hour the killer carries the body through one door into "
        "the room next to it, and that is where it is found. Set `discovery.place` "
        "to that room, adjacent to the murder scene's room. Nobody else is in it "
        "from that hour on. The move leaves something behind that somebody can come "
        "across (a trace, a sound through a wall, an object out of place), so put it "
        "in a secret: where it really happened is a thing the player can establish, "
        "and the room the body was found in is a thing they will be told.\n\n"
    )


def _lies(request: GenerationRequest) -> str:
    """How the innocents lie, dealt (D-192). Not for the conspiracy, where every
    innocent is inside the one shared lie by definition."""
    if request.topology == "the_conspiracy":
        return ""
    hand = "\n".join(f"  {n}. {LIES[k]}" for n, k in enumerate(innocent_lies(request.seed), 1))
    return (
        f"**How the innocents lie, also dealt.** Take these in order, one kind per "
        f"innocent lie, and never use the same kind twice. Most cases use the first "
        f"two or three:\n{hand}\n\n"
    )


_EARLIER_LIE = (
    "**The killer also lies about an earlier hour, and that is dealt.** Two "
    "`false_claims` for the killer: the one the shape asks for, and one about "
    "an hour before the murder, covering the preparation (fetching what they "
    "used, reading what gave them the reason, a word with the victim), a "
    "secret of the killer's named in `covers`. That "
    "earlier hour is not an empty one: in the room the killer was really in, "
    "at most one other person, an innocent busy with a secret of their own, "
    "whose residue or carried object is there. Opening that innocent's "
    "secret gives the player a witness against the killer's earlier lie. "
    "Put the killer in the `known_by` of a secret an innocent holds: when "
    "the earlier lie breaks, the killer owns up to being there and, in the "
    "same breath, says something true about that secret, which points away.\n\n"
)


def _earlier(request: GenerationRequest) -> str:
    """The killer's earlier lie, when dealt (D-207)."""
    if not earlier_lie(request.seed, request.topology):
        return ""
    return _EARLIER_LIE


def _objects(request: GenerationRequest) -> str:
    """The roles the objects play, and what lies with the body, dealt (D-203)."""
    held = object_hand(request.seed)
    hand = "\n".join(f"  {n}. `{k}`, {OBJECT_ROLES[k]}" for n, k in enumerate(held, 1))
    scene = scene_object(request.seed)
    with_body = (
        "**Nothing** lies in the room of the finding at the last hour: no object's "
        "`where` puts it there then."
        if scene == "nothing"
        else f"The `{scene}` object lies in the room of the finding at the last hour, "
        f"and is the first thing the player is told about (\"found with the body\")."
    )
    return (
        f"**THE OBJECTS, dealt.** Write exactly {len(held)} `things`, one for each "
        f"of these roles, and set its `role` to the name in backticks:\n{hand}\n"
        f"{with_body}\n\n"
    )


def _user_prompt(request: GenerationRequest, targets: bool = True) -> str:
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
        f"{_shape(request)}\n\n"
        f"{_targets(request.topology) if targets else ''}"
        f"Setting: {request.setting}\n"
        f"Cast: {request.cast_size} suspects plus one victim, so "
        f"{request.cast_size + 1} entries in `characters`.\n"
        f"Places: {request.place_count} distinct rooms or areas.\n"
        f"Time: {request.slot_count} consecutive slots.\n"
        f"{_when(request)}\n\n"
        f"{_commission(request)}\n\n"
        f"{_casting(request.seed)}\n\n"
        f"{_lies(request)}"
        f"{_body(request)}"
        f"{_earlier(request)}"
        f"{_objects(request)}"
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
STAMPED = (
    "built_with", "world", "authority", "killer_position", "spent_usd", "moved_body",
    "language",
)


# What each stage writes (D-191). Everything a gate reads is in the skeleton;
# the prose stage gets these fields and nothing else, keyed by the skeleton's
# ids, and code puts them on. So a gate passed by the skeleton cannot be undone
# by the prose.
PROSE_TOP = ("title", "investigator", "commission", "common_ground", "accounts")
PROSE_CHARACTER = ("look", "wants", "manner", "voice", "under_pressure", "impressions")

# Attempts per stage. A skeleton is about a third of a draft, so the tries go
# there; prose only fails on something missing, and is mended, not rewritten.
SKELETON_ATTEMPTS = 4
PROSE_ATTEMPTS = 2


@dataclass
class Staged:
    """A drafter in two calls (D-191).

    `skeleton(request, complaints, previous)` returns the structure;
    `prose(request, skeleton, complaints, previous)` returns the prose fields
    for a skeleton that passed. `previous` is what that stage wrote last time,
    so a revision mends it rather than starting blind (B). `last_usd` is what
    the most recent call cost, for the record kept of every draft.
    """

    skeleton: Callable[[GenerationRequest, list[str], dict[str, Any] | None], dict[str, Any]]
    prose: Callable[
        [GenerationRequest, dict[str, Any], list[str], dict[str, Any] | None], dict[str, Any]
    ]
    model: str = ""
    last_usd: float = 0.0


def _skeleton_schema() -> dict[str, Any]:
    """The Mystery schema minus everything the prose stage writes, premise first."""
    schema = _tool_schema()
    props = schema["properties"]
    for name in PROSE_TOP:
        props.pop(name, None)
    defs = schema["$defs"]
    for name in PROSE_CHARACTER:
        defs["Character"]["properties"].pop(name, None)
    defs["Secret"]["properties"].pop("breaks_when", None)
    defs["FalseClaim"]["properties"].pop("admits_when", None)
    for unused in ("Investigator", "Account"):
        defs.pop(unused, None)
    # A number for everybody, and the old business as a roster (D-201).
    character = defs["Character"]
    character["required"] = [*character.get("required", []), "age"]
    # Generated in schema order, so the story comes before the structure.
    schema["properties"] = {"premise": props.pop("premise"), **props}
    schema["required"] = [
        "premise", "killer", "victim", "murder", "characters", "places", "slots",
        "placements", "constraints", "secrets", "false_claims", "discovery",
        "history",
    ]
    return schema


def _prose_schema() -> dict[str, Any]:
    """Only the prose, keyed by the skeleton's ids."""
    defs = Mystery.model_json_schema()["$defs"]
    text = {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "title": text,
            "investigator": {"$ref": "#/$defs/Investigator"},
            "commission": text,
            "common_ground": {"type": "array", "items": text},
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": text,
                        **{name: text for name in PROSE_CHARACTER if name != "impressions"},
                        "impressions": {"type": "object", "additionalProperties": text},
                    },
                    "required": ["id"],
                },
            },
            "secrets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": text, "breaks_when": text},
                    "required": ["id", "breaks_when"],
                },
            },
            "lies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"character": text, "slot": text, "admits_when": text},
                    "required": ["character", "slot", "admits_when"],
                },
            },
            "accounts": {"type": "array", "items": {"$ref": "#/$defs/Account"}},
        },
        "required": [
            "title", "investigator", "commission", "common_ground",
            "characters", "secrets", "lies", "accounts",
        ],
        "$defs": {"Investigator": defs["Investigator"], "Account": defs["Account"]},
    }


def _bare(mystery: Mystery) -> dict[str, Any]:
    """The skeleton of a case: everything but the prose and the stamps."""
    data = mystery.model_dump(mode="json", exclude={*PROSE_TOP, *STAMPED})
    for character in data["characters"]:
        for name in PROSE_CHARACTER:
            character.pop(name, None)
    for secret in data["secrets"]:
        secret.pop("breaks_when", None)
    for claim in data["false_claims"]:
        claim.pop("admits_when", None)
    # The story first, the way it was written and the way it should be read.
    return {"premise": data.pop("premise", ""), **data}


def _dress(skeleton: Mystery, prose: dict[str, Any]) -> Mystery:
    """Put the prose on the skeleton, by id, touching nothing structural."""
    data = skeleton.model_dump(mode="json")
    for name in PROSE_TOP:
        if name in prose:
            data[name] = prose[name]
    people = {c.get("id"): c for c in prose.get("characters") or [] if isinstance(c, dict)}
    for character in data["characters"]:
        written = people.get(character["id"], {})
        for name in PROSE_CHARACTER:
            if name in written:
                character[name] = written[name]
    breaks = {s.get("id"): s for s in prose.get("secrets") or [] if isinstance(s, dict)}
    for secret in data["secrets"]:
        if secret["id"] in breaks:
            secret["breaks_when"] = breaks[secret["id"]].get("breaks_when", "")
    lies = {
        (lie.get("character"), lie.get("slot")): lie
        for lie in prose.get("lies") or []
        if isinstance(lie, dict)
    }
    for claim in data["false_claims"]:
        written = lies.get((claim["character"], claim["slot"]))
        if written:
            claim["admits_when"] = written.get("admits_when", "")
    return Mystery.model_validate(data)


def _says_age(character) -> bool:
    """Whether the `look` sentence states the skeleton's age (D-201)."""
    from mystery.models import age_words

    look = character.look.lower()
    return any(re.search(rf"\b{re.escape(w)}\b", look) for w in age_words(character.age))


def _prose_gaps(mystery: Mystery) -> list[str]:
    """What the prose left unwritten. The only things a prose draft can fail on."""
    gaps: list[str] = []
    for name in ("title", "commission"):
        if not str(getattr(mystery, name) or "").strip():
            gaps.append(f"`{name}` is empty")
    if mystery.investigator is None or not mystery.investigator.role.strip():
        gaps.append("`investigator` is missing or has no `role`")
    if not mystery.common_ground:
        gaps.append("`common_ground` is empty")
    for character in mystery.characters:
        if character.id == mystery.victim:
            if not character.look.strip():
                gaps.append(f"the victim {character.id!r} has no `look`")
            elif character.age is not None and not _says_age(character):
                gaps.append(
                    f"the victim {character.id!r} is {character.age} in the skeleton, "
                    f"and `look` does not say so: open it with the age, in words"
                )
            continue
        missing = [n for n in PROSE_CHARACTER if not getattr(character, n)]
        if character.age is not None and character.look and not _says_age(character):
            gaps.append(
                f"{character.id!r} is {character.age} in the skeleton, and `look` "
                f"does not say so: open it with the age, in words"
            )
        if missing:
            gaps.append(f"{character.id!r} has no {', '.join(f'`{n}`' for n in missing)}")
    gaps += [f"secret {s.id!r} has no `breaks_when`" for s in mystery.secrets if not s.breaks_when]
    gaps += [
        f"the lie by {c.character!r} at {c.slot!r} has no `admits_when`"
        for c in mystery.false_claims
        if not c.admits_when
    ]
    scenes = {c.id for c in mystery.constraints}
    people = {c.id for c in mystery.characters}
    gaps += [
        f"an account is of {a.constraint!r}, which is not a scene in the case"
        for a in mystery.accounts
        if a.constraint not in scenes
    ]
    gaps += [
        f"an account is by {a.character!r}, who is not in the case"
        for a in mystery.accounts
        if a.character not in people
    ]
    if not mystery.accounts:
        gaps.append("`accounts` is empty")
    return gaps


def _holding(mystery: Mystery | None, shape: str) -> str:
    """The numbers a draft already meets, so a revision keeps them met (B)."""
    if mystery is None:
        return ""
    try:
        m = measures.measure(mystery, shape)
    except Exception:  # noqa: BLE001 - a draft too broken to measure says nothing here
        return ""
    gate = measures.GATE
    held = []
    if gate["field"] and m.field >= gate["field"] and m.killer_in_field:
        held.append(f"{m.field} suspects with a reason and the chance")
    if gate["motive"] and m.motive >= gate["motive"]:
        held.append(f"the motive behind {_gates(m.motive)}")
    if gate["trail"] and m.trail >= gate["trail"]:
        held.append(f"an innocent trail {_gates(m.trail)} deep")
    if gate["liars_at_hour"] and m.liars_at_hour >= gate["liars_at_hour"]:
        held.append(f"{m.liars_at_hour} liars at the murder hour")
    if len(m.shortcuts) <= gate["shortcuts"]:
        held.append("no question that names the killer alone")
    if gate.get("objects") and m.gates and m.objects_met(gate):
        held.append(f"{m.gates - m.argued} of {m.gates} gates opened by an object")
    if not held:
        return ""
    return "Already met, and a revision must keep them met: " + "; ".join(held) + "."


def _revision(previous: dict[str, Any], complaints: list[str], holding: str, what: str) -> str:
    problems = "\n".join(f"- {c}" for c in complaints)
    return (
        f"\n\nYOUR PREVIOUS {what.upper()}\n```json\n"
        f"{json.dumps(previous, ensure_ascii=False, indent=1)}\n```\n\n"
        f"It was sent back for these reasons:\n{problems}\n\n"
        + (f"{holding}\n\n" if holding else "")
        + f"Revise it rather than starting again. Keep what works, change what "
        f"these need, and check that the change does not break anything that was "
        f"passing. Return the whole {what}, not only the changes."
    )


def anthropic_drafter(
    model: str = DRAFT_MODEL, api_key: str | None = None
) -> Staged:
    """Build a two-stage drafter backed by the Anthropic API (D-191).

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

    def call(
        stage: str, system: str, content: str, tool: str, schema: dict[str, Any], tries: int
    ) -> dict[str, Any]:
        started = time.monotonic()
        # Streamed, and not for the user's benefit: nobody watches a draft
        # arrive. The SDK refuses a non-streaming request whose `max_tokens`
        # implies it could run past ten minutes (D-148).
        with client.messages.stream(
            model=model,
            # One ceiling for both stages. Truncation arrives as a schema error
            # three lines later (D-110), and a ceiling only costs what is
            # written against it (D-147).
            max_tokens=24000,
            # The standing instructions are the same on every attempt at a
            # seed, so they are cached: a revision reads them at a tenth of the
            # price (D-191).
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
            tools=[{"name": tool, "description": f"Return the {stage}.", "input_schema": schema}],
            tool_choice={"type": "tool", "name": tool},
        ) as live:
            response = live.get_final_message()

        usage = response.usage
        written = getattr(usage, "cache_creation_input_tokens", 0) or 0
        read = getattr(usage, "cache_read_input_tokens", 0) or 0
        rate_in = RATES.get(model, (0.0, 0.0))[0]
        usd = cost(model, usage.input_tokens, usage.output_tokens) + (
            written * 1.25 + read * 0.1
        ) * rate_in / 1_000_000
        staged.last_usd = usd
        log.info(
            "mystery.drafted",
            stage=stage,
            model=model,
            attempt_had_complaints=tries,
            input_tokens=usage.input_tokens + written + read,
            output_tokens=usage.output_tokens,
            usd=round(usd, 4),
            seconds=round(time.monotonic() - started, 2),
        )
        if response.stop_reason == "max_tokens":
            log.warning(
                "mystery.truncated",
                stage=stage,
                output_tokens=usage.output_tokens,
                detail="cut off at the ceiling and cannot parse. Raise max_tokens "
                "rather than reading the schema errors below",
            )
        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input)
        raise RuntimeError("the model returned no tool call")

    def skeleton(
        request: GenerationRequest, complaints: list[str], previous: dict[str, Any] | None
    ) -> dict[str, Any]:
        content = _user_prompt(request)
        if complaints and previous is not None:
            shape = request.topology
            try:
                drafted = Mystery.model_validate({"title": "", **previous})
            except ValidationError:
                drafted = None
            content += _revision(previous, complaints, _holding(drafted, shape), "skeleton")
        elif complaints:
            content += "\n\nA previous attempt was sent back for these reasons:\n" + "\n".join(
                f"- {c}" for c in complaints
            )
        return call("skeleton", SKELETON_PROMPT, content, "emit_skeleton",
                    _skeleton_schema(), len(complaints))

    def prose(
        request: GenerationRequest,
        bones: dict[str, Any],
        complaints: list[str],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        # Without the targets: the skeleton already met them, and the prose
        # cannot move a single one.
        content = (
            _user_prompt(request, targets=False)
            + "\n\nTHE CASE, ALREADY DECIDED\n```json\n"
            + json.dumps(bones, ensure_ascii=False, indent=1)
            + "\n```"
        )
        if complaints and previous is not None:
            content += _revision(previous, complaints, "", "prose")
        return call("prose", PROSE_PROMPT, content, "emit_prose", _prose_schema(),
                    len(complaints))

    staged = Staged(skeleton=skeleton, prose=prose, model=model)
    return staged


def prompt_version() -> str:
    """Which instructions are in force, as eight characters (D-166).

    Stamped on every draft so a corpus can be split by the prompt that made it.
    Without it every base rate is measured over drafts from several different
    sets of instructions at once, which is how a check that "fires on 97% of
    cases" turned out to be firing on drafts written before the instruction it
    was checking existed.
    """
    # The targets are instructions too, so a change to the gate is a new version,
    # and so are the shapes and the decks that only reach the request (D-192):
    # D-188's decks changed what the model was told without changing this.
    from mystery.topology import LIBRARY as SHAPES

    standing = (
        SYSTEM_PROMPT
        + _targets(gate=measures.NORMAL)
        + "".join(SHAPES[k].brief for k in sorted(SHAPES))
        + "".join(LIES[k] for k in sorted(LIES))
        + "".join(POSITIONS[k] for k in sorted(POSITIONS))
        + "".join(OBJECT_ROLES[k] for k in sorted(OBJECT_ROLES))
        + _EARLIER_LIE
    )
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
    stage: str = "",
    usd: float | None = None,
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
        name = f"{request.cache_key()}-{stage + '-' if stage else ''}{attempt}.json"
        (folder / name).write_text(
            json.dumps(
                {
                    "key": request.cache_key(),
                    "attempt": attempt,
                    # Which half of a two-stage draft, and what the call cost
                    # (D-191). A skeleton is a third the price of a whole draft,
                    # so `--stats` can no longer assume one figure for all.
                    "stage": stage or "whole",
                    "usd": usd,
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


def _from_the_cache(
    request: GenerationRequest, cache_dir: Path | None
) -> tuple[Mystery | None, list[str], Mystery | None]:
    """A cached case that still passes, or why it does not and what it was."""
    if cache_dir is None:
        return None, [], None
    cached = cache_dir / f"{request.cache_key()}.json"
    if not cached.exists():
        return None, [], None
    log.info("mystery.cache_hit", key=request.cache_key())
    # Repaired on the way out as well as on the way in (D-149). Drafts cached
    # before the repair existed still have names in the briefing, and a cached
    # case is exactly the one nobody is going to pay to draft again.
    kept = in_its_world(
        unbind_the_imaginary(
            unname_the_commission(Mystery.model_validate_json(cached.read_text(encoding="utf-8")))
        ),
        request,
    )
    # A cached draft that cannot be arranged is worse than a cache miss: it is a
    # seed that fails identically forever and never redrafts (D-157).
    broken = _what_no_arrangement_fixes(kept, request.seed)
    short = [] if broken else _below_the_bar(kept, request.topology)
    if not broken and not short:
        return kept, [], None
    log.warning(
        "mystery.cached_draft_unplayable" if broken else "mystery.cached_draft_below_the_bar",
        key=request.cache_key(),
        problems=broken or short,
        detail="redrafting rather than returning a case that cannot be solved",
    )
    # The first redraft is told why, the same as any other rejection.
    return None, broken or short, kept


def _judge(
    raw: dict[str, Any], request: GenerationRequest, built_with: str, attempt: int
) -> tuple[Mystery | None, list[str], bool]:
    """Everything a draft is held to: the case, what is wrong, and whether only
    quality is wrong (so it is a near miss worth keeping)."""
    from mystery.validator import validate

    try:
        # Repaired before it is judged (D-149): a name in the briefing has one
        # right answer and no judgement in it, so it costs nothing here and a
        # fresh call if it goes back to the model.
        mystery = unbind_the_imaginary(unname_the_commission(Mystery.model_validate(raw)))
        mystery = in_its_world(mystery.model_copy(update={"built_with": built_with}), request)
    except ValidationError as error:
        complaints = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:8]
        ]
        log.warning("mystery.unparseable", attempt=attempt, problems=complaints)
        return None, complaints, False

    result = validate(mystery, phase="proposed")
    # Kept apart because only one of the two is worth a free second opinion.
    # The solver rearranges a grid; it cannot reach a secret nothing unlocks, so
    # an unwinnable case goes straight back to the model.
    unwinnable = _unreachable(mystery)
    if unwinnable:
        return mystery, [v.message for v in result.violations] + unwinnable, False

    # The question that actually matters, asked of every draft: is there an
    # arrangement of this one that satisfies the final rules (D-157)?
    broken = _what_no_arrangement_fixes(mystery, request.seed)
    if not broken and result.violations:
        log.info(
            "mystery.repaired_by_solving",
            attempt=attempt,
            rules=sorted({v.rule for v in result.violations}),
        )
    elif broken and not result.violations:
        log.warning("mystery.no_arrangement_works", attempt=attempt, problems=broken)
    if broken:
        seen = [v.message for v in result.violations]
        return mystery, seen + [b for b in broken if b not in seen], False

    # Solvable is not the same as worth playing (D-184).
    short = _below_the_bar(mystery, request.topology)
    if short:
        log.warning("mystery.below_the_bar", attempt=attempt, problems=short)
    return mystery, short, bool(short)


def _cache(cache_dir: Path | None, request: GenerationRequest, mystery: Mystery) -> None:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{request.cache_key()}.json").write_text(
            mystery.model_dump_json(indent=2), encoding="utf-8"
        )


def generate(
    request: GenerationRequest,
    drafter: "Drafter | Staged",
    cache_dir: Path | None = None,
    attempts: int = 3,
) -> Mystery:
    """Draft a mystery, retrying with the model's own failures fed back to it.

    Returns a Mystery with a proposed grid and bound constraints, ready for
    `solve`. Raises only when every attempt failed, and the exception carries
    what went wrong on the last one.

    A `Staged` drafter (the real one, D-191) builds a skeleton, gates it, and
    only then pays for the prose. A plain function is the single-call path that
    fakes and `--dry-run` use: it hands back a whole case at once.

    Caching is deliberately after validation: a draft that could not be parsed or
    that named a character who does not exist is not worth keeping, and caching
    it would make the failure permanent for that seed.
    """
    kept, inherited, stale = _from_the_cache(request, cache_dir)
    if kept is not None:
        return kept
    if isinstance(drafter, Staged):
        return _in_two_stages(request, drafter, cache_dir, inherited, stale)

    complaints: list[str] = inherited
    # The draft that came closest while failing only on quality (D-188).
    nearest: tuple[Mystery, list[str]] | None = None

    for attempt in range(1, attempts + 1):
        raw = _unwrap(drafter(request, complaints))
        mystery, complaints, quality_only = _judge(raw, request, _stamp(drafter), attempt)
        if mystery is not None and not complaints:
            _cache(cache_dir, request, mystery)
            return mystery
        if quality_only and (nearest is None or len(complaints) < len(nearest[1])):
            nearest = (mystery, complaints)
        if mystery is not None:
            log.warning("mystery.rejected", attempt=attempt, problems=complaints)
        _keep_the_wreckage(cache_dir, request, attempt, raw, complaints, _stamp(drafter))

    if nearest is not None:
        _keep_for_review(cache_dir, request, *nearest)
    raise GenerationFailed(complaints)


def _in_two_stages(
    request: GenerationRequest,
    drafter: Staged,
    cache_dir: Path | None,
    inherited: list[str],
    stale: Mystery | None,
) -> Mystery:
    """Skeleton until one passes every gate, then prose on top of it (D-191).

    Each stage revises its own previous attempt rather than starting blind (B):
    the redraft used to be told "change nothing else" about a draft it was never
    shown, so every attempt was a fresh roll that fixed one number and broke
    another.
    """
    built_with = _stamp(drafter)
    complaints = inherited
    previous: dict[str, Any] | None = _bare(stale) if stale is not None else None
    nearest: tuple[Mystery, list[str]] | None = None
    bones: Mystery | None = None
    bones_usd = 0.0
    # A skeleton whose only fault is soft (D-202): an object that names the
    # killer. Sent back while there are drafts left; kept if none fixes it.
    softly: tuple[Mystery, float, int] | None = None

    for attempt in range(1, SKELETON_ATTEMPTS + 1):
        raw = _unwrap(drafter.skeleton(request, complaints, previous))
        # The prose stage's fields have no business here, and an `investigator`
        # written as a sentence failed three drafts in one batch (D-204).
        raw = {k: v for k, v in raw.items() if k not in PROSE_TOP}
        previous = raw
        mystery, complaints, quality_only = _judge(
            {"title": "", **raw}, request, built_with, attempt
        )
        if mystery is not None and complaints:
            # Said from the first draft, beside the hard ones (D-206): checked only
            # once everything else passed, they arrived on the last draft or
            # after it, and no case in a batch ever fixed one.
            complaints = complaints + [c for c in _soft(mystery, request) if c not in complaints]
        if mystery is not None and not complaints:
            soft = _soft(mystery, request)
            if not soft:
                bones, bones_usd = mystery, drafter.last_usd
                log.info("mystery.skeleton_passed", attempt=attempt)
                break
            if softly is None or len(soft) <= softly[2]:
                softly = (mystery, drafter.last_usd, len(soft))
            complaints = soft
            log.warning("mystery.soft", stage="skeleton", attempt=attempt, problems=soft)
            continue
        if quality_only and (nearest is None or len(complaints) < len(nearest[1])):
            nearest = (mystery, complaints)
        log.warning("mystery.rejected", stage="skeleton", attempt=attempt, problems=complaints)
        _keep_the_wreckage(
            cache_dir, request, attempt, raw, complaints, built_with, "skeleton", drafter.last_usd
        )

    if bones is None and softly is not None:
        bones, bones_usd = softly[0], softly[1]
        log.warning("mystery.kept_soft", objects_naming_the_killer=softly[2])
    if bones is None:
        if nearest is not None:
            _keep_for_review(cache_dir, request, *nearest, stage="skeleton")
        raise GenerationFailed(complaints)

    complaints = []
    previous = None
    spent = bones_usd
    for attempt in range(1, PROSE_ATTEMPTS + 1):
        raw = drafter.prose(request, _bare(bones), complaints, previous)
        previous = raw
        try:
            dressed = in_its_world(unname_the_commission(_dress(bones, raw)), request)
        except ValidationError as error:
            complaints = [
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()[:8]
            ]
            dressed = None
        else:
            complaints = _prose_gaps(dressed)
            if not complaints:
                # The prose cannot move the structure, so this should never
                # fire. It is checked anyway: a case is shelved on the full
                # rules, not on an argument that they still hold.
                _, broke, _ = _judge(dressed.model_dump(mode="json"), request, built_with, attempt)
                complaints = [f"the prose broke the case: {c}" for c in broke]
        if not complaints and dressed is not None:
            spent += drafter.last_usd
            done = dressed.model_copy(
                update={"built_with": built_with, "spent_usd": round(spent, 4)}
            )
            _cache(cache_dir, request, done)
            return done
        log.warning("mystery.rejected", stage="prose", attempt=attempt, problems=complaints)
        _keep_the_wreckage(
            cache_dir, request, attempt, raw, complaints, built_with, "prose", drafter.last_usd
        )

    # A skeleton that passed everything is the expensive half of a case. Kept,
    # so the prose can be written again later rather than the whole thing.
    _keep_for_review(cache_dir, request, bones, complaints, stage="skeleton")
    raise GenerationFailed(complaints)


def _soft(mystery: Mystery, request: GenerationRequest) -> list[str]:
    """Everything a draft is sent back for but never thrown away for (D-206)."""
    try:
        m = measures.measure(mystery, request.topology or "")
    except Exception:  # noqa: BLE001 - a draft too broken to measure is judged elsewhere
        return []
    return (
        measures.soft_complaints(mystery, m)
        + _object_complaints(mystery, request)
        + _earlier_complaints(mystery, request)
    )


def _earlier_complaints(mystery: Mystery, request: GenerationRequest) -> list[str]:
    """The killer's earlier lie, when dealt, is there and costs the killer little
    sight (D-207). Soft, like the other dealt cards."""
    if not measures.GATE.get("dealt_objects") or not mystery.killer:
        return []
    lies = mystery.lies_by(mystery.killer)
    scene = mystery.murder_scene
    order = {s.id: s.index for s in mystery.slots}
    died = order.get(scene.slot) if scene is not None else None
    earlier = [c for c in lies if died is not None and order.get(c.slot, died) < died]
    if not earlier_lie(request.seed, request.topology):
        return [] if not earlier else [
            "The killer lies about an hour before the murder, and that was not dealt. "
            "One lie for the killer, the one the shape asks for."
        ]
    if not earlier:
        return ["The killer's earlier lie was dealt and is not there: a second "
                "`false_claims` entry for the killer, at an hour before the murder."]
    out = []
    claim = earlier[0]
    really = mystery.placements.get(mystery.killer, {}).get(claim.slot)
    others = [
        p for p, rows in mystery.placements.items()
        if p not in (mystery.killer, mystery.victim) and rows.get(claim.slot) == really
    ]
    if len(others) > 1:
        out.append(
            f"At {claim.slot}, the hour of the killer's earlier lie, {len(others)} "
            f"people were in the room the killer was really in. At most one, an "
            f"innocent busy with their own secret, or the killer is left having seen "
            f"almost nothing all evening."
        )
    holds = {s.holder for s in mystery.secrets if mystery.killer in s.known_by}
    if not holds - {mystery.killer, mystery.victim}:
        out.append("For the earlier lie, the killer must be in the `known_by` of a "
                   "secret an innocent holds, so their half-truth has something true "
                   "to point at.")
    return out


def _object_complaints(mystery: Mystery, request: GenerationRequest) -> list[str]:
    """Objects that do not play the roles they were dealt (D-203). Soft, like
    D-202: sent back while there are drafts left, kept if none fixes it."""
    if not measures.GATE.get("dealt_objects"):
        return []
    held = object_hand(request.seed)
    roles = [t.role for t in mystery.things]
    out: list[str] = []
    if sorted(roles) != sorted(held):
        out.append(
            f"The objects play {', '.join(roles) or 'no roles'}; they were dealt "
            f"{', '.join(held)}. One `thing` per dealt role, with its `role` set."
        )
    killer, victim = mystery.killer, mystery.victim
    for t in mystery.things:
        moved = t.moves > 0
        if t.role == "residue" and moved:
            out.append(f"`{t.id}` is residue, and residue does not move.")
        elif t.role == "killer_trace" and killer not in {t.belongs_to, *t.moved_by.values()}:
            out.append(f"`{t.id}` is the killer's trace: it is the killer's, or the "
                       f"killer moves it.")
        elif t.role == "misleading" and t.belongs_to in (None, killer, victim):
            out.append(f"`{t.id}` is misleading: it belongs to an innocent "
                       f"(`belongs_to`), not the killer or the victim.")
        elif t.role == "carried" and not (moved and set(t.moved_by.values()) - {killer}):
            out.append(f"`{t.id}` is carried: an innocent moves it.")
    scene = scene_object(request.seed)
    found = {t.role for t in mystery.found_with}
    if scene == "nothing" and found:
        out.append("Nothing was dealt to lie with the body, and an object is in the "
                   "room of the finding at the last hour. Move it out.")
    elif scene != "nothing" and scene not in found:
        out.append(f"The `{scene}` object must be in the room of the finding at the "
                   f"last hour.")
    return out


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
    cache_dir: Path | None,
    request: "GenerationRequest",
    mystery: Mystery,
    short: list[str],
    stage: str = "whole",
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
                    # "skeleton" when it never reached the prose: kept for C,
                    # where a near miss is shelved at an easier difficulty.
                    "stage": stage,
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


def sketch(request: GenerationRequest, drafter: Staged, var: Path = Path("var")) -> dict[str, Any]:
    """One skeleton, judged and written down, nothing else (D-192).

    For experiments: what the model does on a first try, at a third of the price
    of a case. No revision, no prose, nothing shelved. Each one lands in
    `var/skeletons` with what it was dealt, what it cost, whether it passed, and
    which protection it gave the killer, so a run can be counted without anybody
    reading a case.
    """
    from mystery.topology import classify

    built_with = _stamp(drafter)
    raw = _unwrap(drafter.skeleton(request, [], None))
    mystery, complaints, _ = _judge({"title": "", **raw}, request, built_with, 1)
    kept = {
        "seed": request.seed,
        "topology": request.topology,
        "built_with": built_with,
        "usd": drafter.last_usd,
        "passed": mystery is not None and not complaints,
        "complaints": complaints,
        "protection": classify(mystery) if mystery is not None else "",
        "skeleton": raw,
    }
    folder = var / "skeletons"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{request.cache_key()}.json").write_text(
        json.dumps(kept, indent=2, default=str), encoding="utf-8"
    )
    return kept


class GenerationFailed(RuntimeError):
    def __init__(self, complaints: list[str]) -> None:
        self.complaints = complaints
        super().__init__(
            "The model could not produce a usable mystery. Last problems:\n"
            + "\n".join(f"  - {c}" for c in complaints)
        )
