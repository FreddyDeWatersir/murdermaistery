# STATE

**NEXT:** Generate one case with nothing pinned and play it.

The last one, `the-sixth-name-on-the-board`, was the best so far and is worth
reading before the next: 132 questions, solved, and the four faults it still had
are D-111. What to watch this time is whether the cast is still one nationality,
whether any two of them disagree about a number, and whether the questioner's own
briefing turns up in anybody's mouth.

    uv run python -m mystery.web --setting "the last night of a residency at an old house, with the funding decision in the morning" --art

No seed and no topology: both are drawn and printed. This is the first case
that will be written under D-106 (three of them look guilty), D-108 (a second
half) and D-109 (a web, not a wheel), and every case on the shelf fails at
least two of those.

Watch the three things no check can see. Whether three suspects genuinely feel
worth writing down. Whether question thirty still turns something up, or whether
the case is spent by question ten the way the last one was. And whether anything
one person says ever makes you go back to somebody else, which is the whole
point of the web and the thing the last case never once did.

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
  Place (with its doors), Slot, Constraint, Secret, FalseClaim, Discovery,
  Investigator
- `generator.py` — schema-forced Anthropic call, UTF-8 disk cache, fakeable
  boundary, and the two model tiers
- `solver.py` — repairs the model's grid, or builds one from nothing as fallback
- `validator.py` — V1 to V10, phased into proposed and final. Correctness only
- `critique.py` — A1 to A19. Quality advisories that report and never fail
- `knowledge.py` — co-location arithmetic, no model involved
- `agent.py` — briefs, citation-checked replies, five knowledge states
- `interrogation.py` — transcript, contradictions, leads, what has surfaced,
  and what the house has been saying about it
- `web.py` — the browser game, portraits, notebook, transcript, timeline, and
  the plan with the evening running through it
- `topology.py` — seven shapes a case can have, and the checks each demands
- `solvable.py` — is there a way in, and does it lead to the motive
- `scenery.py` — one optional establishing shot of the place
- `example.py` — one case in the repo, for `--dry-run` and the end-to-end test
- `library.py` — the shelf: cheap listings, whole cases, and the art with them
- `palette.py` — manners, motives, intrigues, where on earth the house is, the
  player's standing and the old business that binds the cast, dealt from the seed
- `session.py` — a play-through, as a record, and what has been shown to whom
- `daily.py` — the rota: claim a day, and the buffer behind it
- `portraits.py` — optional generated faces, never load-bearing
- Three hundred and seventeen tests green, ruff clean, no test calls an API
- Architecture note: https://claude.ai/code/artifact/537fe482-a219-4b13-a108-062bff885a1f
- One hundred and thirteen decisions in `docs/decisions.md`

**Which model does what**

| Job | Model | How often |
|---|---|---|
| Drafting the case | `claude-opus-5` | once per case |
| Speaking as a suspect | `claude-sonnet-5` | once per question |

Both overridable: `--generator-model` and `--model`. See D-060.

A draft costs about twenty five cents, a question about half a cent, so a case is
roughly twenty cents to make and twenty five more to play through. Every model
call logs its own `usd`, and `--fill` prints the bill before it starts. See
D-084.

**The four layers**

| Layer | State |
|---|---|
| Generation | seven shapes, dealt material, and self-correcting retries |
| Play | five suspects, notebook, searchable transcript, notes, map, evidence |
| Resolution | name the killer, write the reason, judge it yourself |
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
| V9 | One room, one moment, one private scene | fails, from the proposed phase |
| V10 | Nobody is in the room with the body | fails, from the proposed phase |
| V11 | Every lie covers a real secret | fails, from the proposed phase |
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
| A15 | The building hangs together: doors, and one piece | reports |
| A16 | At least three of them look guilty, the killer included | reports |
| A17 | The case has a second half: layered, and one chain two deep | reports |
| A18 | Three of them have both a reason and the chance | reports |
| A19 | A web, not a wheel: they know things about each other | reports |
| T1 | Mutual alibi: somebody actually vouches for the killer | reports |
| T2 | Mutual alibi: the corroborator can be broken from their own side | reports |
| T3 | False confession: the confessor is not the killer | reports |
| T4 | False confession: the confession can be disproved | reports |
| F1 | Frame: the killer tells no lie of their own | reports |
| F2 | Frame: somebody else is carrying enough to be framed | reports |
| W1 | Finder: the one who found the body is the killer | reports |
| W2 | Finder: the finding story can be contradicted | reports |
| C1 | Conspiracy: they are all covering one thing | reports |
| C2 | Conspiracy: the shared lie is not the motive | reports |
| C3 | Conspiracy: somebody has a private thread to pull first | reports |
| H1 | Wrong hour: nobody lies about where | reports |
| H2 | Wrong hour: the real time can be established, and produced | reports |
| H3 | Wrong hour: the killer's alibi for the believed hour is real | reports |
| S1 | There is a secret the player can get with nothing in hand | reports |
| S2 | No secret is sealed behind a loop or a missing gate | reports |
| S3 | The motive is reachable | reports |
| S4 | Every lie covers something that can surface | reports |
| S5 | A gate the player can produce, not only argue with | reports |

**Numbers nobody has justified**

`STICKINESS = 0.75`, `MAX_MOVES_PER_CHARACTER = 2`, `ALIBI_GAP_RANGE = (2, 4)`,
`MIN_SUSPECTS_WITH_A_STAKE_IN_THE_VICTIM = 0.5`, `INNOCENT_LIARS = 2`,
`MIN_SUSPECTS_WHO_LOOK_GUILTY = 3`,
`MIN_SHARE_GATED = 0.4`, `MIN_DEPTH = 2`,
`MIN_SHARE_ABOUT_EACH_OTHER = 0.3`.
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
3. **Does persuasion work now.** D-089 tells a character how worked over they
   are and lets `under_pressure` decide what that does, and reworded every
   condition from a lock into the fastest way in. Nothing counts and nothing
   unlocks. `agent.folded` logs `after=N`: folding on question two, repeatedly,
   means it went too far, and never folding means it did not go far enough
4. What else is built and never called. The end-to-end test (D-070) covers the
   library seams; nothing yet covers `main()` in either entry point
5. Two more shapes, both needing a model change rather than a paragraph: the
   moved body, and the unpinned time of death

**How to check the state of things, cheapest first**

    uv sync                                   # httpx is new
    uv run pytest                             # 317 tests, no network, no spend
    uv run ruff check .
    uv run python -m mystery.cli --topologies
    uv run python -m mystery.cli --material 3 --setting "a residency"  # what 3 seeds get dealt
    uv run python -m mystery.cli --casts      # every saved cast, side by side
    uv run python -m mystery.cli --dry-run    # the whole pipeline, no key needed
    uv run python -m mystery.cli --setting "a residency" --topology mutual_alibi
    uv run python -m mystery.cli --today      # today's case, and what is queued
    uv run python -m mystery.cli --fill --setting "a residency"  # top the shelf to four
    uv run python -m mystery.web --daily      # serve today's, never generate
    uv run python -m mystery.web --cases      # what you have already got
    uv run python -m mystery.web --case <name> # play it again, no model, no wait
    uv run python -m mystery.web --dry-run    # play the shipped case
    uv run python -m mystery.web --setting "a residency" --topology mutual_alibi --art
    uv run python -m mystery.cli --bundle NAME    # carry a case to another machine
    uv run python -m mystery.cli --unbundle F.zip # and unpack it there

Every command that generates a case keeps it: `--cases` is empty only because
nothing has been generated since the shelf existed. A draft is about twenty five
cents, and `--fill` says so before it starts (D-084, re-measured in D-110).

`--art` costs about seven cents a case at the default `--art-quality low`,
four times that at medium and fifteen times at high. Six images: a portrait
each, and one establishing shot of the place (D-102). It prints the estimate
before spending and never regenerates pictures already on disk. See D-082.

The CLI and the web game share `var/mysteries`, so a case inspected with the
first is free to start with the second, as long as every flag matches.

**Standing rules**

- The player always arrives after the body has been found. They witnessed
  nothing; everything they know, they were told. See D-109
- A setting is a phrase, not a placeholder. `"..."` is refused before anything
  is spent, and both entry points print the setting they were given. See D-110
- The person asking the questions is not one of the cast. A suspect is told what
  the visitor is and nothing written to the player in the second person. See
  D-111
- Every number about the house comes from `common_ground` and nowhere else. A
  suspect who is asked for a figure that is not written down says they would
  have to check. See D-111
- Nobody lies about where they were for no reason. See D-111
- An object put in front of somebody always reaches their prompt, whether or not
  it opens a gate, and can move them beyond the gates the generator wrote. It
  never buys a fact about who was where, and never the killer's motive. See D-112
- The hand shows what a thing is and where it came from, and never what to do
  with it. See D-112
- A breaking point is the shape of what gets past somebody, never a password.
  No required gesture, order of words, or phrasing. See D-113

**Errands, not gates**

- V0
- Blind replay of a third prototype. See D-020
- The murder hour is derived in one place now. Grep for it before trusting that
- Stages 4 and 5, AWS and the daily shared case, untouched
