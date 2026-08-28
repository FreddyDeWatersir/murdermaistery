# STATE

**NEXT:** Generate three cases on consecutive seeds and read the casts side by
side. Every seed now deals its own manners, motive and intrigues (D-075), and
the question is whether that shows up as five different people or as five
different labels on the same five people. If it is the latter, the worked
example in the prompt is the next suspect: it is the last place the model is
still being shown somebody else's finished cast.

Then play two cases of different shapes back to back and see whether they feel
like different puzzles or the same one.

    uv run python -m mystery.web --setting "..." --topology mutual_alibi

Three things to watch. Whether catching somebody in a lie still ends the
investigation or whether the player now has to ask why. `agent.folded` in the
log: how many questions it takes an innocent to admit where they were, where
folding on question two means the conditions are too soft and never folding
means the red herrings never resolve. And whether the false confession lands as
a twist or as an annoyance.

Cached seeds are invalidated again by the prompt change, so the first run of any
seed costs a fresh Opus draft. That is D-035 working, not a bug.

Optional: `--art` (faces and rooms, or `--portraits` and `--scenery`
separately) needs `OPENAI_API_KEY` and
`uv sync --extra portraits`. Run `uv sync` either way: the tests now need httpx.

---

**Where things are, 27 August 2026**

The game is playable end to end in a browser, three playtests deep. The third
one found the structural flaw: one liar meant one hidden variable, and the
timeline answered the case on its own (D-063).

- Repo: github.com/FreddyDeWatersir/murdermaistery
- `models.py` — Mystery, Character (`role` and `gender` public, `wants` not),
  Place, Slot, Constraint, Secret, FalseClaim, Discovery
- `generator.py` — schema-forced Anthropic call, UTF-8 disk cache, fakeable
  boundary, and the two model tiers
- `solver.py` — repairs the model's grid, or builds one from nothing as fallback
- `validator.py` — V1 to V8, phased into proposed and final. Correctness only
- `critique.py` — A1 to A14. Quality advisories that report and never fail
- `knowledge.py` — co-location arithmetic, no model involved
- `agent.py` — briefs, citation-checked replies, three knowledge states
- `interrogation.py` — transcript, contradictions, leads, what has surfaced
- `web.py` — the browser game, portraits, notebook, transcript, timeline
- `topology.py` — the shapes a case can have, and the checks each one demands
- `solvable.py` — is there a way in, and does it lead to the motive
- `scenery.py` — optional backdrops for the setting and the rooms
- `example.py` — one case in the repo, for `--dry-run` and the end-to-end test
- `library.py` — the shelf: cheap listings, whole cases, and the art with them
- `palette.py` — the manners, motives and intrigues each case is dealt
- `session.py` — a play-through, as a record, with two stores behind one boundary
- `daily.py` — the rota: claim a day, and the buffer behind it
- `portraits.py` — optional generated faces, never load-bearing
- Two hundred and twenty two tests green, ruff clean, no test calls an API
- Architecture note: https://claude.ai/code/artifact/537fe482-a219-4b13-a108-062bff885a1f
- Eighty four decisions in `docs/decisions.md`

**Which model does what**

| Job | Model | How often |
|---|---|---|
| Drafting the case | `claude-opus-5` | once per case |
| Speaking as a suspect | `claude-sonnet-5` | once per question |

Both overridable: `--generator-model` and `--model`. See D-060.

A draft costs about nineteen cents, a question about half a cent, so a case is
roughly twenty cents to make and twenty five more to play through. Every model
call logs its own `usd`, and `--fill` prints the bill before it starts. See
D-084.

**The four layers**

| Layer | State |
|---|---|
| Generation | three shapes, dealt material, and self-correcting retries |
| Play | browser, five suspects, notebook, transcript, timeline |
| Resolution | name the killer and the motive, three endings, full reveal |
| Delivery | localhost, or `--share` on the wifi. Sessions per visitor |

**Rules and advisories**

| Id | What | Kind |
|---|---|---|
| V1 | Bound constraints agree with the timeline | fails |
| V2 | Exclusive constraints are private | fails |
| V3 | Every constraint was placed | fails |
| V4 | Every referenced id exists | fails |
| V6 | No character required in two rooms at once | fails, final phase only |
| V7 | The victim stays dead and the body stays put | fails |
| V8 | A lie is actually a lie, one per person | fails |
| V0 | No holes in the grid | unwritten |
| A1 | Nobody wanders more than twice | reports |
| A2 | Two to four people lack an alibi at the murder | reports |
| A3 | Every suspect has something to conceal | reports |
| A4 | The victim is a hub, not one subplot among five | reports |
| A5 | The killer's motive is gated behind another secret | reports |
| A6 | The killer makes a false claim about where they were | reports |
| A7 | The alibi breaks on combined testimony, not on any one | reports |
| A8 | Every suspect had a moment nobody witnessed | reports |
| A9 | Every suspect is load-bearing | reports |
| A10 | The killer is not the only liar | reports |
| A11 | Every innocent lie has a way out | reports |
| A12 | Position alone does not convict | reports |
| A13 | Somebody other than the killer knows the motive | reports |
| A14 | The cast is not five of the same person | reports |
| T1 | Mutual alibi: somebody actually vouches for the killer | reports |
| T2 | Mutual alibi: the corroborator can be broken from their own side | reports |
| T3 | False confession: the confessor is not the killer | reports |
| T4 | False confession: the confession can be disproved | reports |
| S1 | There is a secret the player can get with nothing in hand | reports |
| S2 | No secret is sealed behind a loop or a missing gate | reports |
| S3 | The motive is reachable | reports |
| S4 | Every lie covers something that can surface | reports |

**Numbers nobody has justified**

`STICKINESS = 0.75`, `MAX_MOVES_PER_CHARACTER = 2`, `ALIBI_GAP_RANGE = (2, 4)`,
`MIN_SUSPECTS_WITH_A_STAKE_IN_THE_VICTIM = 0.5`, `INNOCENT_LIARS = 2`.
All invented. All at least visible. See D-025 and D-031.

**Open questions, in priority order**

1. Stage 4. Sessions (D-077) and the daily rota (D-078) are in and run locally.
   The rota claims a day (D-079) and a session is a record with two stores
   behind it (D-080). What is left: the shelf behind its own interface, then the
   S3 and DynamoDB implementations written with the console open, then Lambda,
   Terraform and CI. The budget guard is
   not optional: a public URL that calls a model per question is how people wake
   up to a four figure bill
2. Does the case still fall to the timeline alone? Three liars is the structural
   fix; whether it works is a question about play, not about code
3. How hard should an innocent be to crack. `agent.folded` measures it and
   nothing tunes it yet
4. What else is built and never called. The end-to-end test (D-070) covers the
   library seams; nothing yet covers `main()` in either entry point
5. Two more shapes, both needing a model change rather than a paragraph: the
   moved body, and the unpinned time of death

**How to check the state of things, cheapest first**

    uv sync                                   # httpx is new
    uv run pytest                             # 222 tests, no network, no spend
    uv run ruff check .
    uv run python -m mystery.cli --topologies
    uv run python -m mystery.cli --material 3 --setting "..."  # what 3 seeds get dealt
    uv run python -m mystery.cli --casts      # every saved cast, side by side
    uv run python -m mystery.cli --dry-run    # the whole pipeline, no key needed
    uv run python -m mystery.cli --setting "..." --topology mutual_alibi
    uv run python -m mystery.cli --today      # today's case, and what is queued
    uv run python -m mystery.cli --fill --setting "..."   # top up the shelf to four
    uv run python -m mystery.web --daily      # serve today's, never generate
    uv run python -m mystery.web --cases      # what you have already got
    uv run python -m mystery.web --case <name> # play it again, no model, no wait
    uv run python -m mystery.web --dry-run    # play the shipped case
    uv run python -m mystery.web --setting "..." --topology mutual_alibi --art
    uv run python -m mystery.cli --bundle NAME    # carry a case to another machine
    uv run python -m mystery.cli --unbundle F.zip # and unpack it there

Every command that generates a case keeps it: `--cases` is empty only because
nothing has been generated since the shelf existed. A draft is about nineteen
cents, and `--fill` says so before it starts (D-084).

`--art` costs about fifteen cents a case at the default `--art-quality low`,
four times that at medium and fifteen times at high. It prints the estimate
before spending and never regenerates pictures already on disk. See D-082.

The CLI and the web game share `var/mysteries`, so a case inspected with the
first is free to start with the second, as long as every flag matches.

**Errands, not gates**

- V0
- Blind replay of a third prototype. See D-020
- Stages 4 and 5, AWS and the daily shared case, untouched
