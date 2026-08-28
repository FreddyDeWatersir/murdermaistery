"""One character, answering questions from only what they know.

The design rule is D-038: facts are computed, only the voice is generated. This
module turns a character's derived `Knowledge` into a numbered list of licensed
facts, hands that to a model, and requires the model to cite which facts it used.

Citation is the whole trick. Free prose cannot be checked for leakage without
reading it, and "did this answer contain something the character could not know"
is otherwise a judgement call made by a human at midnight. With citations it
becomes set membership: every id the reply claims to have used must be in the
licensed set, and one that is not is a leak, mechanically.

Two honest limitations, stated here rather than discovered later:

1. A model can cite correctly and still say something unlicensed in the prose.
   Citation catches the common failure, not every failure.
2. `conceals` are included in the brief on purpose. A character has to know their
   own secret in order to deflect around it. That means the brief contains
   material the answer must not reveal, which is a real risk and is exactly what
   the leakage suite exists to measure.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

# The two model tiers live in generator.py because that is where the model
# boundary was first drawn (D-060). Importing the name rather than repeating the
# string keeps them from drifting apart the next time one is bumped.
from mystery.generator import VOICE_MODEL, cost
from mystery.knowledge import Knowledge
from mystery.models import CharacterId, Mystery, PlaceId, SlotId

log = structlog.get_logger()


@dataclass(frozen=True)
class Fact:
    """One thing a character may say, with an id the model must cite.

    `subject`, `slot` and `place` carry the same content as `text` in a form the
    contradiction tracker can compare. Parsing meaning back out of prose is how
    you build a tracker that works on Tuesday and breaks when someone rewords a
    sentence, so the structure travels alongside the words rather than being
    recovered from them.
    """

    id: str
    text: str
    subject: CharacterId | None = None
    slot: SlotId | None = None
    place: PlaceId | None = None


@dataclass
class Brief:
    """Everything one character brings into an interrogation.

    Two halves, from two different places. `facts` and `conceals` are derived
    from the timeline and must never be invented. `wants`, `manner` and
    `under_pressure` are authored by the model at generation time, because a
    person cannot be computed from a grid (D-044).
    """

    character: CharacterId
    name: str
    wants: str = ""
    manner: str = ""
    under_pressure: str = ""
    facts: list[Fact] = field(default_factory=list)
    guarded: list[Fact] = field(default_factory=list)
    conceals: list[Fact] = field(default_factory=list)
    impressions: list[str] = field(default_factory=list)
    common: list[str] = field(default_factory=list)
    # Behaviour this character has that no fact can express, put here by the
    # shape of the case rather than by the timeline (D-067). The false
    # confession is the first one: it is a thing they will do, not a thing they
    # know.
    instructions: list[str] = field(default_factory=list)

    @property
    def licensed(self) -> set[str]:
        """Everything this character may cite, guarded material included.

        Three states, not two (D-064). `facts` they will say. `conceals` they
        will never say. `guarded` is the middle: true, citable, and held back
        until the questioner earns it. An innocent who lied about where they
        were needs that middle state, because a retraction nobody can cite is a
        retraction the notebook never hears, and the player watches a suspect
        come clean while the timeline goes on showing the lie.
        """
        return {fact.id for fact in self.facts} | {fact.id for fact in self.guarded}


@dataclass
class Reply:
    speech: str
    used: list[str] = field(default_factory=list)
    refused: bool = False


def build_brief(
    mystery: Mystery, knowledge: dict[CharacterId, Knowledge], character: CharacterId
) -> Brief:
    """Assemble the licensed facts for one character.

    Anyone in `false_claims` gets the *lie* as the thing they will say about
    that moment, and the truth is moved out of their sayable facts. An agent
    given both will hedge, and a liar who hedges is a liar the player spots in
    one question.

    Where the truth goes depends on whether they killed him (D-063). The
    killer's goes to `conceals` and never comes out. An innocent's goes to
    `guarded`: still withheld, but citable once the questioner meets the
    condition, because their retraction is the thing that clears them and the
    notebook has to be able to record it.

    Either way, what they saw during the moment they are lying about is dropped
    from their facts entirely (D-042). A character who claims the green room
    cannot report who else was in the prop store.

    Their own secrets are guarded rather than concealed (D-066), for the same
    reason and with the same exception: a secret that surfaces has to be
    countable, and the killer's motive is the one thing that never surfaces.
    A killer under pressure gives up the smaller true thing instead, which is
    the shield, and the shield is now a guarded fact rather than a hope.
    """
    names = {c.id: c.name for c in mystery.characters}
    places = {p.id: p.name for p in mystery.places}
    times = {s.id: s.label for s in mystery.slots}
    know = knowledge[character]

    facts: list[Fact] = []
    guarded: list[Fact] = []
    conceals: list[Fact] = []

    claim = mystery.lie_by(character)
    lying_about = claim.slot if claim else None
    is_the_killer = character == mystery.killer

    for slot in sorted(mystery.slots, key=lambda s: s.index):
        where = know.movements.get(slot.id)
        if where is None:
            continue

        if slot.id == lying_about:
            facts.append(
                Fact(
                    id=f"self:{slot.id}",
                    text=f"At {times[slot.id]} you were in the {places[claim.place]}.",
                    subject=character,
                    slot=slot.id,
                    place=claim.place,
                )
            )
            really = (
                f"You were actually in the {places.get(where, where)} at {times[slot.id]}."
            )

            if is_the_killer:
                # The killer never gives this up. Under pressure they offer the
                # shield instead: a smaller true thing that explains the
                # evasiveness and is not the murder.
                conceals.append(
                    Fact(
                        id=f"truth:{slot.id}",
                        text=f"{really} You will not say this. Not to anyone, not ever.",
                    )
                )
            else:
                # An innocent liar can be brought to it, and the notebook has to
                # be able to hear it when they are, so it is citable (D-064).
                condition = claim.admits_when or (
                    "the questioner already knows what you were really doing"
                )
                guarded.append(
                    Fact(
                        id=f"truth:{slot.id}",
                        text=(
                            f"{really} You said otherwise and you are not going back "
                            f"on it lightly. You will admit it only if: {condition}"
                        ),
                        subject=character,
                        slot=slot.id,
                        place=where,
                    )
                )
        else:
            facts.append(
                Fact(
                    id=f"self:{slot.id}",
                    text=f"At {times[slot.id]} you were in the {places.get(where, where)}.",
                    subject=character,
                    slot=slot.id,
                    place=where,
                )
            )

    for observation in know.observations:
        if observation.slot == lying_about:
            continue
        facts.append(
            Fact(
                id=f"saw:{observation.subject}@{observation.slot}",
                text=(
                    f"At {times.get(observation.slot, observation.slot)} you saw "
                    f"{names.get(observation.subject, observation.subject)} in the "
                    f"{places.get(observation.place, observation.place)}."
                ),
                subject=observation.subject,
                slot=observation.slot,
                place=observation.place,
            )
        )

    by_id = {secret.id: secret for secret in mystery.secrets}

    for secret_id in know.conceals:
        secret = by_id.get(secret_id)
        if not secret:
            continue

        # The one secret nobody ever gives up: the reason the killer did it.
        # Everything else a person is sitting on can be got out of them, which
        # is what an interrogation is for (D-066).
        sealed = is_the_killer and secret.is_motive

        if sealed:
            conceals.append(
                Fact(
                    id=f"secret:{secret_id}",
                    text=(
                        f"{secret.summary} This is why you did it. You do not give "
                        f"this up, under any pressure, to anyone, ever."
                    ),
                )
            )
            continue

        breaks = (
            f" You will say it only if: {secret.breaks_when}"
            if secret.breaks_when
            else " You give this up only if you are left with no way around it."
        )
        guarded.append(Fact(id=f"secret:{secret_id}", text=f"{secret.summary}{breaks}"))

    for secret_id in know.aware_of:
        secret = by_id.get(secret_id)
        if secret:
            facts.append(
                Fact(
                    id=f"heard:{secret_id}",
                    text=f"You know, but it is not your secret: {secret.summary}",
                )
            )

    person = next((c for c in mystery.characters if c.id == character), None)

    impressions = []
    if person:
        for other, view in person.impressions.items():
            if other != character and other in names:
                impressions.append(f"{names[other]}: {view}")

    instructions = []
    if character == mystery.false_confessor:
        instructions.append(
            "If you are pushed hard, and only then, you will say that you killed "
            "them. You did not. You have your own reason for saying it and you "
            "believe in it. Do not offer this early and do not hint at it: it "
            "should arrive as the last thing you have left."
        )

    common = []
    if mystery.discovery:
        d = mystery.discovery
        common.append(
            f"{names.get(mystery.victim, 'The victim')} is dead. "
            f"{names.get(d.finder, d.finder)} found the body in the "
            f"{places.get(d.place, d.place)} after the evening was over. "
            f"{d.summary}".strip()
        )
        common.append("Everybody here knows that much. It is not a secret.")

    return Brief(
        character=character,
        name=names.get(character, character),
        wants=person.wants if person else "",
        manner=person.manner if person else "",
        under_pressure=person.under_pressure if person else "",
        facts=facts,
        guarded=guarded,
        conceals=conceals,
        impressions=impressions,
        common=common,
        instructions=instructions,
    )


SYSTEM = """\
You are {name}. There has been a death at a gathering you attended and somebody \
is asking you about it.

WHO YOU ARE
{person}

WHAT EVERYONE KNOWS
{common}

HOW TO ANSWER

Be a person, not a witness statement. Two to five sentences. React to what you \
are asked, have feelings about it, say what you thought of people. If a question \
is rude, be annoyed by it. If it is the fourth time you have been asked the same \
thing, say so.

There is one hard line and it is only about **facts of who was where and when**. \
For those you may state nothing beyond FACTS below, and you cite the id of each \
one you use in `used`. If you are asked to place somebody somewhere and no fact \
covers it, say you do not know, you did not see, you were not paying attention. \
Set refused to true only in that case.

Everything else is yours and you should be generous with it. Your opinions of \
these people. How the evening felt. What you were doing and why, in your own \
words. What you make of the death. What you think of being questioned. None of \
that needs a fact and none of it needs citing, and a question about a person \
rather than a place should never be refused.

WHAT YOU THINK OF THEM
{impressions}

THINGS YOU HAVE ALREADY SAID
Stay consistent with these. If you contradict yourself the person asking will \
notice, and if you are changing your story do it deliberately rather than by \
accident.
{history}

CONCEALED
These are true, you know them, and you will not volunteer them. Deflect, answer \
a narrower question than the one asked, change the subject. Never mention that \
there is something you are not saying. Each one names the condition under which \
you would give it up: if the questioner has met that condition, you may. Nothing \
else opens you.
{conceals}

HELD BACK
True, and yours to give if the questioner earns it. Each one says what would \
make you say it. Until then you stay with the story you told. If you do decide \
to come clean, say so plainly rather than hinting, and cite it like any other \
fact.
{guarded}

FACTS
Only these may be stated as fact about where anyone was.
{facts}
"""


def render_person(brief: Brief) -> str:
    lines = [
        f"  You want: {brief.wants}" if brief.wants else "",
        f"  Your manner: {brief.manner}" if brief.manner else "",
        f"  Under pressure: {brief.under_pressure}" if brief.under_pressure else "",
        *(f"  {note}" for note in brief.instructions),
    ]
    return "\n".join(line for line in lines if line) or "  (an ordinary guest)"


def render_history(history: Sequence[tuple[str, str]]) -> str:
    """What this character has already committed to, in their own words.

    Without it a suspect answers every question as though it were the first,
    which the first playtest noticed immediately. Consistency is not something a
    model can invent from nothing: it has to be shown what it said.
    """
    if not history:
        return "  (nothing yet, this is the first thing you have been asked)"
    return "\n".join(f'  They asked: {q}\n  You said: {a}' for q, a in history)


def render_system(brief: Brief, history: Sequence[tuple[str, str]] = ()) -> str:
    return SYSTEM.format(
        name=brief.name,
        person=render_person(brief),
        common="\n".join(f"  {c}" for c in brief.common) or "  (nothing beyond the death)",
        impressions="\n".join(f"  {i}" for i in brief.impressions)
        or "  (no strong feelings about any of them)",
        history=render_history(history),
        guarded="\n".join(f"  [{f.id}] {f.text}" for f in brief.guarded)
        or "  (nothing, you have been straight about where you were)",
        facts="\n".join(f"  [{f.id}] {f.text}" for f in brief.facts) or "  (nothing)",
        conceals="\n".join(f"  {f.text}" for f in brief.conceals) or "  (nothing)",
    )


# system prompt, question -> raw reply dict. Same shape as Drafter (D-027): the
# real one calls a model, tests pass a fake, and the suite never touches a network.
Responder = Callable[[str, str], dict[str, Any]]


def ask(
    brief: Brief,
    question: str,
    responder: Responder,
    history: Sequence[tuple[str, str]] = (),
) -> Reply:
    raw = responder(render_system(brief, history), question)
    reply = Reply(
        speech=str(raw.get("speech", "")),
        used=list(raw.get("used", [])),
        refused=bool(raw.get("refused", False)),
    )

    # A liar retracting is the single most interesting event in a session, and
    # it is the one thing about the cast we can measure without reading prose.
    # If characters fold on question two, the conditions are too soft; if nobody
    # ever folds, the red herrings never resolve and the case is unplayable.
    for fact in brief.guarded:
        if fact.id in reply.used:
            log.info(
                "agent.folded",
                character=brief.character,
                fact=fact.id,
                after=len(history) + 1,
            )

    return reply


def leaks(brief: Brief, reply: Reply) -> list[str]:
    """Fact ids the reply cited that this character has no licence to state.

    This is the knowledge leakage detector, and it is deliberately mechanical.
    A concealed item cited as a source is the worst case: the character has just
    handed over the thing they exist to hide.
    """
    concealed = {fact.id for fact in brief.conceals}
    found = []

    for used in reply.used:
        if used in concealed:
            found.append(f"cited concealed material: {used}")
        elif used not in brief.licensed:
            found.append(f"cited something it does not know: {used}")

    return found


def anthropic_responder(model: str = VOICE_MODEL, api_key: str | None = None):
    """The real thing. Imported lazily so the suite runs with no SDK and no key."""
    import os

    import anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "No ANTHROPIC_API_KEY found. Put it in a .env file in the project "
            "root as ANTHROPIC_API_KEY=sk-ant-... , or set it in your shell."
        )

    client = anthropic.Anthropic(api_key=key)

    schema = {
        "type": "object",
        "properties": {
            "speech": {"type": "string", "description": "What you say, in character."},
            "used": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids of every fact you drew on.",
            },
            "refused": {
                "type": "boolean",
                "description": "True if no fact covered the question.",
            },
        },
        "required": ["speech", "used", "refused"],
    }

    def respond(system: str, question: str) -> dict[str, Any]:
        response = client.messages.create(
            model=model,
            max_tokens=1000,
            system=system,
            messages=[{"role": "user", "content": question}],
            tools=[
                {
                    "name": "answer",
                    "description": "Reply in character.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": "answer"},
        )
        log.info(
            "agent.answered",
            model=model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            usd=round(
                cost(model, response.usage.input_tokens, response.usage.output_tokens), 4
            ),
        )
        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input)
        return {"speech": "", "used": [], "refused": True}

    return respond
