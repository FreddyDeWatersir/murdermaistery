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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import structlog
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
    conceals: list[Fact] = field(default_factory=list)

    @property
    def licensed(self) -> set[str]:
        return {fact.id for fact in self.facts}


@dataclass
class Reply:
    speech: str
    used: list[str] = field(default_factory=list)
    refused: bool = False


def build_brief(
    mystery: Mystery, knowledge: dict[CharacterId, Knowledge], character: CharacterId
) -> Brief:
    """Assemble the licensed facts for one character.

    The killer is a special case and the most important one. Their brief carries
    the *lie* as the thing they will say about the murder slot, and the truth
    appears only among the things they conceal. An agent given both as sayable
    facts will hedge, and a killer who hedges is a killer the player spots in one
    question.
    """
    names = {c.id: c.name for c in mystery.characters}
    places = {p.id: p.name for p in mystery.places}
    times = {s.id: s.label for s in mystery.slots}
    know = knowledge[character]

    facts: list[Fact] = []
    conceals: list[Fact] = []

    claim = mystery.false_claim
    lying_about = claim.slot if claim and claim.character == character else None

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
            conceals.append(
                Fact(
                    id=f"truth:{slot.id}",
                    text=(
                        f"You were actually in the {places.get(where, where)} at "
                        f"{times[slot.id]}. You will not say this."
                    ),
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
        if secret:
            breaks = (
                f" You will stop concealing it only if: {secret.breaks_when}"
                if secret.breaks_when
                else " You do not give this up."
            )
            conceals.append(
                Fact(id=f"secret:{secret_id}", text=f"{secret.summary}{breaks}")
            )

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

    return Brief(
        character=character,
        name=names.get(character, character),
        wants=person.wants if person else "",
        manner=person.manner if person else "",
        under_pressure=person.under_pressure if person else "",
        facts=facts,
        conceals=conceals,
    )


SYSTEM = """\
You are {name}, being questioned after a death at a gathering you attended.

WHO YOU ARE
{person}

Answer in character, briefly, the way a real person under mild suspicion would: \
not a report, not a list. One to four sentences. Your manner matters as much as \
your answer: a cold person and a nervous person can give the same facts and the \
questioner should be able to tell them apart.

You may only state things from FACTS below. If the question asks about something \
no fact covers, say you do not know or do not remember, and set refused to true. \
Do not guess, do not reconstruct, do not be helpful about things you did not see. \
Being unable to answer is a normal thing for a person to be.

Cite the id of every fact you draw on in `used`.

Things under CONCEALED are true and you know them, and you will not volunteer \
them. Deflect, change the subject, answer a narrower question than the one asked. \
Do not lie about anything else, and never mention a concealed item's existence.

Each concealed item names the condition under which you would give it up. If \
the questioner has met that condition, you may. Nothing else opens you.

FACTS
{facts}

CONCEALED
{conceals}
"""


def render_person(brief: Brief) -> str:
    lines = [
        f"  You want: {brief.wants}" if brief.wants else "",
        f"  Your manner: {brief.manner}" if brief.manner else "",
        f"  Under pressure: {brief.under_pressure}" if brief.under_pressure else "",
    ]
    return "\n".join(line for line in lines if line) or "  (an ordinary guest)"


def render_system(brief: Brief) -> str:
    return SYSTEM.format(
        name=brief.name,
        person=render_person(brief),
        facts="\n".join(f"  [{f.id}] {f.text}" for f in brief.facts) or "  (nothing)",
        conceals="\n".join(f"  {f.text}" for f in brief.conceals) or "  (nothing)",
    )


# system prompt, question -> raw reply dict. Same shape as Drafter (D-027): the
# real one calls a model, tests pass a fake, and the suite never touches a network.
Responder = Callable[[str, str], dict[str, Any]]


def ask(brief: Brief, question: str, responder: Responder) -> Reply:
    raw = responder(render_system(brief), question)
    return Reply(
        speech=str(raw.get("speech", "")),
        used=list(raw.get("used", [])),
        refused=bool(raw.get("refused", False)),
    )


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


def anthropic_responder(model: str = "claude-sonnet-4-5", api_key: str | None = None):
    """The real thing. Imported lazily so the suite runs with no SDK and no key."""
    import os

    import anthropic

    client = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

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
        )
        for block in response.content:
            if block.type == "tool_use":
                return dict(block.input)
        return {"speech": "", "used": [], "refused": True}

    return respond
