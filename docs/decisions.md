# Decisions log

Every non-obvious choice, two sentences, with what was rejected. Code comments
reference these by ID, for example `# D-004: threshold is 2 on purpose`.

Never edit an entry. If a decision changes, mark it superseded and add a new
one.

---

## D-001 Portfolio piece first, product later
**Date:** 2026-08-26
**Decision:** Target stages 1 to 2 plus a rough AWS deploy, and do not design
for multi-user or a daily shared game yet.
**Why:** Designing for users who do not exist is the most common way this kind
of project dies before it is demoable.
**Insurance taken:** Core logic (generator, validator, agents) stays pure, data
in and data out, with no file, network or print calls, so a later product
version does not require a rewrite.
**Status:** active

## D-002 No LLM orchestration framework
**Date:** 2026-08-26
**Decision:** Plain provider SDK calls plus Pydantic, no LangChain or LangGraph,
despite prior LangGraph experience.
**Why:** The orchestration here is a for-loop over N agents, and every framework
layer makes it harder to mock the LLM boundary, which is exactly the testing
skill this project exists to build.
**Rejected:** LangGraph (complexity unearned at this scale), LangChain.
**Status:** active

## D-003 Pydantic models as the spine, not dicts
**Date:** 2026-08-26
**Decision:** Ground truth is a typed Pydantic model end to end; generation uses
schema-constrained output and parses into it.
**Why:** Validator tests become trivial to write because a deliberately broken
mystery can be constructed in five lines in a fixture.
**Status:** active

## D-004 Frontier model for generation, local model for interrogation
**Date:** 2026-08-26
**Decision:** Use a strong hosted model for ground truth generation and treat
Ollama as the candidate for the interrogation loop, not the other way round.
**Why:** Generation is one call per game so its cost is negligible, while a weak
generator produces incoherent ground truth and makes it impossible to tell
whether a validator failure is the validator's fault or the generator's.
**Follow-on:** The knowledge-leakage test suite doubles as the model selection
instrument, which turns the routing decision from an assertion into a measured
result.
**Status:** active

## D-005 Cache a corpus of generated mysteries for validator development
**Date:** 2026-08-26
**Decision:** Generate roughly twenty mysteries once, freeze them to disk, and
develop and test the validator entirely against that corpus.
**Why:** The validator needs no LLM calls at all, so this removes almost all
development cost and makes the test suite deterministic and runnable offline.
**Status:** active

## D-006 Paper prototype before schema design
**Date:** 2026-08-26
**Decision:** Hand-build and play one mystery on paper before designing the
ground truth JSON schema.
**Why:** The schema will otherwise be invented from imagination, and the fields
that turn out to matter are the ones discovered when a real player asks a
question the cards cannot answer.
**Status:** active

## D-007 Claude drafts working code from Federico's pseudocode
**Date:** 2026-08-26
**Decision:** Federico writes rough or pseudocode for the validator, its tests,
and all of the AWS and CI work; Claude turns it into running code and supplies a
short note on what changed and why. Claude authors generator plumbing, agent
scaffolding and the frontend outright.
**Why:** The learning sits in the diff between the draft and the working
version, and the three named gaps (AWS, testing, observability) close only by
doing rather than by reading.
**Status:** active

## D-008 Solver generates the movement grid, not the LLM
**Date:** 2026-08-26
**Decision:** Split generation into three stages: LLM invents cast, wants,
secrets and the murder; a deterministic solver lays out the movement grid to
satisfy the solvability constraints; LLM writes the surface phrasing of clues
and dialogue.
**Why:** Building the paper prototype showed the creative layer takes minutes
and the combinatorial layer is genuinely hard, which is precisely the split
between what LLMs do well and badly, so asking one model for the whole ground
truth puts the failure exactly where the project can least afford it.
**Consequence:** Mysteries become solvable by construction rather than by
rejection sampling. The validator remains, guarding the LLM-authored layers and
catching semantic contradictions the solver does not model, but it is no longer
compensating for a fundamentally unreliable generator.
**Rejected:** Generate-then-validate with retries, which would have meant
debugging the validator against incoherent input.
**Status:** active

## D-009 Clues are a dependency graph, not a flat set
**Date:** 2026-08-26
**Decision:** The schema represents prerequisite relationships between clues,
so a clue can be present but meaningless until another is known.
**Why:** Prototype 01 has a two-layer structure where the killer's motive is
invisible until the player has cracked an unrelated-looking affair, and that
gating is what makes the misdirection work rather than being decoration.
**Note:** This field would not have been invented from imagination. It came
out of hand-building one case, which is the justification for D-006.
**Status:** active

## D-010 The murder should be unpremeditated where possible
**Date:** 2026-08-26
**Decision:** Prefer ground truths where the killer's motive comes into
existence during the event rather than before it.
**Why:** An unplanned murder means the killer has no prepared alibi, so their
cover story is improvised and therefore has the seams that make it breakable
under combined testimony.
**Status:** provisional, revisit after playtesting whether this holds as a
general rule or was specific to prototype 01

---

*Everything below came out of playing prototype 02 to a solution on 26 August.
Full reasoning in `findings-playtest-01.md`.*

## D-011 Location is two-level, not one
**Date:** 2026-08-26
**Decision:** A character's position is a place plus a position within it, and
the observation derivation rule accounts for the difference.
**Why:** The single-room grid was too coarse to answer a natural player question
four separate times in one playthrough, including a suspect behind her own door
off a corridor and a killer who left a room and came back inside one time slot.
**Status:** active

## D-012 Private knowledge is three-state with break conditions
**Date:** 2026-08-26
**Decision:** Model knowledge as does-not-know, knows-and-will-say, and
knows-and-will-conceal, with an explicit condition under which concealment
breaks.
**Why:** A character revealing something she knows and meant to hide looks
identical in a transcript to an agent leaking something it never should have
known, and they are opposite events that a two-state model cannot distinguish.
**Note:** Observed break conditions were not uniform. One held four rounds and
went under a direct named press, another went sideways under an emotional
question. The condition is per character, not global.
**Status:** active

## D-013 Refusal is a first class agent behaviour and must be tested
**Date:** 2026-08-26
**Decision:** Ground truth must be complete with respect to reachable questions,
and where it is not, the agent detects it is off the map and declines rather than
improvising. Tested explicitly in the agent suite.
**Why:** During play, ground truth was invented twice to cover questions that
reached past what was written, and one of those inventions cohered so well with
the existing facts that it was indistinguishable from design. An agent with only
its own card and no incentive to be careful will do this constantly.
**Status:** active, and highest priority among the agent tests

## D-014 Agents have wants, not only knowledge
**Date:** 2026-08-26
**Decision:** Each agent carries a goal and a stake alongside its knowledge set.
**Why:** The most alive moments in the playtest came from a suspect who asked the
player a question, opened a negotiation, and eventually volunteered decisive
evidence because it served her, none of which was designed and all of which
emerged from a card whose secret conflicted with its self interest.
**Status:** active

## D-015 Player stance affects what suspects disclose
**Date:** 2026-08-26
**Decision:** Some model, however crude, of how the player is treating a suspect
feeds into what that suspect will part with.
**Why:** A clue held for five rounds was released when the player named the
suspect's stakes accurately and framed pressure as help, which is a social move
rather than an informational one. Without this the game is a search interface
with roleplay on top.
**Status:** active, mechanism undecided

## D-016 Agents get read access to a shared public record
**Date:** 2026-08-26
**Decision:** Alongside private knowledge, an agent can see what has been
established in front of it, what it has itself claimed, and what is common
knowledge in the fiction.
**Why:** The player bluffed a suspect with a false assertion about the state of
the investigation and it landed unchallenged, because the agent had no view of
anything outside its own card. Without a public record, bluffing always works and
the game is trivially exploitable.
**Tension:** This cuts against the founding principle that each agent knows only
its own knowledge, and the naive implementation reintroduces exactly the leakage
that principle prevents. Needs careful design.
**Status:** active, design open

## D-017 Inspectable world objects are part of ground truth
**Date:** 2026-08-26
**Decision:** Objects, rooms and documents the player can examine have pinned
content in the ground truth, generated with the case rather than at inspection
time.
**Why:** The player stopped interrogating and went to look inside a van, and the
contents had to be invented on the spot. In a generated game the model will
supply whatever seems dramatically appropriate, which is the fastest available
way to break a mystery.
**Note:** Physical verification is not neutral. The van corroborated the killer's
true confession to a lesser crime and made him more credible.
**Status:** active

## D-018 Variety is structural, not cosmetic
**Date:** 2026-08-26
**Decision:** The generator's first draw is a solution topology from a library,
and the cast is generated to fit that shape rather than the other way round.
**Why:** Prototypes 01 and 02 shared a genre, a cast size and a slot count and
felt clearly different, and the difference was the shape of the solution and the
killer's disposition rather than the setting. Setting is the axis the LLM is best
at and therefore the one to rely on least for real variety.
**Status:** provisional, topology library not yet enumerated

## D-019 Open: notebook versus solver
**Date:** 2026-08-26
**Question, not yet decided:** The contradiction tracker is specified to flag
self contradictions and cross character contradictions automatically. If the
software finds every contradiction for the player, what is left for the player to
do.
**Why it matters:** The decisive break in the playtest was found because a
notebook placed two conflicting claims in adjacent rows. Deduction here is a
memory problem before it is a reasoning problem, so how much memory the software
provides is the difficulty dial for the entire game.
**Status:** open, and it gates the interface design

## D-020 Blind replay demoted from gate to errand
**Date:** 2026-08-27
**Decision:** The blind replay of a third prototype is no longer the next action.
It happens some evening, and nothing waits for it.
**Why:** The test as specified was slightly wrong. It removed the notebook, but
the notebook is a designed feature that will exist in the finished game, so the
condition being tested is one that will never occur. What actually contaminated
the first playtest was the out of fiction commentary and the nudges, not the
claim log.
**Also:** No downstream work depends on the outcome. Schema, validator, fixtures
and solver are built identically whether it scores well or badly.
**Supersedes:** the NEXT line in STATE.md as of 26 August.
**Status:** active

## D-021 First validator rule is event/timeline agreement
**Date:** 2026-08-27
**Decision:** The first rule implemented is V1, that every narrative event's
participants must be placed in that event's room at that event's time slot.
**Why:** It is the failure that actually occurred in the hand-built prototype 02
and went unnoticed until interrogation surfaced it, so it is motivated rather
than hypothetical. It also requires the smallest data model that everything else
will be built on, and its logic is simple enough that the first unit of work
stays focused on pytest and Pydantic mechanics rather than on the rule itself.
**Rejected as first rule:** the alibi breakability rule, which needs claims,
contradiction and independence machinery before it can be expressed at all.
**Status:** active

## D-022 The LLM supplies narrative constraints, the solver satisfies them
**Date:** 2026-08-27
**Decision:** The LLM does not produce the movement grid, but it does produce
the list of things that must happen and to whom: a tryst, private, mid-evening;
a confrontation with exactly one overhearing witness; a discovery. These are
constraints expressed as desired events. The solver then finds a grid satisfying
both the hard solvability constraints and every narrative constraint at once.
**Why:** A pure constraint solver produces a valid and soulless grid. The reason
the hand-built prototypes felt motivated is that every movement existed to make
something happen, and that intent has to come from somewhere. It comes from the
LLM, as input to the solver rather than as output alongside it.
**Refines:** D-008, whose three-stage split was too coarse. The real split is
what must happen (LLM), where and when so that everything holds (solver), and
how it reads (LLM).
**Consequence:** `Event` is not an annotation on the timeline, it is the
solver's input. Rule V1 is therefore the acceptance test on the solver's output,
not merely a guard against hand-written typos.
**Consequence:** Unsatisfiable constraint sets become a first class failure. The
solver reports which constraint it could not place, and the system relaxes or
regenerates that one rather than discarding the whole mystery.
**Status:** active

## D-023 Rules are classified by who they protect against
**Date:** 2026-08-27
**Decision:** Every validator rule records whether it is guarding LLM output,
our own solver, or a file a human edited. V0, grid completeness, runs at the
parse boundary rather than after the solver.
**Why:** If the solver builds placements over the full cross product of
characters and slots, a hole in the grid is structurally impossible, so a rule
checking for one would be guarding our own deterministic code and is better
written as a test of the solver. The same hole is entirely possible in a JSON
file from the cached corpus or edited by hand, which is untrusted input and
where the rule belongs.
**Consequence:** Ask of every new rule which of the three it catches. Rules that
only guard our own code usually want to be solver tests instead.
**Status:** active

## D-024 Constraints are underspecified; binding them is the solver's job
**Date:** 2026-08-27
**Decision:** `Event` becomes `Constraint`, with `place` and `slot` optional. An
unbound constraint is what the language model emits; a bound one is what the
solver produced. Rule V3 fails any constraint still unbound in a finished
mystery.
**Why:** `Event` had place and slot as required fields, which made it a
description of the solver's output rather than of its input, and D-022 says the
model must not choose rooms and times. "A tryst, private, mid-evening" is a real
constraint with both fields empty. Conflating the constraint with its solution
meant the code contradicted the architecture note.
**Consequence:** The question of whether `Alone` deserves its own type dissolves.
`people=["alex"], exclusive=True` is the same predicate over a one-element set,
and no new type or rule is needed. A separate `Alone` would have been a naming
convenience for the prompt masquerading as a type distinction.
**Consequence:** Unsatisfiability stops being silent. V3 is the solver saying
out loud which constraint it could not place, which is what makes relaxing one
constraint possible instead of discarding the mystery.
**Note:** This came out of asking whether `Alone` should be its own type. The
answer was that the question could not be settled because the model underneath
it was wrong. Worth remembering as a pattern: a question with two equally good
answers is often a question resting on a bad distinction.
**Status:** active

## D-025 Free placement has inertia
**Date:** 2026-08-27
**Decision:** A character with no constraint governing where they are in a slot
stays where they were in the previous slot 75% of the time, rather than being
placed at random.
**Why:** The solver's first output passed every test and read as nonsense, with
one character crossing four rooms in four slots for no reason. Every rule was
satisfied and nothing in the suite noticed, because valid was never the goal.
**Consequence:** Numbers like this one, the stickiness, the number of
independent contradictors an alibi needs, the number of suspects who must be
concealing something, are not correctness and cannot be tested. They are the
difference between a mystery that plays and one that does not, and the only way
to tune them is to generate output and look at it.
**Status:** active, value unjustified beyond "the grids read better"

## D-026 Rules run in phases
**Date:** 2026-08-27
**Decision:** `validate(mystery, phase=...)` runs `DRAFT_RULES` or
`SOLVED_RULES`. A draft's constraints must be unbound; a solved mystery's must
all be bound.
**Why:** The two states have opposite expectations, so a single rule list would
have to contradict itself. V5 requires no constraint to carry a place; V3
requires every constraint to carry one. Both are correct, in different phases.
**Consequence:** V4 (referential integrity) runs in both, and is the first rule
in the project whose job is catching the model rather than our own code.
**Status:** active

## D-027 The model boundary is a plain callable
**Date:** 2026-08-27
**Decision:** `Drafter` is `Callable[[GenerationRequest], dict]`. The real
implementation calls Anthropic with a schema-forced tool call; tests inject a
fake. The Anthropic SDK is imported lazily inside the factory.
**Why:** The whole test suite runs offline, free, and in a tenth of a second,
with no API key present. A suite that needs a key stops being run. This is the
concrete payoff of D-002, no orchestration framework: nothing sits between us
and the boundary we need to fake.
**Also:** Output is schema-forced rather than requested as JSON in prose. The
Pydantic schema goes to the model as a tool definition with `tool_choice` set,
and `placements` is stripped from that schema, because a field the model cannot
see is a field it cannot hallucinate into.
**Status:** active

## D-028 Model responses are cached to disk by request hash
**Date:** 2026-08-27
**Decision:** `generate(..., cache_dir=...)` writes each parsed mystery under a
hash of the request and reads it back on a repeat.
**Why:** Developing the solver and validator needs a corpus, not a live model,
and a corpus costs money once (D-005). `var/` is gitignored for now; a curated
subset moves to `tests/fixtures/` when the shape settles.
**Status:** active

## D-029 The model proposes the grid; the solver repairs it
**Date:** 2026-08-27
**Decision:** The model writes the timeline as part of writing the story, and
the solver takes that proposal and moves only the cells that break a constraint.
Minimal-conflict repair, not generation. The build-from-nothing path stays as
the fallback for when no grid arrives.
**Why:** Federico's observation, and it is correct. The hand-built prototypes
were good precisely because every placement had a reason: someone slips to the
storeroom *because of the affair*. A constraint list cannot carry those reasons,
so a solver working from one produces motion without motive. The model is the
only component that knows why anyone is anywhere.
**Why it is safe:** because the validator already exists. The reason to distrust
model-written grids was the prototype 02 contradiction, which went unnoticed on
two rereads. That failure is now caught mechanically by V1, so the model's
weakness is covered and its strength is not thrown away.
**Supersedes:** the part of D-008 and D-022 that said the model must never touch
placements. The split was drawn in the wrong place: the model is bad at *global
consistency checking*, not at *choosing rooms*.
**Consequence:** STICKINESS (D-025) is revealed as a crude proxy for narrative
motivation and now applies only to the fallback path. Where the model proposes,
real reasons replace it.
**Consequence:** `_tool_schema` no longer strips `placements`.
**Status:** active

## D-030 V5 retired one session after being written
**Date:** 2026-08-27
**Decision:** `check_draft_constraints_are_unbound` is deleted. Phases renamed
from draft/solved to proposed/final, and the proposed phase runs referential
integrity only.
**Why:** V5 forbade the model from binding constraints. Under D-029 that is
exactly what the model is now asked to do, so the rule was backwards. Rejecting
a proposal for breakages the repairer exists to fix would also throw away
proposals that are one small move from correct.
**Note:** Worth leaving in the log rather than quietly deleting. A rule written
on Wednesday and deleted on Wednesday is what it looks like when a design
assumption turns out to be wrong, and the log is more useful if it records the
reversals as well as the wins.
**Status:** active

## D-031 Advisories are separate from rules
**Date:** 2026-08-27
**Decision:** `critique.py` holds quality checks that report and never fail.
`validator.py` holds correctness rules that fail. The CLI prints "Valid" and
then, separately, "Valid, but:".
**Why:** The two are different questions and conflating them makes both worse.
Every quality check rests on a threshold somebody invented: two moves per
character, two to four people without an alibi. Those are arguable, and a rule
that fails a mystery over an arguable number is a rule that gets deleted the
first time it is inconvenient. An advisory that reports one is a measurement you
can watch and disagree with.
**Why it matters more than it sounds:** the first real generated case was valid
and had a character discovering the body halfway through the evening under
investigation. The solver's first grid was valid and read as five random walks.
Valid was never the goal, and this is the first place in the project that says
so in code.
**Consequence:** the answer to "how would you know STICKINESS is wrong" is that
you write the advisory that measures what it was trying to buy, and then you can
see it.
**Status:** active

## D-032 Killer and victim are fields, not a naming convention
**Date:** 2026-08-27
**Decision:** `Mystery.killer` and `Mystery.victim` are explicit optional fields.
**Why:** Nothing in the model identified who did it. Any check that asks a
question about the murder rather than about the grid was impossible to write,
which surfaced the moment the first advisory needed to ask who lacked an alibi
at the time of the killing. Knowledge derivation, the reveal, and the clue post
mortem all need this too.
**Status:** active

## D-033 A clash reschedules a scene rather than rejecting the mystery
**Date:** 2026-08-27
**Decision:** When two constraints require the same person in two places at the
same moment, the solver keeps the more load-bearing one and finds the other a
new place and slot. V6 moves out of the proposed-phase rules and stays in the
final ones, so it reports only a clash that survived repair.
**Why:** A real generated case died on exactly this: one character was needed in
the back office confronting someone and in the main gallery overhearing a threat
at 20:20. Both scenes were good. Neither needed rewriting. They simply could not
both happen at once. Rejecting the whole case for a scheduling conflict throws
away twenty five good cells to fix one bad pair.
**Ranking used:** the murder never moves, since the case is arranged around it.
Then exclusive scenes over open ones, because privacy is what makes a moment
matter. Then larger scenes, because they are harder to reschedule.
**Consequence:** rescheduling is allowed to move people, unlike the first repair
pass. A scene deleted from the story is worse than a character standing in a
different room.
**Refines:** D-022, which said unsatisfiable constraints should be relaxed one at
a time rather than discarding the mystery. That was written in August and not
implemented until the failure actually happened.
**Note on rules generally:** every rule should say not only who it guards
against (D-023) but who can *fix* it. A bad character reference can only be
fixed by the model. A scheduling clash can be fixed by the solver. Those belong
at different phases, and getting that wrong is what made this one fatal.
**Status:** active

## D-034 The victim's story ends at the murder, enforced in two places
**Date:** 2026-08-27
**Decision:** V7 fails any case where the victim appears in a scene after the
murder slot, or where the body moves. The solver also pins the victim in the
murder room for every subsequent slot, and refuses to reschedule a
victim-involving scene to after the killing.
**Why:** A generated case had the victim strangled in the vault at 20:30, walking
to the main gallery at 20:45, and returning to the vault at 21:00 to blackmail
somebody. Every existing rule passed it. This is the single most obvious thing
that can be wrong with a murder mystery and nothing was watching for it.
**Both places on purpose:** the rescheduler introduced by D-033 can move a scene
to a later slot, so it can create this failure itself. The solver prevents it and
the rule is the backstop, because a check that only exists in the component that
causes the fault is not a check.
**Status:** active

## D-035 The prompt is part of the cache key
**Date:** 2026-08-27
**Decision:** `GenerationRequest.cache_key` hashes the request together with the
system prompt.
**Why:** It did not, so after rewriting the prompt every previously generated
seed kept returning its old draft. The observed symptom was a case with no
secrets and no false claim being reported as fine, generated under instructions
that predated both. Prompt changes were silently having no effect.
**Status:** active

## D-036 An advisory that goes quiet on missing data is worse than one that fires
**Date:** 2026-08-27
**Decision:** A4 and A5 report when the fields they inspect are absent, instead
of returning early.
**Why:** They were written to skip a case with no secrets, on the reasoning that
there was nothing to judge. The effect was that the worst possible case, one with
no motives at all, produced a clean bill of health. Absence of data is not
absence of a problem.
**Status:** active

## D-037 Generation retries with its own failures fed back
**Date:** 2026-08-27
**Decision:** `Drafter` takes the request plus a list of complaints about its
previous attempt. `generate` parses, runs proposed-phase validation, and on
failure sends the reasons back to the model, up to three attempts, then raises
`GenerationFailed` carrying the last set of problems.
**Why:** Two real failures in one afternoon that nothing downstream could fix. A
constraint naming a character who does not exist can only be corrected by the
model. A response arriving wrapped in a stray `$PARAMETER_NAME` key is not
anybody's fault and simply needs another go. Neither is the user's problem and
neither should end a run.
**Why it was nearly free:** the violation messages were already written to be
read by a person, so they work unchanged as instructions to the model. That was
an accident of writing good error messages and it paid for itself.
**Also:** a degenerate wrapper is unwrapped rather than retried, because it is
cheaper than another twenty five second call. And nothing is cached until it has
passed validation, since caching a broken draft would make that seed permanently
broken.
**Completes:** the rule taxonomy from D-023 and D-033. Every failure now goes to
whoever can fix it: the solver reschedules clashes, the model corrects its own
inventions, and only a failure nobody can fix reaches the user.
**Status:** active

## D-038 Knowledge is derived, never generated
**Date:** 2026-08-27
**Decision:** `knowledge.py` computes what each character saw from co-location in
the grid. No model is involved. Observations are things a character knows and
will say; `conceals` are things they know and will not; anything absent is a
thing they do not know (D-012).
**Why:** The facts must be computed and only the voice generated. An agent that
produces a fact outside its derived knowledge is leaking, and that is only
detectable if the boundary of what it knows is a data structure rather than a
paragraph in a prompt.
**Detail:** the victim stops observing at the moment they die. The body is still
in the room and other people still see it, but it testifies to nothing.
**Status:** active

## D-039 A witness with nothing to hide is what makes a case trivial
**Date:** 2026-08-27
**Decision:** `Knowledge.is_credible` is true when a character holds no secret of
their own. A7 fires when any contradictor of the killer's alibi is credible.
**Why:** This is the mechanism behind the original brief's "no single clue is
individually conclusive", and it took two prototypes and a week to see it. In
Opening Night every witness against Wouter was compromised: Renske had lied about
her whereabouts for three rounds, Ilse had just admitted hating the victim.
Neither could settle it alone, so the player had to combine them. That was not
decoration, it was the entire reason the case was fun.
**Consequence:** the generator's job is not only to arrange rooms so an alibi can
be broken, but to make sure everyone who could break it has a reason not to be
believed.
**Status:** active

## D-040 A7 replaces A2 as the real check on solvability
**Date:** 2026-08-27
**Decision:** A7 analyses the killer's false claim against derived knowledge:
who could contradict it, and whether any single one of them settles it. A2, which
counted characters without an alibi, stays as a cheap signal but is no longer the
project's answer to its own founding constraint.
**Why:** The brief said the killer's alibi must be falsifiable from combined
testimony but not from any single one. That was unwritable without knowledge
derivation, and A2 was a proxy that measured something adjacent. It has taken
until now to check the thing the project was actually specified around.
**Status:** active

## D-041 Agents must cite the facts they use
**Date:** 2026-08-27
**Decision:** A character's brief is a numbered list of licensed facts with ids.
The agent returns speech plus `used`, the ids it drew on. `leaks()` reports any
id outside the licensed set, and separately any id belonging to concealed
material.
**Why:** Knowledge leakage was the project's third named hard problem and had no
detector. Free prose cannot be checked without a human reading it, and "could
this character know that" is a judgement call made at midnight. With citations it
is set membership.
**Honest limits, recorded rather than discovered later:** a model can cite
correctly and still say something unlicensed in the prose. Citation catches the
common failure, not every failure. The prose-level check remains unsolved.
**Status:** active

## D-042 The killer's brief contains the lie, not the truth
**Date:** 2026-08-27
**Decision:** For the slot the killer lies about, the sayable fact is the false
claim. The true location appears only among concealed material, and observations
from that slot are withheld entirely.
**Why:** An agent handed both the truth and the instruction to lie will hedge,
and a hedging killer is spotted in one question. Withholding the observations
matters just as much: Otto saw Magnus in the cellar, and citing that would place
him there.
**Consequence:** the false claim stops being decoration on the ground truth and
becomes the thing that actually drives the killer's behaviour.
**Status:** active

## D-043 Concealed material is in the prompt and never citable
**Date:** 2026-08-27
**Decision:** A character's own secrets appear in the brief, under CONCEALED,
without citable ids.
**Why:** A character has to know their own secret in order to deflect around it.
Vera cannot be evasive about an affair she has not been told about. That means
the prompt contains exactly what the answer must not reveal, which is a genuine
risk rather than an oversight, and it is what the leakage suite measures.
**Status:** active, and the riskiest thing in the module

## D-044 A character has two halves and they come from different places
**Date:** 2026-08-27
**Decision:** `Character` gains `wants`, `manner` and `under_pressure`, authored
by the model at generation time. The brief renders them above the derived facts.
**Why:** The agent boundary was built with derived knowledge only, and the
resulting brief was a witness reciting locations. The hand-built cards had a
second half: Renske was cold and precise and would trade rather than give, Ilse
performed composure that was costing her, Wouter was helpful about everything
that cost him nothing. Every interesting moment in the playtest came from that
half, and none of it can be computed from a grid.
**The split holds:** facts derived and never invented, person authored and never
derived. Same rule as D-029 at a smaller scale.
**Status:** active

## D-045 Every secret carries its breaking point
**Date:** 2026-08-27
**Decision:** `Secret.breaks_when` states the condition under which its holder
stops concealing it, and the brief renders it inside the concealed item.
**Why:** D-012 said concealment needs a break condition and it was never
implemented, so a concealed secret was a wall. Renske gave up the lighting box
the moment the questioner traded her Wouter's claimed location; Ilse gave up her
sighting when her stakes were named accurately. Those are different conditions on
different characters, which is why it belongs on the secret rather than in the
system prompt.
**Consequence:** a secret with no breaking point renders as "You do not give this
up", which is a legitimate choice and now a visible one rather than a default.
**Status:** active

## D-046 Two advisories were measuring the wrong thing
**Date:** 2026-08-27
**Decision:** A5 selects the killer's motive by an explicit `Secret.is_motive`
flag rather than taking the first secret it finds. A3 checks the `secrets` list
rather than inferring "has something to hide" from exclusive constraints, and the
opportunity half splits out into A8.
**Why:** Both were false-positiving on real output and neither was noticed until
two cases were read side by side. A5 flagged the killer's *background* secret as
ungated while the actual motive sitting next to it was correctly gated. A3
predated the secrets layer entirely and reported characters as concealing nothing
while they held a documented secret.
**The general lesson:** an advisory written before the data it should read exists
will quietly keep reading the old data. Both of these passed their tests the
whole time, because the tests were written against the same wrong assumption.
**Status:** active

## D-047 An unbreakable lie is repaired by moving it
**Date:** 2026-08-27
**Decision:** After solving, if the killer's claimed room had fewer than two
other people in it, the solver relocates the claim to a room that did, preferring
one whose occupants are all concealing something.
**Why:** A real generated case had the killer claim an empty room. Nobody could
contradict them, so the case was unsolvable no matter how many questions a player
asked, and A7 said so. The model had followed every instruction it was given.
**Why this is safe to move, unlike anything else in the timeline:** the room a
killer *names* carries no story. Nothing happened there, no scene depends on it,
nobody's motive references it. It is the one piece of a mystery that is pure
mechanism, so it can be chosen mechanically.
**Preference order:** at least two witnesses, then all witnesses compromised, then
more witnesses. Straight from D-039.
**Status:** active

## D-048 The tracker does the remembering; the player does the deciding
**Date:** 2026-08-27
**Decision:** D-019 is settled. The notebook automatically reports proven
contradictions, and separately reports unconfirmed claims as leads without
drawing conclusions from them.
**Why:** The open question was what is left for the player if the software finds
every contradiction. The answer is that two different things were being confused.
Noticing that two statements disagree is bookkeeping and a player gains nothing
by doing it by hand. Deciding who to press, in what order, and what to trade for
an answer is the game, and the playtest bore that out: the case broke because a
question was asked in the right way, not because a conflict was spotted.
**Status:** active, settles D-019

## D-049 Silence means two different things
**Date:** 2026-08-27
**Decision:** A lead records whether the silent witness has themselves described
that room at that time. If they have not, their silence means nobody asked them.
If they have, and left the claimant out, their account and the claim cannot both
be complete.
**Why:** This is the mechanism that broke prototype 02. Renske described the
lighting box during the interval and Wouter was not in her account of it. The
first version of the tracker collapsed both cases into "unconfirmed", which made
the decisive move look identical to a question nobody had got round to.
**Consequence:** the notebook has two sections rather than one, and the stronger
one is the one that actually solves cases.
**Status:** active

## D-050 Facts carry structure alongside their prose
**Date:** 2026-08-27
**Decision:** `Fact` gains `subject`, `slot` and `place` beside `text`.
**Why:** The tracker needs to compare claims, and recovering meaning by parsing
the sentence back out is how you build something that works today and breaks the
first time anyone rewords a template. The structure travels with the words.
**Status:** active

## D-051 A browser build arrives early, for a playtest rather than for stage 3
**Date:** 2026-08-27
**Decision:** `mystery/web.py` is a single-file FastAPI app holding one game in
memory, serving one HTML page with the notebook as a live panel. No database, no
sessions, no build step, no React.
**Why:** Two people around one laptop want a browser, not a terminal, and a
playtest with someone who has never seen the project is worth more right now than
any amount of further generation work. Stage 3 was scheduled for later; the
reason to pull it forward is a real playtest tonight, not a plan.
**What it deliberately is not:** it is not the stage 3 frontend. It has no
multi-user support and one process holds one case. When the real frontend gets
built it can throw this away, and it will be a better frontend for having watched
someone use this one.
**Also:** `--model` selects the model playing the suspects, separately from the
generator. Sonnet is the default because a suspect answering from a written brief
is a much smaller task than inventing a mystery, and that gap is exactly the
routing question in D-004.
**Status:** active

## D-052 Portraits are drawn, not fetched
**Date:** 2026-08-27
**Decision:** Character portraits are SVG composed at runtime from a hash of the
character id: palette, hair shape, glasses, collar, all deterministic. The
typewriter blip is a square wave synthesised with the Web Audio API, pitched per
character.
**Why:** No image API, no asset pipeline, no files to ship, and it works offline.
A hash also means a character looks the same every time the same seed is played,
which matters more than the portraits being good.
**Rejected:** generated images, which would need another provider, another
budget, another failure mode, and twenty seconds per face.
**Note:** the blips are per-character pitched, so each suspect has a voice you
recognise before you read the nameplate. That was almost free and it does more
for the visual novel feel than the portraits do.
**Status:** active
