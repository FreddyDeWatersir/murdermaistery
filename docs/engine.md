# How a case gets made

What happens between `uv run python -m mystery.web` and a playable evening, in
order, with every number written down. Read `decisions.md` for *why* any of it is
the way it is; this is *what*.

The shape in one sentence: **a seed deals the raw material, one model call writes
the case, arithmetic repairs and checks it, and three gates decide whether it is
allowed to be played.**

---

## 1. The seed deals

Nothing here calls a model. Every draw is `random.Random(f"<label>|{seed}")`, so
the same seed always deals the same hand, and each label gets its own stream so
adding a draw does not shift the others (`palette.py`).

| drawn | from | how |
|---|---|---|
| occasion | 18 written occasions | one |
| manners | 28 | sample, one per suspect |
| voices | 18 | sample, one per suspect |
| motive flavour | 20 | one |
| intrigues | 24 | sample of 3 |
| standing, old business | 12 each | one each |
| where | 16 kinds of building | one |
| **question budget** | `[70, 80, 90, 100, 110, 120, 130, 140, 150, 45, 55]` | one |
| **murder slot** | `randrange(2, slot_count + 1)` | never the first slot |
| **commission** | 8 briefs | one, and `sound` with probability **0.6** |
| **topology** | 7 shapes | `sorted(LIBRARY)[seed % 7]`, unless `--topology` names one |

Two of those are load-bearing and worth knowing by heart. The **murder slot** is
dealt rather than left to the model, because left alone the model put the murder
in slot four ten times out of twelve and the killer necessarily lies about the
hour they killed in, so "who is lying about the second to last hour" solved the
game (D-125). The **commission** is wrong 40% of the time, so what the house
tells you at the door is not reliably what happened (D-129).

The **topology** is the third worth knowing, and until D-154 it was dealt and
then thrown away: the parser handed `--topology` a default, so the `is None`
branch that calls `drawn` was dead and every case ever generated was `the_lie`.
Any base rate measured over drafts from before that fix is a base rate for one
shape, not for the engine.

## 2. The prompt is built, and hashed

`SYSTEM_PROMPT` (31,397 characters) plus a user prompt carrying the drawn
material. **The shape of the solution opens the request**, above the setting,
and says in one line that it overrides anything in the standing instructions
that assumes a different pattern of lying (D-151). It used to sit on the fifth
line while the standing instructions insisted on a pattern four of the seven
shapes forbid, and the shapes lost. The cache key is `sha256(SYSTEM_PROMPT + user_prompt)[:16]`, so
**editing one word of the prompt invalidates every draft ever cached** (D-035,
D-075). That is deliberate: without it, prompt edits silently do nothing because
every seed keeps returning its old answer.

## 3. The cache is checked

A hit returns immediately and costs nothing. On the way out the commission is
run through `unname_the_commission` again, so drafts cached before that repair
existed are still repaired (D-149).

## 4. One model call

`claude-opus-5`, streamed, schema-forced: the `Mystery` schema is handed over as
a tool called `emit_mystery` and the model is required to call it, so malformed
output is rejected by the API before it reaches us.

| | |
|---|---|
| ceiling | `max_tokens=24000` (streamed, because the SDK refuses a non-streaming call this size, D-148) |
| real size | ~17,900 in, 10,400 to 12,900 out |
| cost | **$0.35 to $0.41 a call** |
| time | about three minutes |
| attempts | **3** |

## 5. Parsed and repaired

Three repairs, all free, all deterministic. `_unwrap` undoes a degenerate wrapper
if the model nested the whole case under one key. Pydantic parses. Then
`unname_the_commission` takes any suspect's name out of the briefing.

The principle these follow, and the one worth taking away:
**repair what has exactly one right answer; complain only about what does not.**
A rejection costs another 38 cent draft, so anything mechanical should never
cause one (D-149).

---

# The three gates

Only three things can stop a case. Everything else is reported.

## Gate 1: the proposed rules

Seven checks run on the model's own draft, before any arithmetic touches it. A
failure sends every complaint back to the model and it redrafts. **This is the
expensive gate: each failure costs about 38 cents.**

| | what it requires | protects against |
|---|---|---|
| V4 | every id named in a constraint exists | the model inventing a character |
| V6 | nobody required in two rooms in one slot | an impossible schedule |
| V9 | one private scene per room per moment | two exclusive scenes colliding |
| V10 | nobody in the murder room after the murder | stepping over the body |
| V11 | every lie names the secret it covers | a dead end the player cannot tell from a live one |
| V12 | no year in a `role` | a fact five people believe and the case does not contain (D-138) |
| V13 | the commission names no suspect | the answer handed over before question one (D-139) |

Three solvability findings ride along in the same complaint list, because the
program already treats them as fatal and used to throw the case away without ever
telling the model (D-149): **S2** a secret that can never surface, **S3** a motive
that can never be reached, **S4** a lie covering a secret that can never surface.

On success the draft is cached. A draft that fails all three attempts raises and
nothing is kept.

## Gate 2: the final rules

The solver runs (see below), then twelve checks: the seven above plus five that
only make sense once the grid is settled.

| | what it requires |
|---|---|
| V1 | everyone in a bound constraint is actually placed there |
| V2 | an exclusive scene has nobody else in the room |
| V3 | no constraint left unbound |
| V7 | nothing involving the victim after the murder, and the body does not move |
| V8 | a lie is actually false, and one person tells at most one |

**A failure here costs nothing.** Drafting is a model call; solving is
arithmetic, so the free half is the half to retry: `solve_until_valid` tries up
to **24 arrangements** in seed order and returns the first that holds (D-147).
Only if all 24 fail does the run stop.

## Gate 3: winnable

```
winnable = killer_is_assailable and motive_is_reachable
```

`solvable.py` computes a **closure**, not a property: start from the secrets
obtainable cold, add whatever those unlock through `revealed_by`, repeat until
nothing changes. Anything still outside is unreachable however many questions are
asked, which catches every cycle and every chain hanging off a gate that does not
exist (D-068).

An unwinnable case is refused, and `--anyway` plays it regardless.

**What this can and cannot know.** Gating is structure and is followed exactly.
Whether a suspect *actually* gives something up depends on `breaks_when`, which
is a sentence in a prompt. So this is a necessary condition, not a sufficient
one: a case that fails is definitely unsolvable, a case that passes is merely not
provably broken.

---

## The solver, in between

The model proposes the whole grid and the solver **moves only what breaks**
(D-029). Two paths: repair when the model supplied placements, build from nothing
when it did not.

The repair path, in order: unbind constraints that clash, settle everyone their
scenes name, rehome the freed constraints, settle again, fill everybody's
remaining holes, and lay the body to rest.

| constant | value | what it does |
|---|---|---|
| `STICKINESS` | 0.75 | chance a character with a free slot stays where they were, so an evening reads as people rather than a random walk |
| `MAX_REPAIR_PASSES` | 8 | settle loops before giving up |
| `SOLVER_TRIES` | 24 | arrangements tried before a draft is declared hopeless |

One rule cuts across all of it: from the murder slot onward the murder room is
**sealed** to everyone but the victim. That was checked by V10 and not enforced
by the solver for months, which is how two paid drafts died in one evening
(D-147).

---

## Testing it without playing a case

`uv run python -m mystery.web --score` solves and measures every draft in
`var/mysteries` and prints a scoreboard. No model, no network, no spend (D-152).

Three things it is for. **Finding bugs the suite cannot**: twenty-five real
drafts are twenty-five shapes nobody designed, and the first sweep found a V10
failure the seal in D-147 had missed. **Setting thresholds from the
distribution**: an advisory firing on 96% of cases is not a check, and the report
says so in the margin. **Seeing a change land**: edit a check, sweep, read what
moved, and if nothing moved across twenty-five cases the change did not do what
you thought.

What it cannot see is whether a case is any fun.

## The advisories: 21 checks that never block

These are the quality layer. They measure the case and print. Nothing here stops
a run, which is deliberate: a rule that fails a case on a judgement call
eventually throws away a good one (D-031). A21 and A23 are retired, not deleted:
they check objects with paths, which nothing has displayed since D-139.

Base rates across the 25-draft corpus are in D-152, and two of these currently
fire on 96% of cases, which means they have stopped carrying information.

**The numeric ones.** These are the dials a difficulty setting would turn.

| | measures | threshold |
|---|---|---|
| **A1** | rooms a character moves between | at most **2** moves in 5 slots |
| **A4** | suspects with a stake in the victim | at least **50%** |
| **A10** | innocents who also lie about where they were | at least **2** |
| **A16** | suspects holding something damning | at least **3** |
| **A17** | secrets behind a gate | at least **40%**, and one chain **2** deep |
| **A18** | suspects with both a reason and the chance | at least **3** |
| **A19** | secrets about another suspect rather than the victim | at least **30%** |

**The structural ones**, which are true or false rather than counted: A2 (someone
was alone at the murder hour), A3 (everyone conceals something), A5 (the motive is
gated), A6 (the killer lies), A7 (the alibi breaks from combined testimony but not
from any single one — the property the whole project was specified around), A8
(everyone has an unwitnessed moment), A9 (every character is a source of
something), A11 (an innocent lie can be resolved, not only detected), A12
(position alone does not convict), A13 (the motive is learnable), A14 (the cast is
not five of the same person), A15 (every room reachable, no room without doors),
A20 (an innocent lies about the murder hour too), A21 (an object has a path), A22
(somebody is wrong without lying), A23 (the objects that move are not all the
killer's).

---

## What a whole case costs

| | |
|---|---|
| draft, one attempt | $0.35 to $0.41 |
| each rejected attempt | the same again, up to 3 |
| art, `low` tier, 6 portraits and a setting | $0.08, once per case, however many people play it |
| solving, validating, advising | **nothing** |
| playing, per question | about 0.9 cents on Sonnet |

The asymmetry is the thing to hold on to: **the draft is one call and everything
after it is arithmetic.** Every design decision about gates follows from that.
Anything a machine can fix should be fixed, anything only the model can fix
should be complained about once and batched with every other complaint, and
anything that is merely a matter of taste should be printed and left alone.
