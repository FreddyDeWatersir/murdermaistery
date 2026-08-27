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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import structlog
from dotenv import load_dotenv
from mystery.models import Mystery
from pydantic import BaseModel, ValidationError

# Reads .env from the project root if present, so a key can live in a
# gitignored file instead of being re-exported in every new terminal.
load_dotenv()

log = structlog.get_logger()

DEFAULT_MODEL = "claude-sonnet-4-5"


class GenerationRequest(BaseModel):
    """What we ask for. Everything the prompt varies on lives here, so the cache
    key is just a hash of this."""

    setting: str
    cast_size: int = 5
    slot_count: int = 5
    place_count: int = 5
    topology: str = "the killer lies about where they were"
    seed: int = 0

    def cache_key(self) -> str:
        """Hash of the request *and* the prompt that will be sent with it.

        Without the prompt in the key, editing the system prompt changes nothing:
        every previously generated seed keeps returning the draft it produced
        under the old instructions, and you spend an afternoon wondering why your
        changes had no effect. They did. You were reading a cached answer.
        """
        payload = (self.model_dump_json(exclude_none=True) + SYSTEM_PROMPT).encode()
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

1. The cast. Each suspect wants something and each is concealing something. \
Only one of those secrets is the murder. A cast where three people have nothing \
to hide is three cooperative witnesses and one obvious liar, and there is no \
game.

For every character fill in `wants`, `manner` and `under_pressure`. These are \
not decoration: they are the whole difference between a witness reciting \
locations and a person. Make them specific and make them different from each \
other. One talks too much and volunteers irrelevant detail. One is cold and \
answers exactly the question asked and nothing more. One is performing \
composure and it is costing them. One is helpful in manner and unhelpful in \
substance. Somebody should be willing to trade information rather than simply \
give it.

2. The murder. Who, whom, how, and above all why. The motive should come out of \
what the killer is concealing.

3. The secrets, and this is the step that decides whether the case is any good.

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

**The killer lies about where they were.** Fill in `false_claim` with the room \
and the slot they will claim, which must not be where they actually were. \
Choose a room that had **at least two other people in it at that moment**, and \
ideally people who are themselves concealing something. An empty room is an \
unbreakable alibi: nobody can say the killer was not there, and the case cannot \
be solved at all. Compromised witnesses matter too, because a witness with \
nothing to hide is believed instantly and ends the game in one question.

**Mark the killer's motive.** The killer holds two secrets: the background that \
made them vulnerable, and the reason they killed. Set `is_motive` to true on the \
second one, and gate it with `revealed_by`.

**Every secret needs a breaking point.** Fill in `breaks_when` with the \
condition under which its holder stops concealing it: confronted with a named \
fact, offered something in return, asked a question they were not braced for, \
told that someone else has already said it. Concealment that never breaks is a \
wall rather than a mystery, and the conditions should differ from character to \
character.

Put all of this in `secrets`, with `holder`, `about`, `summary`, `known_by` for \
anyone else who knows, `revealed_by` where one secret gates another, and \
`breaks_when` on every one.

4. The constraints: the things that must be true of the evening. A constraint \
names people who share a place at a moment. Mark it `exclusive` when they must \
be alone with nobody else present. You need, at minimum:
   - the killer and the victim alone together
   - at least two other suspects with a private moment of their own, so a \
missing alibi proves nothing on its own
   - one exchange overheard by exactly one person who was not part of it

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
- Name the killer and the victim in the `killer` and `victim` fields.

Design rules for a case worth playing:
- The killer's alibi must be breakable by combining at least two people's \
testimony, and by no single person's alone.
- The killer's motive should only become visible after some unrelated-looking \
secret has been cracked, so that the obvious suspect is not the answer.
- Six to ten constraints.

Names belong to the setting. A gathering in Amsterdam has Dutch names, one in \
Naples has Italian ones. Reaching for the same handful of Anglo-thriller \
surnames every time is the fastest way to make every case feel like the last one.

Ids are short lowercase snake_case. Every id you reference must exist.\
"""


def _user_prompt(request: GenerationRequest) -> str:
    return (
        f"Setting: {request.setting}\n"
        f"Cast: {request.cast_size} suspects plus one victim.\n"
        f"Places: {request.place_count} distinct rooms or areas.\n"
        f"Time: {request.slot_count} consecutive slots.\n"
        f"Shape of the solution: {request.topology}\n\n"
        f"Variation key {request.seed}: use it to take a different angle on this "
        f"setting than you otherwise would."
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
    model: str = DEFAULT_MODEL, api_key: str | None = None
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
            max_tokens=8000,
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
            seconds=round(time.monotonic() - started, 2),
            setting=request.setting,
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
