# What a case costs

Measured, not estimated. Everything here comes from one real drafted case
(`the-gold-bangle-nobody-counted`, six characters, five slots, five places) and
one real played session against it (71 questions, five suspects spoken to).

Play figures are character counts divided by 3.8, which is stated so the
arithmetic can be rechecked rather than believed. **Draft figures are the API's
own numbers**, taken from four real drafts on 4 September, and they are the ones
to trust.

## The three costs

| | model | tokens | cost |
|---|---|---|---|
| Draft, one attempt | `claude-opus-5` | 17,900 in / 10,400-12,900 out | **$0.35 to $0.41** |
| Art, default tier | image, `low` | 6 portraits + 1 setting | **$0.08** |
| Play, 71 questions | `claude-sonnet-5` | see below | **$0.65** |

A full cold case, drafted, illustrated and played once: **about $1.10.** A draft
the validator sends back costs the same again, and the drafter is allowed three
attempts, so a bad night can reach $1.20 before a single question is asked.

**The draft figure here was wrong until 4 September, and by a lot.** It was
estimated at 10,500 input tokens by dividing characters by 3.8; the API reports
17,900. Dense markdown full of identifiers and json runs closer to 2.2 characters
a token than 3.8, so the estimate was out by seventy per cent on the one number
nobody had measured directly. The play figures use the same method and are
probably light for the same reason: they should be replaced with logged
`input_tokens` from a real session at the first opportunity, rather than trusted
as they stand.

## Where the play cost actually goes

$0.65 over 71 questions is **0.92 cents a question**, roughly twice the figure
this project has been quoting. The reason is that it is not flat:

| | stable block | history + question | answer |
|---|---|---|---|
| Question 1 | 4,151 (written to cache) | 682 | 160 |
| Question 70 | 4,151 (read from cache) | 4,332 | 331 |

The stable block is the character's brief: facts, secrets, roster, manner. It is
cached, read at a tenth of the input rate, and its size does not change. It is
not the problem.

The **history** is. Every question re-sends everything that character has already
said, uncached, at full rate. By the seventieth question that is more tokens than
the brief. Total input over a run is quadratic in the number of questions, so the
last ten questions of this run cost more than the first ten despite the answers
being the same length.

## Where the money goes, by block

Same run, broken down. This is what decides which lever is worth pulling.

| | share of $0.65 |
|---|---|
| History, re-sent uncached every question | **34.5%** |
| The answer itself, at the output rate | **28.9%** |
| The character brief, cached | **21.8%** |
| The live block (table, word, pressure) | **14.9%** |

The brief is 4,150 tokens and is 21.8% *despite* being cached, because a cache
write at the 1h rate costs 2x and there is one per character. Caching is still
clearly right: without it the brief alone would be $0.59 instead of $0.14.

## Lever one: stop sending the history verbatim

A character does not need forty of their own paragraphs to stay consistent. They
need the positions they have committed to, which this program already computes:
`Statement.assertions` is exactly that, and `cited` says which secrets they have
already given up. So the history can become a short ledger, derived, with no
summarising model and nothing to drift:

    You put yourself in the corridor at 19:40, 20:00 and 20:40.
    You put Nadia in the corridor at 19:40.
    You have already told them about the letters.
    You have answered 14 questions and refused 2.

**Built, and measured against the real run** (D-140). Three exchanges stay
verbatim, because a ledger alone reads as somebody who remembers the file and not
the conversation:

| questions | verbatim | ledger + 3 | saved |
|---|---|---|---|
| 45 | $0.50 | $0.48 | 4.5% |
| 71 (the real run) | $0.78 | $0.68 | 12.9% |
| 110 | $1.31 | $0.98 | 24.7% |
| 150 (top of the budget band) | $2.02 | $1.30 | 36.0% |

Twelve per cent on the run that motivated it, which is less than the first
estimate. The number that matters is the shape rather than any row: the growing
term is gone, the history block peaks at 1,545 tokens instead of 4,536, and a
long case no longer costs three times a short one. It probably also improves
consistency, since the model no longer has to re-derive what it said from forty
paragraphs.

A smaller cut in the same place: the live block prints its whole paragraph about
objects on the table on every question, including the great majority where the
table is empty. Making those blocks conditional is worth about 6% on its own.

This also supersedes the D-130 caching question. The reason a second breakpoint
looked attractive was the growing history, and a history that does not grow does
not need caching.

## Lever two: a cheaper voice model

The suspects are a `claude-sonnet-5` call each. The same run priced against every
plausible alternative, with each provider's own cache rates applied to the brief:

| model | 71 questions | per question |
|---|---|---|
| Claude Opus 5 | $1.63 | 2.30c |
| Claude Sonnet 5 (today) | $0.65 | 0.92c |
| Gemini 3.6 Flash | $0.46 | 0.64c |
| GPT-5.6 Luna | $0.33 | 0.46c |
| **Claude Haiku 4.5** | **$0.33** | **0.46c** |
| GPT-5.4 mini | $0.25 | 0.35c |
| Gemini 3 Flash | $0.16 | 0.23c |
| Gemini 3.1 Flash-Lite | $0.08 | 0.11c |
| GPT-5.4 nano | $0.07 | 0.09c |
| DeepSeek V4 Flash | $0.03 | 0.04c |

Prices as published in September 2026 and worth re-checking against each
provider's own page before committing to one.

**This lever is five to twenty times bigger than the first one.** It is also the
riskier one, because this workload is unusually hostile to a weak model in three
specific ways:

1. **It must withhold something it can see.** `conceals` is in the prompt by
   necessity, since a character has to know their own secret in order to deflect
   around it. Leaking it is the failure mode, and small models leak.
2. **It must emit a schema-forced tool call with valid citations.** A wrong
   citation is worse than a refusal: it puts a claim in the notebook that the
   character never made, and nothing downstream can tell.
3. **It must lie consistently and sound like a person while doing it.** This is
   the thing the frontier tiers are actually better at, and it is most of what
   makes a case worth playing.

All three are measurable here, which is the point. The leakage suite already
counts one, citation validation counts two, and a played case judges three. The
`Responder` boundary is a plain callable by construction (D-002), so a second
implementation is a small adapter rather than a rewrite.

The sensible order to try: **Haiku 4.5 first** (same API, same caching
semantics, same tool-call behaviour, half the price, near-zero integration risk),
then GPT-5.4 mini or Gemini 3 Flash if Haiku holds up and more is wanted. The
bottom of the table is not for the suspects.

## Both levers together

| | Sonnet 5 | Haiku 4.5 | Gemini 3 Flash |
|---|---|---|---|
| Today | $0.65 | $0.33 | $0.16 |
| With the history compacted | ~$0.46 | ~$0.23 | ~$0.11 |

## What that means for a business model

The shape is unusual and worth being clear about: **the draft is one-time and
shareable, the play is per-player and dominates.** One $0.26 draft can serve
every player who ever opens that case. Every play costs its own $0.65 and nothing
amortises it.

So a free tier is not free. One shared daily case costs $0.26 to write, once, for
everybody, and then $0.65 for each person who plays it. Free-with-ads does not
close a gap that size at any realistic ad rate.

Rough shapes, at today's $0.65 and at a compacted Haiku's $0.23:

| | today | compacted Haiku |
|---|---|---|
| One played case | $0.65 | $0.23 |
| Subscription, 20 cases a month | $13.00 | $4.60 |
| Subscription, 8 cases a month | $5.20 | $1.84 |

A €9.99 subscription with a soft cap around eight cases a month works today and
is comfortable at $0.23. Twenty cases a month does not work today at any price a
person would pay for a game, and works fine at $0.23. Pay-per-case at €1.50 to
€2 has the healthiest margin and the worst conversion, which is the usual trade.

The important consequence: **the model swap is what decides whether a
subscription is viable, not the engineering.** Compaction alone does not get
there; Haiku alone nearly does.

The free funnel that does work is a **shorter** case rather than a rationed one:
a fixed weekly case with a 40-question budget costs about $0.25 to let a stranger
play, and 40 questions is enough to feel the thing without finishing it.

Two things move these numbers on their own and neither is engineering: model
prices fall, and a cheaper voice tier becomes good enough at being a liar. Both
are worth re-measuring rather than assuming.

## Infrastructure

Negligible at this scale and worth stating so it is not worried about. S3 storage
for cases and art is fractions of a cent a month, DynamoDB on-demand at a few
hundred writes a day is under a cent, and Lambda at this volume sits inside the
free tier. The bill is the model, and only the model.
