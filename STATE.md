# STATE

**NEXT:** Play it with someone. In a browser:

    uv add fastapi uvicorn
    uv run python -m mystery.web --setting "..." --seed 3

Then open http://localhost:8000. Suspect buttons, a chat, and the notebook as a
live panel on the right. `--model` switches which model plays the suspects.

The terminal version is still there: `uv run python -m mystery.cli --setting "..." --seed N --play`
is a complete game: generate, solve, validate, interrogate, accuse, reveal.

Nobody has played a generated case yet. The questions that matter are the same
ones the paper prototype answered: is it fun, do the five suspects sound like
different people, and does the notebook do too much or too little. Use
`--show-leaks` to watch the agents while you play.

After that: measure the leak rate against a local model, which is the Ollama
routing decision (D-004). The suite exists and passes against fakes; what nobody knows yet is
how often a real model cites something it does not have, and whether llama can do
this at all. That number is the Ollama routing decision (D-004), settled by
measurement instead of assertion.

Then the interrogation loop: ask, log the claim, and track contradictions across
characters. That is the last piece before the game is playable in a terminal.

---

**Where things are, 27 August 2026**

The pipeline runs end to end against the real model. First real output was valid
on the first try, and had four things wrong with it that no rule could catch.

- Repo: github.com/FreddyDeWatersir/murdermaistery
- `models.py` — Mystery (with killer and victim), Character, Place, Slot, Constraint
- `generator.py` — schema-forced Anthropic call, UTF-8 disk cache, fakeable boundary
- `solver.py` — repairs the model's grid, or builds one from nothing as fallback
- `validator.py` — V1 to V4, phased into proposed and final. Correctness only
- `critique.py` — A1 to A3. Quality advisories that report and never fail
- `cli.py` — generate, solve, validate, critique, print
- Thirty two tests green, ruff clean, no test calls an API
- Architecture note: https://claude.ai/code/artifact/537fe482-a219-4b13-a108-062bff885a1f
- Thirty two decisions in `docs/decisions.md`

**What was wrong with the first real output**

1. A character found the body at slot 4 of 5, and the evening carried on around
   her. Discovery must fall after the last slot. Prompt fixed
2. Everyone wandered: five rooms in five slots. The same failure the solver had,
   reproduced by the model. Prompt fixed, A1 now measures it
3. Anglo-thriller names for an Amsterdam gallery. D-018 arriving on schedule.
   Prompt fixed
4. Nothing verified the alibi property the whole design rests on. A2 now
   measures it, crudely

**The four layers**

| Layer | State |
|---|---|
| Generation | runs end to end. Knowledge derivation still missing |
| Play | nothing |
| Resolution | nothing |
| Delivery | nothing |

**Rules and advisories**

| Id | What | Kind |
|---|---|---|
| V1 | Bound constraints agree with the timeline | fails |
| V2 | Exclusive constraints are private | fails |
| V3 | Every constraint was placed | fails |
| V4 | Every referenced id exists | fails |
| V6 | No character required in two rooms at once | fails, final phase only |
| V7 | The victim stays dead and the body stays put | fails |
| V0 | No holes in the grid | unwritten |
| A1 | Nobody wanders more than twice | reports |
| A2 | Two to four people lack an alibi at the murder | reports |
| A3 | Every suspect has something to conceal | reports |
| A4 | The victim is a hub, not one subplot among five | reports |
| A5 | The killer's motive is gated behind another secret | reports |
| A6 | The killer makes a false claim about where they were | reports |
| A7 | The alibi breaks on combined testimony, not on any one | reports |
| A8 | Every suspect had a moment nobody witnessed | reports |

**Numbers nobody has justified**

`STICKINESS = 0.75`, `MAX_MOVES_PER_CHARACTER = 2`, `ALIBI_GAP_RANGE = (2, 4)`,
`MIN_SUSPECTS_WITH_A_STAKE_IN_THE_VICTIM = 0.5`.
All invented. All now at least visible. See D-025 and D-031.

**Open questions, in priority order**

1. Nothing checks the property the design rests on: that the killer's alibi
   breaks under two combined testimonies and no single one. A2 is a crude proxy
2. Notebook versus solver. Gates the interface
3. Topology library, since variety is structural not cosmetic
4. Where game state lives between turns

**Errands, not gates**

- V0, and moving a curated corpus from `var/` to `tests/fixtures/`
- Blind replay of a third prototype. See D-020
