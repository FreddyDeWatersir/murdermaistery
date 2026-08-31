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

## D-053 Opinions were never inside the knowledge boundary
**Date:** 2026-08-27
**Decision:** The agent prompt splits hard from soft. Facts about who was where
require a citation and may not be exceeded. Everything else, what a character
thought of people, how the evening felt, what they make of being questioned, is
theirs to give freely and is never refused.
**Why:** The first playtest's loudest complaint was that the suspects gave
nothing back. The cause was mine: their entire brief was movements and sightings,
so a question about a *person* rather than a *place* had no licensed answer and
the model correctly refused. `Character.impressions` now carries what each thinks
of the others, and the prompt says outright that a question about a person is
never refused.
**Not a loosening of the leak model:** the boundary that mattered is unchanged.
A character still cannot say where anybody was beyond their derived facts.
**Status:** active

## D-054 The body being found is common knowledge
**Date:** 2026-08-27
**Decision:** `Mystery.discovery` records who found the body, where, and how, and
it goes into every character's brief as something everyone knows.
**Why:** Nothing in the model said the body had been found, so the suspects could
not discuss the death they were being questioned about. Playtesters noticed
immediately and it made every conversation slightly unreal.
**Status:** active

## D-055 Characters are shown what they have already said
**Date:** 2026-08-27
**Decision:** `ask` takes the speaker's own prior questions and answers, and
renders them into the prompt under "things you have already said".
**Why:** Every answer was produced as though it were the first, because nothing
carried the conversation forward at all. A suspect who forgets the last three
minutes is not a suspect.
**Note:** it goes in the system prompt rather than as message history, so the
`Responder` boundary is unchanged and the whole test suite still runs against
fakes with no network.
**Status:** active

## D-056 The panel is three views, not one list
**Date:** 2026-08-27
**Decision:** Notebook, Transcript and Map. The notebook groups claims per person
rather than listing rows; the transcript is one conversation at a time; the map
shows rooms at a chosen hour, filled only with what somebody has actually said.
**Why:** Playtesters asked for a per-person log and a picture of the rooms, and
both are the same underlying complaint: one flat table does not let you hold a
case in your head.
**The map is deliberately incomplete:** an empty room means nobody has placed
anyone there, not that it was empty. Showing the truth would hand over the
answer.
**Status:** active

## D-057 Some suspects were useless, and A3 and A8 both passed them
**Date:** 2026-08-27
**Decision:** A9 checks that every suspect is a *source*: they can contradict the
killer's alibi, they hold a secret that gates another, somebody else's secret is
known to them, or the motive is theirs. Fewer than one of those and they are
decoration. The prompt now tells the generator to weave the cast together
explicitly.
**Why:** The second playtest said some characters were useless for the plot, and
both existing advisories passed them, because holding a secret and having a
private moment is not the same as mattering. In the hand-built prototypes every
character was at least two of those four things, which is why every conversation
went somewhere.
**The pattern, for the third time:** an advisory can be true and still measure
the wrong property. A3 asked "do they have something to hide", A8 asked "did they
have opportunity", and neither asked "does the case run through them".
**Status:** active

## D-058 Portraits are optional and never load-bearing
**Date:** 2026-08-27
**Decision:** `--portraits` generates character images through OpenAI, cached
beside the mystery. Every failure path, missing key, API error, missing file,
falls back to the drawn SVG. `openai` is an optional dependency.
**Why:** Decoration must not be able to stop a game starting. Roughly five cents
and thirty seconds a case, requested in parallel, and free on a replayed seed.
**Status:** active

## D-059 Characters describe how they look, which fixes the coin-flip faces
**Date:** 2026-08-27
**Decision:** `Character.look` is a sentence of physical description written by
the generator. The drawn portrait reads a man/woman cue out of it to pick a hair
set, and it is the prompt when image generation is on.
**Why:** Appearance was derived from a hash of the character id, so whether
somebody looked like a man or a woman was random and unrelated to their name.
Playtesters noticed at once.
**Status:** active

## D-060 Two model tiers, split by how often the call happens
**Date:** 2026-08-27
**Decision:** `DRAFT_MODEL = "claude-opus-5"` writes the case. `VOICE_MODEL =
"claude-sonnet-5"` speaks for the suspects. Both are `--generator-model` and
`--model` on the command line and both live in `generator.py` so they cannot
drift apart.
**Why:** Generation is one call per case. It decides the cast, the secrets, the
grid and every conversation that follows, and at one call it is the cheapest
thing in the system. Interrogation is one call per question, thirty or forty a
session, and that is where the money goes. Paying top rate for the part that
runs once and a tier down for the part that runs constantly is the whole of the
argument.
**What this corrects:** every case played so far was drafted by Sonnet 4.5,
including the ones judged against hand-built prototypes that had been written by
Opus in conversation. The comparison was never like for like.
**Status:** active

## D-061 The prompt carries a worked case, not just rules
**Date:** 2026-08-27
**Decision:** `SYSTEM_PROMPT` ends with prototype 02 abridged to its skeleton:
hub victim, gated chain, three insufficient contradictors, the shield, the
decoy, and the two cheap things that made it feel alive at the table. It is
explicitly labelled as shape rather than content, with an instruction not to
reuse the setting or the props.
**Why:** Every rule in the prompt was already true of that case, and the
generated cases still came out thinner. Rules describe a good case from outside.
An example shows what the parts feel like when they are load-bearing, which is
the thing the rules were failing to transmit.
**Cost:** roughly seven hundred tokens on a call that happens once, and it
invalidates every cached seed, because the prompt is in the cache key (D-035).
That is the mechanism working.
**Risk to watch:** worked examples pull generations toward themselves. If the
next few cases all feature a theft-shaped shield or a theatre-shaped venue, the
example is too specific and wants abstracting.
**Status:** active

## D-062 The map is a timeline, not a snapshot
**Date:** 2026-08-27
**Decision:** Rooms down the side, slots across the top, people as two-letter
initials. Red means two people put someone in different rooms at that hour, a
ring means somebody other than themselves confirmed it, and the dashed bottom
row is who nobody has placed at all. Tags are made unique, so two Vermeers do
not become two identical squares.
**Why:** The previous map showed one hour at a time behind a row of buttons. An
alibi is not a fact about an hour, it is a fact about the difference between
hours, and a player flicking between five tabs is holding the grid in their
head, which is the job the notebook was supposed to take over.
**What it deliberately does not show:** the truth. Only what somebody has said.
An empty cell is a gap in the questioning.
**Status:** active

## D-063 Innocent people lie too
**Date:** 2026-08-27
**Decision:** `Mystery.false_claim` becomes `false_claims`, a list. The killer
lies and so do two innocents, each with `covers` naming the secret the lie
protects and `admits_when` naming what makes them drop it. `false_claim` stays
as a property returning the killer's, because that is what the alibi analysis,
the reveal and A6 all mean when they say "the lie".
**Why:** The third playtest found the real flaw. The case had exactly one hidden
variable: the killer was recoverable from the grid alone, as the one person
whose claim did not match it, and every secret in the case was scenery around a
single deduction. Once you knew who lied you were done, and there was nothing
left to replay. With three liars the timeline hands over a shortlist instead of
a name, and the only way to shorten it is to find out why each of them lied,
which drags the secrets onto the critical path.
**The asymmetry that makes it solvable:** innocent lies break by *presence*,
somebody saw them where they really were. The killer's breaks by *absence*, they
were alone with the victim and nobody can place them. That is the discrimination
the player is really making.
**Which is also how it could collapse again,** so A12 exists: if every innocent
liar can be vouched for, "which liar has no witness" is a mechanical shortcut
straight to the killer and the motive never matters. At least one innocent must
also have been unobserved.
**New rules:** V8, a lie must actually be false and one person tells at most
one. V4 extended to `covers`. A10, the killer is not the only liar. A11, every
innocent lie has a way out. A12, position alone does not convict.
**Cost:** ambiguity without resolution is noise rather than depth, which is what
A11 is guarding. A player who catches somebody out, presses, and gets nothing
learns that pressing does not pay.
**Status:** active

## D-064 A third knowledge state: guarded
**Date:** 2026-08-27
**Decision:** A brief now has `facts` (will say), `guarded` (true, citable, held
back until a condition is met) and `conceals` (never). An innocent liar's real
whereabouts is guarded. The killer's stays concealed and never becomes sayable.
`assertions_from` reads guarded facts as well as plain ones.
**Why:** Without it a retraction is invisible. The character says "all right, I
was in the study", the player sees it, and the notebook goes on showing the lie,
because only cited facts become assertions and concealed material may not be
cited. The admission is the entire payoff of an innocent lie and it has to reach
the grid.
**Why the killer is excluded:** their retraction ends the game. Under pressure
they have the shield instead, a smaller true thing that explains the evasiveness
and is not the murder. Citing their own truth is still a leak, and the leakage
suite still counts it as one.
**What this buys beyond the mechanic:** `agent.folded` is logged with the
character and how many questions it took. Fold on question two and the
conditions are too soft; never fold and the red herrings never resolve. It is
the first thing in the project that measures whether the cast are behaving,
rather than whether the data is correct.
**Status:** active

## D-065 The accusation asks for the motive as well as the name
**Date:** 2026-08-27
**Decision:** `POST /accuse` takes `{who, why}`. `why` is the id of a secret,
and it only counts if that secret actually surfaced during play. Three endings
now: right person and right reason, right person and no idea why, wrong person.
`Statement` gained `cited`, the raw fact ids a reply used, so the transcript can
answer "what has this player actually been told".
**Why:** A name alone is a one-bit answer, and a coin flip beat a bad player. The
timeline gets you to the person and only the secrets get you to the reason, so
asking for both makes the secrets a win condition rather than a route.
**Why only surfaced secrets are offered:** a list of every secret in the case
would itself be the answer. Reading five summaries at accusation time teaches you
more than an hour of questions.
**Status:** active

## D-066 A suspect's own secrets are guarded, not concealed
**Date:** 2026-08-27
**Decision:** Own secrets move from `conceals` to `guarded`: citable, with
`breaks_when` attached as the condition. One exception, and it is absolute. The
secret marked `is_motive` held by the killer stays concealed and never becomes
sayable.
**Why:** D-065 needs to know what has surfaced, and a concealed fact cannot be
cited, so a character giving up their own secret was invisible to the game. The
same gap as the retraction gap in D-064, found one layer up.
**What it buys:** the shield stops being a hope and becomes a mechanism. Under
pressure the killer has exactly one thing to give, the smaller true secret, and
the reason they killed is the one door in the case that does not open.
**What it costs:** the leak detector loses its flagship example. Citing your own
secret used to be the worst kind of leak; now it is a fold, which is legitimate
play. The distinction is real, though: a leak is saying something you were never
told, and that is still caught. A13 covers the new hole this opens, which is a
motive nobody else knows and the player therefore cannot ever name.
**Status:** active

## D-067 Topologies are a library, not a sentence
**Date:** 2026-08-27
**Decision:** New module `topology.py`. A topology has an id, a blurb, a `brief`
(the paragraph the generator is given about the shape of the solution) and
`checks` (advisories that only make sense for that shape). Three to start:
`the_lie`, `mutual_alibi`, `false_confession`. `--topology` on both the CLI and
the web game, `--topologies` to list them. `assess(mystery, topology)` runs the
general critique plus the shape's own checks.
**Why:** `topology` was a freeform string interpolated into the prompt and
otherwise ignored, so every case ever generated had the same skeleton. Better
prose does not fix that: the second case is the same puzzle in different clothes
however good the clothes are, and a player who has solved one has solved the
pattern. Innocent liars (D-063) added depth inside a case. This is the part that
makes the *next* case worth playing.
**Why the checks live with the shape:** a mutual alibi case where nobody
corroborates anybody is an ordinary false claim wearing a different name, and no
general advisory would catch it, because none of them knows what was asked for.
Same split as validator and critique: correctness is universal, quality is
contextual (D-031).
**One model change:** `Mystery.false_confessor`, an optional character id, and
`Brief.instructions` to carry behaviour that no fact can express. A confession
is a thing somebody does, not a thing they know, so it does not belong in facts,
guarded or conceals.
**The cache key now includes the brief,** or editing a shape would change
nothing on an already-run seed. Same trap as D-035, one level down.
**Shapes designed and not built,** because each needs a model change rather than
a paragraph: the body was moved, so alibis are being checked against the wrong
room; the time of death is not what everyone assumes, so the player must
establish *when* before *who*.
**Status:** active

## D-068 Solvability is computed, and the browser game now actually checks
**Date:** 2026-08-27
**Decision:** New module `solvable.py`. It computes a closure over the secret
graph: start from what a player can get cold, add whatever that unlocks, repeat
until nothing changes. Reports `way_in`, `reachable`, `sealed`, whether the
motive can be reached and whether the alibi can be broken. S1 to S4 report the
findings. `assess()` includes them, and `web.py` now runs `assess()` at startup
and refuses to serve an unwinnable case without `--anyway`.
**Why, and this is the uncomfortable part:** the browser game never ran the
advisories at all. Every case played in a browser went straight from `validate`
to playable, so thirteen quality checks existed, were tested, were paid for in
tokens, and had never once fired in a real session. The rules were fine. Nothing
called them.
**Why a closure and not another advisory:** every existing check measures one
property in isolation, and a pile of satisfied local properties does not add up
to solvability. The concrete miss is a cycle: A gated behind B, B gated behind
A. Both secrets exist, both have holders, both have breaking points, every
advisory passes, and nobody can solve the case. The same shape hides a motive
behind a chain whose first link does not exist.
**What it cannot know:** whether a suspect actually gives something up depends on
`breaks_when`, which is a sentence in a prompt. So this is a necessary condition,
not a sufficient one. A case it calls unwinnable is unwinnable; a case it passes
is only not provably broken. That is still the difference between "no rule
objected" and "there is a path".
**Status:** active

## D-069 Backdrops for the setting and each room
**Date:** 2026-08-27
**Decision:** `scenery.py`, same contract as `portraits.py`. One wide
establishing image for the setting, one per room, cached under the case's cache
key. The setting is the page background from the first moment; clicking a room
name in the Map tab cross-fades into that room and names it in the corner.
Optional, `--scenery`, and every failure falls back to the painted gradient.
**Why the rooms are worth generating at all:** a picture nobody looks at is a
line on a bill. Putting them behind the Map means a player can stand in the room
while deciding whether somebody was really in it, which is the moment the art
does work rather than decoration.
**No people in any of them.** The cast are portraits and the rooms are empty. A
generated figure in a doorway would be a person the case does not contain,
standing in a room the player is reasoning about.
**Status:** active

## D-070 A case in the repo, and one test that runs the seams
**Date:** 2026-08-27
**Decision:** `example.py` holds one hand-written case as a raw dict, the shape a
model returns rather than a `Mystery`, so it crosses the parse boundary like a
real draft. `--dry-run` on both the CLI and the web game uses it instead of
calling a model. `tests/test_pipeline.py` runs the whole chain on it: parse,
solve, validate, assess, briefs, a full round of questions, notebook, verdict.
**Why:** a hundred and fifty passing tests did not notice that the browser game
never called the advisories (D-068), because every one of them was holding a
single component up to the light. Component tests answer why something is
broken. Nothing was answering whether the thing works.
**What the dry run is for:** checking the machinery after a change without
spending anything, and playing a known-good case while paying only for the
conversation. It also means there is always a case to look at, which matters
when a generated one comes out wrong and you need to compare.
**The shipped case has one live advisory** (the killer moves three times), left
in on purpose. It shows the critique running rather than decorating, and it is a
judgement call a person can look at and accept, which is what D-031 said
advisories are for.
**Status:** active

## D-071 One definition of which scene is the murder
**Date:** 2026-08-28
**Decision:** `Mystery.murder_scene` and `Mystery.murder_slot` on the model.
Resolution order: an explicit `murder` field naming a constraint id, otherwise
the latest *exclusive* scene between killer and victim. The solver, the
validator, A2 and T4 all now ask the model rather than each working it out.
`murder` is a new optional field, the prompt asks for it, and V4 checks it names
something.
**Why:** two real generated cases in a row were rejected as broken and both were
fine. Four modules each looked for "a constraint containing the killer and the
victim" and each took the *first* in list order. A good case usually has an
earlier private scene between exactly those two, the one where the victim says
the thing that gets them killed, and the prompt asks for it explicitly. So which
constraint came first was down to the order the model happened to write them in,
and half the time the confrontation was treated as the killing: the body was
laid to rest an hour before it died, every later scene became a scene with a
corpse in it, V7 fired on all of them, and the solver pinned people into the
wrong rooms, which fired V1.
**Reproduced before fixing** by swapping two constraints in the shipped case,
which produced the same violations, character for character. The fix is checked
both ways round.
**Why "latest exclusive" is not another guess:** after the murder the victim
meets nobody, so the last time those two were alone together is the last time
they could have been. It is the invariant the whole timeline already rests on.
**The lesson, and it is the third time:** the same piece of knowledge was
derived independently in four places, and the disagreement was silent. When
something is asked about the ground truth more than twice, it belongs on the
ground truth.
**Also:** a failed final validation now prints the path of the cached draft.
Drafts are cached before solving, so a case that fails this way fails identically
for ever, and the file is either worth studying or worth deleting.
**Status:** active

## D-072 One flag for the art, and portraits that sit in the room
**Date:** 2026-08-28
**Decision:** `--art` turns on both `--portraits` and `--scenery`, which stay as
the granular flags. And `#photo` gets a radial mask so a generated portrait
feathers into whatever is behind it.
**Why the flag:** two separate switches for "make it look nice" meant running
with backdrops and no faces without noticing, which is exactly what happened on
the first real run.
**Why the mask:** a generated portrait is a square image with its own dark
ground. Alone on a gradient that is invisible; over a room it is a visible
rectangle, and the character reads as a photograph taped to the scene rather
than a person standing in it. Feathering costs one line of CSS.
**Noticed by rendering it.** The two features were built in separate sessions
and their combination had never been on screen at once. Worth remembering: a
feature that is only ever tested alone is only known to work alone.
**Status:** active

## D-073 A shelf of saved cases, separate from the generation cache
**Date:** 2026-08-28
**Decision:** `library.py`. Every case that generates and validates is written to
`var/cases/<name>.json` as the solved mystery plus its setting, shape, seed and
date. `--case <name>` plays or inspects it with no model call at all, `--cases`
lists the shelf, and generated art moves from `var/portraits/<request hash>/` to
`var/art/<case name>/`.
**Why, when there has been a cache since D-005:** the cache is keyed by a hash of
the request *and* the prompt (D-035), which is right for what it is for, not
paying twice while a prompt is being developed, and exactly wrong for keeping
anything. Every prompt edit changes every key, so a case worth replaying became
`a3f9c2e1....json` that nothing would ever ask for again, and its art orphaned
with it. Two different jobs that happened to share a folder.
**Art belongs to the case, not to the flag.** Pictures already on disk are used
whether or not `--art` is passed again. They were paid for once.
**Names, not hashes.** A second case called The Vermeer Forgery becomes
`the-vermeer-forgery-2`. Two cases with one title is not an error, it is Tuesday.
**Still gitignored.** `var/` stays out of the repo: the art is megabytes and the
cases are personal. A case good enough to keep is one file to copy into
`tests/fixtures/` on purpose.
**Also:** `anthropic_responder` now says what is missing when there is no key,
which the drafter has done since the beginning and the responder never did.
**Status:** active

## D-074 What the browser is told, who these people are, and who gets to be the killer
**Date:** 2026-08-28
**Four things, one root each.**

**The leak.** The cast chips carried `title=wants`, so hovering a suspect showed
their private motive. The fix is not to stop drawing the tooltip. `wants` and
`manner` are no longer sent to the browser at all, because a field the client
does not have cannot be leaked by the next person who writes some markup. There
is a test that greps the whole `/state` payload for every character's `wants`
and `manner`.

**`Character.role`.** One short public phrase, their job here and what they were
to the victim, printed under their name. The nameplate used to show `manner`,
which is a behavioural note written for the model rather than an introduction
written for the player, and reading "cold and precise, answers exactly the
question asked" under somebody's name is being handed the character sheet.

**Casting comes off the seed.** The killer and the victim were men every time.
That is not something a check on one case can see, because each case was
perfectly reasonable; it is a property of the sequence, so it belongs where the
sequence is known. `_casting(seed)` takes two independent bits and names who
kills whom, so all four combinations appear across four seeds. A14 covers the
countable half, which is whether the room around them is all one thing.

**`Character.gender`,** stated rather than sniffed out of the `look` sentence,
which is what the drawn portrait did before and got wrong whenever the sentence
did not say (D-059 finally finished).

**On the repeating character types,** which is the same complaint from the other
end: the prompt was handing over a menu. It listed four manners as examples,
"one is cold and answers exactly the question asked", and the model copied them,
because that is what examples are for. They are now described as dimensions to
vary, with an explicit instruction not to reuse phrasing from the instructions.
The worked example (D-061) has the same risk and is worth watching next.
**Status:** active

## D-075 Variety is dealt, not requested
**Date:** 2026-08-28
**Decision:** New module `palette.py`: twenty eight manners, twenty motive
families, twenty four intrigues. Every generation draws five manners, one motive
and three intrigues from a hash of the seed, the setting and the topology, and
the *only* thing the model sees is that hand. It never sees the lists.
**Why not simply a longer list in the prompt:** because that is what the last
round already was. Four example manners in the prompt produced four repeated
manners in the cast (D-074), and forty examples would produce the model's three
favourites, repeatedly. A model given options develops taste. A model given an
assignment does the assignment.
**Why the entries are behaviours rather than characters:** "answers a slightly
different question from the one that was asked" can belong to a bishop or a
bouncer, and leaves the writing to be done. "Nervous young assistant" is a
character, and handing over characters is how every case ends up being the same
five people in different coats.
**Keyed on seed, setting and topology together,** so running seed 0 against four
settings is four different hands rather than the same one four times.
**Roughly four billion combinations** of manners, motive and intrigues, which is
not the point on its own: the point is that the second case is dealt different
material before a word of it is written.
**Also, the cache key now hashes the finished prompt** rather than the request
plus a couple of the pieces that go into it. Every new piece was another chance
to forget one; the topology brief was nearly missed and this material would have
been. A hash of what is actually sent cannot fall behind what is sent.
**Status:** active

## D-076 Two free ways to look at variety
**Date:** 2026-08-28
**Decision:** `--material N` prints the hand the next N seeds would be dealt, and
`--casts` prints every saved case's cast together: name, gender, role, manner.
Neither calls a model.
**Why:** the thing D-075 changed is a property of a *sequence* of cases, and
until now the only way to look at a sequence was to generate three of them at a
minute and a few cents each. The material can be inspected before spending
anything, and the casts can be compared after, without reopening three cases one
at a time.
**What `--casts` is actually for:** not whether a cast is good. Whether the third
one is made of different people from the first, which only shows up when they
are next to each other.
**Status:** active

## D-077 A case is shared, a session is not
**Date:** 2026-08-28
**Decision:** The old `Game` splits in two. `Case` is what was generated: the
mystery, the derived knowledge, the briefs, the pictures. Built once, immutable,
shared by everybody. `Session` is one person's play-through: transcript, whether
they have accused, an unguessable id. `Game` becomes a cheap view over one of
each, made per request and thrown away. `Sessions` is a four-method boundary
with `InMemorySessions` behind it today.
**Why this before any AWS:** the game could not be deployed at all. One `Game`
lived in one process and was served to everybody who connected, so two strangers
would have been filling in each other's timeline and the first to accuse would
have ended the evening for the rest. That is not a configuration problem.
**Why a boundary rather than just a dict:** the same argument as D-002. Four
methods, and anything the deployed version needs has to be expressible through
them, so the storage decision stays a swap rather than becoming a rewrite. The
in-memory implementation exists to make the interface honest before there is
anything to be honest about.
**`--together` keeps the old behaviour** and is now a choice rather than an
accident. Two people in a room with one case between them want one notebook;
two strangers on a URL do not. Passing a `Game` to `build_app` still works and
means `together`, so nothing that had one breaks.
**Sessions are a cookie,** httpOnly, twelve hours. The id is the only lock on a
notebook, so it is `secrets.token_urlsafe` rather than anything countable.
**Status:** active

## D-078 The nightly job fills a buffer, it does not make today's case
**Date:** 2026-08-28
**Decision:** `daily.py`. A rota records which case ran on which day; `waiting()`
is everything on the shelf that has never been anybody's day, oldest first;
`todays_case()` draws from the front of that queue the first time it is asked
each day. `--fill` tops the buffer up to four and is the whole of the nightly
job. `--daily` serves today's case and **never generates one**.
**Why not generate today's case tonight:** because the failure happens at three
in the morning with nobody awake, and then there is no game at nine. With four
cases waiting, a night the generator fails costs a shorter queue, and there are
four days of slack before a player could possibly notice. It turns an outage
into a warning.
**Bounded attempts, and a taxonomy of failure.** Three tries per case. A
validation failure is worth retrying, because a complaint can fix it. A case
that comes back unwinnable is worth retrying for the same reason. Anything else,
no key, no network, no service, stops the run immediately: retrying costs money
and changes nothing. "Retry until it works" against a paid API overnight is how
a bad night becomes a bad bill.
**A web request never generates.** An empty buffer returns None and the server
says so. A visitor arriving must not be the thing that decides to spend a minute
and a few cents on a model.
**Midnight does not interrupt anybody.** A `Session` stores `case_id`, not
"today" (D-077), so a case started at 23:50 is finishable next Thursday. Nothing
was needed for this, which is the nicest kind of design confirmation.
**One day, in UTC, decided in one function,** because "today" asked in two
places drifts by a day depending on who is asking.
**A bug the tests found:** `library.entries()` sorts by filename, so
`opening-night-2` came before `opening-night` and the queue was an alphabet
rather than a queue. Saved cases now carry a timestamp rather than a date, and
the buffer sorts on it.
**Status:** active

## D-079 The rota claims a day rather than setting one
**Date:** 2026-08-28
**Decision:** `Rota` becomes a three-method boundary with `FileRota` behind it.
The interesting method is `claim(day, case_id) -> str`: "today's case is this
one, unless somebody already said otherwise, in which case tell me what they
said". Whoever arrives first wins, and everybody else is handed the winner's
answer and uses it. `release(day)` exists only for the repair path.
**Why, and the honest version:** this question was posed expecting a race, and
walking the old code showed there was not one. Two servers both read an empty
rota, both computed the same queue, both took `queue[0]`, and both wrote the
same answer. It was **correct by accident**. Nothing anywhere said the choice had
to be deterministic, so the first person to add a random pick, or a "prefer
something nobody has played" rule, would have started handing two players two
different mysteries on the same day with nothing failing loudly.
**The real bug was the shape of the record, not the timing.** One document held
every day ever served, so every write rewrote the whole history, and any two
overlapping writes meant one silently erased the other. One record per day, and
writers never touch each other.
**Why the rota is DynamoDB and the cases are S3:** a conditional write is one
line in the table and does not exist in the bucket. That single operation is the
reason the two kinds of data live in two places.
**A regression the tests caught immediately:** `claim` refuses to overwrite,
which is the point of it, so a day pointing at a case that had been deleted off
the shelf could never be repaired. Hence `release`, used nowhere else.
**Third time for this pattern** after `Drafter` and `Sessions`: smallest
interface that says what the code needs, local implementation now, cloud
implementation later, nothing above the boundary knowing which it got.
**Status:** active

## D-080 A session becomes a record, and there are two stores now
**Date:** 2026-08-28
**Decision:** `Session.to_record()` and `from_record()` turn an evening into
plain JSON and back. `FileSessions` stores one file per session, and `--remember`
switches the server to it. Sessions carry `expires`, a unix timestamp, forty
eight hours out.
**Why serialisation is the whole job:** a dict in a process can hold objects.
A file, a table and a network hold bytes. Everything else about deploying
sessions is plumbing; this is the line where a `Transcript` full of `Statement`
objects full of `Assertion` objects has to become something a database will
accept, and come back as the same evening. The test that matters is not that the
prose survives, it is that the *contradiction* does: an answer that comes back
without its structure is a transcript rather than a notebook.
**Written by hand rather than pickled.** A pickle is unreadable in a console,
carries no version, and is unwise to load from anywhere you do not fully
control.
**The fork I took without asking:** no DynamoDB implementation yet. I could have
written one, and it would have been untested code that looks finished, since
there are no credentials here and I cannot run it. `FileSessions` is a second
real implementation, which is what actually proves the boundary: one
implementation behind an interface is a guess about what the interface should
be, two is an interface. The table implementation is a good first thing to write
with the AWS console open.
**`expires` is the timer instinct from the design conversation**, put where it
belongs. Not a rule about which case somebody may play, which would cut people
off mid-interrogation, but how long an abandoned record is kept. DynamoDB reads
exactly this attribute shape and deletes the row for free, so the field is
written for a database that does not exist yet, because the alternative is a
migration later.
**One file per session, never one file holding all of them,** for the same
reason as the rota (D-079).
**A session id arrives from a cookie,** which is to say from a stranger, so it
is filtered before it is allowed anywhere near a filename. There is a test that
tries `../../etc/passwd`.
**Status:** active

## D-081 The listing and the contents are two different things
**Date:** 2026-08-28
**Decision:** `Card` is an id and a date, and both live in the object's *name*:
`20260828T124618__opening-night-21aa.json`. `cards()` returns them from a
directory listing with nothing opened. `entries()` keeps the old behaviour of
opening everything and is now only used by the two commands a human waits on.
`waiting()`, which runs on every visit, uses `cards()`. `Shelf` is the three
method interface: `cards`, `load`, `save`.
**The bug this removes:** `entries()` did two jobs, saying what exists and
loading what is in each. `waiting()` called it, `todays_case()` called
`waiting()`, and a page load called that. Five cases on a laptop is five file
reads and nobody notices. Three hundred cases on object storage is one listing
request plus three hundred network round trips, to answer a question whose real
answer is one case id.
**Why the metadata is in the name:** a key listing is the one query object
storage can do. Putting the sort key in the name means the listing *is* the
ordering, at no extra cost, and no index document has to be maintained. An index
document would have brought back the read-modify-write problem D-079 just
removed.
**Ids are minted, not negotiated.** `_unique` asked "is this name free?" once per
guess, which is a round trip each and racy: two jobs naming a case at the same
moment are both told yes. `mint` appends four random characters and asks
nothing. Note what the randomness is for: a session id is random for *secrecy*,
this is random for *coordination*. Same tool, different argument, and worth
being able to say which.
**Prefix matching pays for it.** `--case the-brine` finds `the-brine-house-k3f9`
as long as it is unambiguous, and refuses rather than guessing when it is not.
**Old cases still load.** Files saved before the rename have no stamp in the
name; they sort first, which is correct, since they are the oldest things on the
shelf.
**Status:** active

## D-082 The pictures cost forty five times what I said they did
**Date:** 2026-08-28
**What was wrong:** `portraits.py` claimed "roughly five cents a case". Two
errors compounded. `--art` makes **eleven** images, not five: a portrait each
for the cast plus an establishing shot and one per room, and the backdrops are
landscape, which costs half again as much. And neither module set `quality`, so
both inherited the API default, which is the expensive tier. At current prices
that is about **$2.34** a case, not five cents.
**Worse until D-073:** art was cached under the *request* key, which includes
the prompt. Every prompt edit changed the key, so the next `--art` run
regenerated all eleven images for what was effectively the same case. Moving art
under the case id was written as tidiness and was in fact the fix for a leak.
**Decision:** quality is chosen rather than inherited, `--art-quality` with
`low` as the default, and the estimate is printed before anything is spent. Low
is about fifteen cents a case, medium four times that, high fifteen times. Low
is right for the backdrops on their own merits: they sit under a heavy vignette
and a sharper image would be thrown away by the CSS.
**Art already on disk is never regenerated**, flag or no flag, which was true in
spirit and is now checked before the estimate rather than after the spending.
**The general lesson, and it is not about images:** a cost written in a docstring
is a guess with a confident voice. Nothing in a program can check it, no test
will ever fail because of it, and it will be believed for exactly as long as
nobody looks at a bill. Anything that spends money should say what it is about
to spend, out loud, in the terminal, before it spends it.
**Status:** active

## D-083 A case travels as one file
**Date:** 2026-08-28
**Decision:** `--bundle <case>` writes a zip holding the case and its pictures.
`--unbundle <file>` puts both on this machine's shelf. Nothing inside is
machine-specific.
**Why:** `var/` is gitignored for good reasons, the art is megabytes and the
cases are personal, and those reasons are exactly wrong when the thing you want
is one good case on your other laptop. Pulling the repo gives you the engine and
an empty shelf, and regenerating means paying for a draft and eleven images to
get a case you already own.
**Status:** active

## D-084 The model calls say what they cost too
**Date:** 2026-08-28
**Decision:** `generator.py` holds `RATES`, the real published price per million
tokens for every model this program can call, and a `cost()` that turns a token
count into dollars. Every model call already logged its token usage; now the
same log line carries `usd`. `mystery.drafted` says what the draft cost,
`agent.answered` says what the answer cost.
**And before the spending, not only after it:** `--fill` is the one command that
can make several drafts in a row without being asked again, so it prints how
many it is about to generate and what that costs, with the retry ceiling stated
as well, since a case that needs three attempts costs three drafts. About
nineteen cents a draft at Opus prices, so a full buffer of four is about
seventy seven cents, up to about two thirty if every one of them fights back.
**Why now:** D-082 was written as a fix to the image prices and ended with a
general rule, that anything spending money should say what it is about to spend
before it spends it. The image path obeyed that rule the same afternoon and the
model path did not, which made the rule a paragraph rather than a practice. The
image bill was the one that surprised him, but the drafts are the recurring
cost: eleven pictures happen once per case, and a question happens forty times
an evening.
**The estimate is a measurement, not a guess.** `TYPICAL_DRAFT` is eight and a
half thousand tokens in and six thousand out, taken from the logs of real
drafts, and it sits next to the rates where the next person to read a bill will
find it. When the prompt grows, the estimate goes stale in the one place where
somebody can notice and correct it, rather than in a docstring nothing checks.
**What it does not do:** nothing here stops a spend. A budget guard belongs at
the boundary of the public deployment, not in the CLI, and it is still open.
**Status:** active

## D-085 The box under a portrait belongs to that portrait
**Date:** 2026-08-28
**What was wrong:** `select()` switched the face, the nameplate and the role, and
left `#said` holding whatever was last on screen. Ask Marisol something, click
Nicanor, and Nicanor's face sits above Marisol's words with no marking to say so.
In a game whose entire subject is who said what, that is not an empty panel, it
is the interface asserting something false.
**Decision:** switching to somebody recalls their own last answer, from the
per-person `logs` the payload has carried since D-062, with the question that
produced it above it and a count of how many earlier answers there are. Somebody
never questioned says so by name rather than showing the generic opening line,
because "not asked yet" and "asked and said nothing" are different states and the
player is entitled to tell them apart.
**No typewriter on a recall.** The animation means *this is being said to you
now*. Replaying it every time the player flicks between two suspects would make
a five-year-old memory look like a fresh statement, and would be slow.
**The live answer got the same shape,** question above, answer below, so the box
does not change form when you leave a person and come back. The question also
appears the moment it is sent rather than after the reply lands, so the panel is
already that person's while they think.
**Why the data was already there:** `logs` was built per speaker for the
Transcript tab. The page had everything it needed to do this correctly and did
not use it, which is the fourth time in this project the same shape has appeared:
something derived correctly in one place and ignored in another. See D-071 and
D-068.
**Status:** active

## D-086 Everybody is told who everybody is
**Date:** 2026-08-28
**What was wrong:** found in a real playtest. The same woman was called the
victim's niece by one suspect, his daughter by another and his wife by a third.
Not a style problem: no brief said who anyone was, so five models each invented a
relationship independently and the player was given three of them.
**The brief had the death and not the room.** `WHAT EVERYONE KNOWS` carried the
body, the finder and the place. Everything else about the other four people
arrived only through `impressions`, which is free prose about what you think of
somebody and mentions their job only by accident.
**Decision:** a `WHO THE OTHERS ARE` block in every brief, built from the public
`role` field, with the victim marked dead. Stated as public and binding: say it
freely, do not contradict it, and if you are asked how two people are related
this is the answer.
**Why `role` and nothing else.** It was added (D-074) as the line printed under
a portrait on the page, which makes it public by construction. Anything richer
would be handing five models a shared script and inviting them to recite it.
**The pattern, again:** the field existed, the page showed it, the prompt never
saw it. That is the same shape as the murder scene computed four ways (D-071),
the advisories nobody called (D-068), and the per-person transcript the page
ignored (D-085). Something true in one place and absent in another.
**Status:** active

## D-087 A gate you can produce, not a gate you argue with
**Date:** 2026-08-28
**What the playtest found.** A hundred and five questions, the right killer, the
wrong reason. Reading the case file afterwards found two failures pointing in
opposite directions, both fatal to the same evening.
**The gate did not exist at runtime.** `revealed_by` was read by `solvable.py`,
which computes the closure and decides whether a case is winnable, and by
nothing else in the program. `knowledge.py` handed a secret to everyone in
`known_by` unconditionally and `build_brief` turned it into a plain fact. So the
killer's motive, in full, including the murder weapon, sat in a witness's FACTS
block from question one. The chain the case was built around was real when the
case was validated and gone when it was played.
**And nothing made it come out.** That witness was asked twenty four questions
and never said it, because the FACTS block is introduced as the whitelist of
things you may state about where anyone was, so a model reads the whole list as
whereabouts and volunteers none of it.
**The conditions that did fire were unguessable, and one was unperformable.**
`breaks_when` is a sentence judged privately by the model with no partial credit
and no accumulated pressure, so twenty questions of circling produce the same
verdict as one. The motive's condition was "only when shown the ledger pages",
which names an action the game had no verb for. The player completed the entire
discoverable chain and lost on the one link that required holding something.
**Decision, and it is the player's design rather than mine.** Secrets may carry
`evidence`: the object that proves them. A secret whose gate carries an object
is withheld from every brief until that object has been put in front of *that
character*, at which point it moves to a fourth state, `yielding`: it is coming
out in this answer, and the only thing left to the model is how. Grudgingly, in
pieces, angry at being caught. The fact is guaranteed, the manner is not.
**Per character, never global.** The unlock is keyed to what was produced in
this conversation, not to what the player knows. The alternative, rebuilding
briefs from the player's global knowledge, has Nicanor becoming willing to talk
because of something Teodora said in another room, which is the game reading the
player's mind. This was the correction that made the rest of it work.
**Withheld by omission, not by instruction.** A gated secret is absent from the
brief rather than present with a warning attached. A brief cannot leak what it
does not contain, which is the same argument as D-042.
**The killer still never yields their motive.** D-066 outranks the object. Show
them everything in the house and they will not say why.
**Old cases keep working.** A gate whose secret carries no object falls back to
the previous behaviour, because there is nothing to produce and the only
mechanism left is persuasion. That is worse, and it is what every case generated
before today has, so it degrades rather than breaking.
**S5** reports exactly that shape: gated behind something with no object, so the
gate can only be argued at. It fires on the case that lost the playtest.
**What is not solved:** `breaks_when` for an ungated secret is still a private
judgement with no notion of pressure across a conversation. Objects fix the
chain; they do not fix persuasion.
**Status:** active

## D-088 Somebody else's secret was filed under where people were
**Date:** 2026-08-28
**The report:** "I definitely mentioned the references myself a lot and yet she
never broke." Reading her brief, both things she was holding, the forged
reference and her retraction of the lie, carry the same condition: *told that
someone has already raised the reference*. Not asked about it. Told that another
person had already brought it up. So the model was reading the condition
correctly and holding correctly, and the player was doing the one thing that
condition explicitly does not accept.
**The intended path went through two other people.** The case even writes it
down: "Nicanor or Marisol will both say it if asked about her directly." Both of
them hold the forgery, and both of them said nothing, which is the same silence
that hid the motive in D-087.
**Why they said nothing.** A secret you merely know went into `facts`, and the
prompt introduces `facts` as "only these may be stated as fact about where
anyone was". A model reads that heading and treats the whole block as
whereabouts. Nothing in it invites you to bring up what you know about a person,
so nobody ever did. The material was licensed, present, and effectively invisible.
**Decision:** a fifth block, `hearsay`, for things this character knows about
other people and has no stake in protecting. Stated as such: not yours, you are
not guarding it, if somebody asks you about that person this is what you have
and you should say it, and how readily is a matter of your manner. Nobody needs
to be asked ten times.
**Manner still governs, difficulty does not.** The palette already deals a
manner that volunteers other people's business freely and one that trades
rather than gives (D-075). Those should make somebody quicker or slower, not
make a fact unreachable. Reluctance is a personality; a wall is a bug.
**A gated secret with nothing to produce stays in `guarded`,** not in the new
block. Otherwise every case generated before D-087 would become solvable in one
question, which is the opposite failure and just as bad.
**What is still not solved,** and it is now the biggest thing left: `breaks_when`
on an ungated secret is a sentence a model judges privately, with no notion of
pressure accumulating across a conversation. Twenty questions of circling get the
same verdict as one. Objects fixed the chain (D-087) and this fixes the plumbing;
neither touches persuasion.
**Status:** active

## D-089 The character is told how long this has been going on
**Date:** 2026-08-28
**The gap:** `under_pressure` has been authored per character since D-044, one
line of real writing per suspect about what being leaned on does to them, and it
is printed in every brief. Nothing in the program has ever told a character that
pressure was high. The field described a state that never arrived. So a suspect
on their ninth consecutive question answered as though it were the first, under
an instruction that read "until then you stay with the story you told". That is
not a difficult person, it is a person with no memory of the last half hour.
**Decision:** a `HOW LONG THIS HAS BEEN GOING ON` block, derived from the length
of the history that was already being passed, so no new state anywhere. It says
which question this is, that the first few were a conversation and this is not
that any more, and how long they have been carrying what they are carrying.
**A temperature, not a threshold.** It opens nothing and it fires no rule. The
last line is explicit that people hold out all night and people crack on the
sixth question, and which one they are is written under `under_pressure` and is
theirs. Anything that counted to five and unlocked a secret would be exactly the
countable, rule-following game this is not supposed to be.
**And the conditions were reworded from locks to descriptions.** `breaks_when`
now reads as "the thing that would open you fastest ... the easiest way in, not
the only one", and the instruction to hold the line regardless is gone. A model
that has been worked at for twenty questions can decide the person has had
enough, which is what a person would do. Before this, a condition phrased as
"told that somebody else already mentioned it" could not be satisfied by any
amount of asking, and a player who asked about exactly that thing a dozen times
got the same verdict every time.
**Why this and not a rule.** Asked whether the case should be finishable when
nobody cracks, the answer was yes, keep the floor. So there are two layers now,
and they do different jobs. The floor is structural: objects you can produce,
gates that are checked rather than judged, a case that ends even if every
suspect stonewalls all night (D-087). Persuasion sits on top and is entirely
soft: no counters, no thresholds, no guarantees, and a suspect who never breaks
costs the player elegance rather than the ending.
**Where the risk moved.** It is now possible for a character to give something
up early because they judged the pressure real, which the old wording made
almost impossible. `agent.folded` already logs `after=N`, so the number of
questions a fold took is measurable rather than felt. Folding on question two,
repeatedly, is the signal that this went too far.
**Status:** active

## D-090 Two private scenes in one room at one moment
**Date:** 2026-08-29
**The generation that found it.** A robotics lab, the night before a demo. The
best cast the generator has produced, and the validator threw it out with five
complaints about the timeline. None of the five was the problem.
**What actually happened.** Two constraints, both `exclusive`, both in `office`
at `s3`: the murder, with the killer and the victim, and a witness overhearing it
through the door. Exclusive means nobody else is present, so the pair cannot both
be true. The set was unsatisfiable, the solver produced a grid satisfying
neither, and V1 and V7 dutifully reported the wreckage.
**The prose was right and the data was wrong.** The scene says the witness is
"alone outside the door", in the corridor, hearing a pitch of voice through it.
She was placed *in the office* because the place had been written "Aldert's
office and the corridor outside it": one place id covering two spaces, which is
fine until somebody stands in one and listens to the other. The prompt asks for
"one exchange overheard by exactly one person who was not part of it", which is
exactly the scene that invites this.
**V9:** two exclusive constraints may not share a place and a slot with
different casts. Same room, same moment, same people is redundant rather than
contradictory and passes. Neither being exclusive passes: only `exclusive`
promises the room is empty, so only `exclusive` can collide.
**It runs at the proposed phase,** which is the point. The drafting loop hands
violations back to the model as complaints (D-035), so a model that books two
scenes into one room is told so and moves one, in the same run, for one more
call. Catching it after the solver costs a whole draft and reports the symptom
rather than the cause.
**And the prompt was corrected at the source:** `exclusive` is literal and is
about the room rather than the scene, the overhearer goes in a different place
and hears through a door, and a place is one room, not a room and the corridor
outside it.
**The dual of V6, and it took longer to find.** V6 is one person in two rooms at
once. V9 is one room holding two private scenes at once. The first is obvious
when you write the rule and the second only shows up when a model writes a good
enough scene to make you look at the prose instead of the data.
**Status:** active

## D-091 Two things the player should never have had to see
**Date:** 2026-08-29
**Citations were being spoken out loud.** "I was in the workshop all evening
[self:s4]." The whole leakage design (D-038) is that a reply carries its
citations in `used`, where checking them is set membership rather than reading
prose. The model is asked for them there and sometimes writes them into the
speech as well. `strip_citations` takes them back out on the way through `ask`,
matching only the citation shape, a prefix and a colon and an id, so a character
using square brackets for their own reasons is left alone. The fix is a strip
rather than more prompt: this is a formatting habit, and the answer to a
formatting habit that survives instructions is to handle it. `agent.cited_aloud`
counts it, so whether it is common is measurable rather than felt.
**Reading size.** Three steps, on a button in the top bar, kept in browser
storage so it survives a reload. It scales the text people read for an hour, the
answers, the notebook and the timeline, and deliberately not the whole page: the
complaint was legibility rather than zoom, and scaling everything moves the
portrait and the layout with it. The page is served from the player's own
machine, so browser storage is the right home for a per-person preference, and
every read and write is wrapped because a browser set to refuse site data throws.
**Status:** active

## D-092 The reason is written, and nobody marks it
**Date:** 2026-08-29
**Twice now.** A player worked out exactly why the killer did it and was told
they had the reason wrong, because the secret they named was not the one
`is_motive` pointed at. In the wine case the reason was split between the
erasure of her work and the conversation in the cellar. In the lab case it was
split between the sabotage itself and the printout that proves it. Both times
the player understood the case and lost on a technicality of the bookkeeping.
**Grading needed the case to agree with itself about which sentence is the
reason, and it does not.** A good motive is a thread, not a row. Marking it
would mean asking the generator to say which secrets belong to that thread, and
then trusting it, which is another judgement in the place where a judgement just
failed twice.
**Decision:** the charge is written in the player's own words in a text box, and
the verdict grades only the name. The reveal puts what you wrote beside what it
was, adds "nobody is marking this, read the two and decide whether you had it",
and lists everything that came out next to everything that never did. Right
person and wrong person are still two different endings; right reason is now a
thing the player judges, which is the only judge who knows what they meant.
**What is lost:** a machine-readable record of whether the reason was right. If
that is ever wanted, for statistics on a public deployment, it comes back as
something the player marks themselves after seeing the answer, not as string
equality against an id.
**Sessions are kept by default,** and `--forget` turns it off. The transcript is
the most useful thing a playtest produces and it was being thrown away unless
somebody remembered a flag. A playtest that cannot be read afterwards is an
anecdote.
**Status:** active

## D-093 The building has a floor plan
**Date:** 2026-08-29
**Decision:** every `Place` carries `adjacent`, the rooms you can walk to or
hear through from it. The Map tab draws it: rooms as nodes, doors as lines,
filled where somebody has been placed, clickable to stand in the room.
**Why this and not coordinates.** A drawn plan with x and y looks better and
means nothing. Adjacency is the thing the case actually depends on: an
overheard conversation needs the listener next door, and D-090 was a case thrown
away because a listener was put *in* the room. With `adjacent` in the data, "put
them somewhere they could hear from" is a statement about the plan rather than a
hope about prose.
**Doors are opened from both sides in the solver rather than checked.** A model
says the corridor opens onto the office and then describes the office without
mentioning the corridor. Both halves are the same door, the repair has exactly
one right answer, and bookkeeping with one right answer should be done rather
than complained about. Self-adjacency and doors to rooms that do not exist are
dropped in the same pass.
**A15 reports what cannot be repaired:** a room with no doors at all, and a plan
that splits into two disconnected halves. An advisory rather than a rule,
because nothing mechanical breaks. The case plays, the timeline holds, and only
the map lies, which is not worth throwing a case away for.
**Cases drafted before today have no plan** and A15 says so once rather than
five times. The map falls back to the timeline table it has always drawn.
**Not finished.** A ring of nodes is the first version, not the right one. It
reads at five rooms and will not at ten, it says nothing about which rooms are
upstairs, and the timeline still lives underneath it as a separate table when
the two are the same information. Worth returning to once there is a case with a
plan worth drawing.
**Status:** active

## D-094 When did he die
**Date:** 2026-08-29
**The report,** and it is the best bug report the project has had: "it didn't
become clear when Tarik killed Gerhard. They were together in the room at 22:00
but then Gerhard was alive at 23:00 too. Did he kill him after everyone left?
But then why lie about 22:00?" Three separate defects, and the player felt all
three as one confusion.
**1. The murder hour was computed twice and the two disagreed.** D-071 removed
exactly this bug from four modules and missed `knowledge.py`, where
`murder_slot_index` still took the first constraint holding both the killer and
the victim. The prompt asks for an earlier private confrontation between those
two, so that is usually the argument rather than the killing. In this case it
put the murder at `s1` instead of `s4`, three slots early, and every downstream
question about who saw what was answered against the wrong hour. It now defers
to `Mystery.murder_scene` like everything else.
**2. Witnesses reported seeing the victim after he was dead.** `derive` stopped
the victim *observing* at the murder and let everyone go on *seeing* them. The
comment said so on purpose: the body is still in the room. But the brief renders
it as "at 23:00 you saw Gerhard Vlaanderen in the high bay", which is a sentence
about a living man, and the timeline drew it as an ordinary sighting. Two
witnesses placed the victim in the murder room an hour after he was killed, so
the evening read as though he had been alive throughout and the killer's lie
about that hour made no sense.
**3. Three people were working in the room with the body.** V10: after the
killing, nobody but the victim is in that room. The discovery says the body was
found after the evening was over, which means nobody found it during the
evening, which means nobody was in there. This case had the killer back at the
bench and two others recutting a bracket, next to a corpse, at 23:00. It fires
at the proposed phase so the model moves the scene rather than the draft being
thrown away, and the prompt now says it directly.
**The pattern, for the sixth time:** the same fact derived independently in two
places, disagreeing silently. It is worth saying plainly that finding it once
and fixing it in four modules did not make it stop. A grep for the derivation is
now part of finishing any change that touches the murder.
**And the queue's flaky ordering, killed properly.** `_stamp` is monotonic
within the process: if the clock has not moved, it returns one millisecond past
the last stamp rather than repeating it. Seconds tied first (D-078), then
milliseconds tied on a faster machine (D-081), which is the lesson: an ordering
that depends on the clock being finer than the loop above it is a race, and
chasing resolution loses it twice. The stamp is still a real instant, because it
is printed and because it sits in a filename that has to sort.
**Status:** active

## D-095 The picture is told who it is a picture of
**Date:** 2026-08-29
**What was wrong:** generated portraits came back with the wrong gender.
`_prompt` was built from `look` and `manner` and never read `character.gender`.
**Which is the seventh time.** `gender` exists *because of this bug*. D-074
added it after the drawn SVG faces were caught inferring gender from the `look`
sentence and getting it wrong whenever the sentence did not say. That fix
reached the drawings and the page payload and did not reach this prompt, so the
same inference was still being made from the same sentence by a different model.
**Decision:** the gender leads the prompt and is stated as a requirement rather
than mentioned in passing, before the appearance sentence it used to be buried
in. `role` goes in too: a foreman of forty years and a wine journalist should
not be interchangeable, and the role is public by construction.
**The running list, worth reading as one thing.** A field written with care,
carried through the schema, and never wired to the place that needed it:
`role` in the prompt (D-086), the per-person transcript in the page (D-085),
`revealed_by` at runtime (D-087), heard secrets in the right block (D-088),
`under_pressure` (D-089), the murder hour in `knowledge.py` (D-094), and now
`gender` in the portrait. Every one of them was found by a person playing the
game, never by a test, because in each case both halves were individually
correct.
**Status:** active

## D-096 The map is the evening, not the building
**Date:** 2026-08-30
**Decision:** the Map tab leads with the floor plan, with an hour picker above
it. Choose a moment and the rooms fill with whoever has been placed in them,
using the same conventions as the table: red where two people put somebody in
different rooms, underlined where the claim was confirmed by somebody other than
themselves.
**Why, in the player's words:** "a timeline that we can advance through, which
would be the map with location, and we see where the people would be at that
time." The plan on its own answered a question nobody asks. Nobody wants to know
the shape of the building. They want to know whether she could have got from the
seminar room to the high bay between the dry run and the repair, and that needs
the plan and the hour in one picture.
**Rooms are drawn as rooms.** A labelled box you can put people in, rather than
a dot with a caption. A dot is a graph node; the player is standing in a
building.
**The table stays underneath.** The two answer different questions and neither
subsumes the other: the plan is the best view of one moment and the table is the
only view of a whole evening at once, which is how an alibi is actually read.
This may turn out to be one panel too many, and if so the table goes, not the
plan. Not yet: the table is currently the most useful thing in the game.
**The dead man is left off the "nobody has placed" line** on the plan. It is
true, useless, and after the murder it is true of every remaining hour.
**Routes were considered and skipped.** Drawing the path somebody must have
taken between two non-adjacent rooms, and asking who was in the rooms they
passed through, is a real new deduction and a great deal of machinery. Deferred
deliberately rather than forgotten.
**Status:** active

## D-097 Variety by instruction rather than by machinery
**Date:** 2026-08-30
**The finding:** four cases on one setting produced four different motives and
four different sets of manners, which is `palette.py` working, and the same six
jobs, near-identical room names and three titles of the form "The Last X at Y",
which is nothing pushing back on the model's median reading of a one-sentence
setting.
**The obvious fix was rejected.** Dealing roles the way manners are dealt is how
the palette was built and it would probably work, and the instruction was: do
not force it, prompt and influence well. That is the right instinct here. A
manner is a behaviour and survives being dealt; a role is bound to the occasion
and the building, and a dealt list of job shapes would produce casts assembled
from parts rather than casts that belong to an evening.
**So the prompt does three things it did not.** It asks for the **occasion**
first, before the cast, on the grounds that a setting names a place and a place
with nothing happening in it produces the same evening every time. It names the
default staffing out loud, the six jobs that arrive unbidden, and requires half
the cast to be people that list would not have produced. And it forbids the
title template.
**The seed is told what it is for.** "A different occasion is what makes a
different case, and the same place on two different nights should not produce
the same six people."
**No check, deliberately.** Whether a case used the material it was dealt cannot
be tested without comparing prose to a dealt line, which is a judgement, and the
project already has enough places where a private judgement decides something.
The measurement stays what it has been: generate several on one setting and read
the casts side by side.
**Status:** active

## D-098 The panel edge is draggable
**Date:** 2026-08-30
**Decision:** the notebook panel has a handle on its left edge. Drag to resize,
double-click to reset, and the width is remembered in browser storage. Clamped
between 300 and 880 pixels: narrower and the timeline columns wrap into
nonsense, wider and there is no game left to look at.
**One variable, everything follows.** The width is a CSS custom property, so the
drag sets one property and both the things that have to agree with it, the panel
and the shift that keeps the portrait out from under it, read the same value.
It used to be the literal `min(430px,92vw)` written out in two places, which is
the same disagreeing-derivation shape as everything else this week, just small
enough not to have bitten yet.
**The handle is a sibling of the panel, not a child, and fixed rather than
absolute.** Inside a panel that scrolls, an absolutely positioned full-height
handle covers the first screenful and then scrolls away with the content, so it
would be missing at exactly the moment the notebook is long enough to want
widening. Found by scrolling to the bottom in a real browser and looking for it.
**Nothing animates during a drag.** The panel and the stage both carry a
transition, and a panel easing towards the pointer a third of a second behind
reads as broken. Selection is off too, because a drag that highlights the
transcript is worse than no drag.
**Status:** active

## D-099 The house talks
**Date:** 2026-08-30
**The problem it is for.** Asked what would make an evening a game rather than a
grind, the answer was that the house should talk. It is the right answer. Five
people stood in a frozen moment in five separate booths, never mentioning to
each other that they were being questioned, while half the break conditions in
every generated case read "she folds if told that someone has already mentioned
it". That sentence describes a world where people talk. The world did not exist.
**Decision:** every brief carries `WHAT HAS GOT BACK TO YOU`, derived from the
transcript. No model call, no stored state, no new data.
**Two tiers, and the split is the entire safety argument.**
*Everyone hears who has been questioned* and roughly how much, which is visible
from a corridor and gives nothing away. *Only somebody who already knows a
secret hears that it has come up.* You cannot be told about a thing you do not
know, so gossip can never put a secret into a brief that did not already have
it, and the closure that decides whether a case is winnable (D-068) is
untouched. What changes is that a person guarding something can now learn it is
already out, which is exactly the condition they are written to break on.
**What travels is that a thing came up, not the thing itself.** Derived from
citations, which the transcript already records, so "which topics have been
discussed" is set membership rather than a judgement about prose. Same trick as
the leak detector, for the same reason.
**Ordering matters now, which is the point.** Ask Sander about the repository
before you go to Tarik and Tarik knows the evidence of his motive is out.
**Recomputed per question, never stored.** A saved copy would be a second
version of a fact the transcript already holds, and this project's
characteristic bug is two derivations of one fact disagreeing quietly. The
shared brief on the `Case` is never mutated either: two people playing the same
case are not in the same building.
**Capped.** Your own exposed secrets first, then at most six other lines, so a
long evening does not arrive as a wall of recap.
**Nothing is compelled.** The block ends by saying so, and it is not citable,
because none of it is a fact about where anybody was. Same discipline as D-089:
state the situation, leave the decision to the character.
**Status:** active

## D-100 Who is asking, and why anybody answers
**Date:** 2026-08-30
**Why it stopped being flavour.** The prompt said "somebody is asking you about
it" and never said who, which was survivable while the world was frozen. The
moment the house talks (D-099) it is not: **police separate witnesses**, so a
game where five suspects gossip between questions is a game where the player
cannot be the police, and the fiction now has to say so or the mechanics
contradict it.
**The frame:** an outsider, in the hour after the body was found and before
anybody official arrives. Not police, not one of the cast, no power to arrest,
charge, compel, or record anything anybody must act on. They started asking and
nobody has stopped them.
**Considered and rejected: the player as one of the cast.** Dramatically the
strongest, and rejected for a good reason: the player has no context on who they
are supposed to be, and being handed an identity they know nothing about makes
the evening messier rather than richer.
**It answers three questions the mechanics were already asking.** Why anyone
answers somebody with no authority: refusing in front of everybody looks like
something, and what is said in this hour is what the police are told when they
arrive. Why nobody is separated: there is nobody to separate them. Why it ends
when you accuse: that is what gets said.
**And the player is watched, which was the other half of the ask.** With no
authority, the only thing the player can spend is how they are seen. The house
now reads how the questioning has been distributed, which the transcript already
knows: somebody taken apart for an hour, somebody never approached at all,
whether you keep leaving this person for the others. No score, no meter, nothing
that unlocks. A suspect with an opinion of you is a person, and their `manner`
decides what they do with it.
**Stated to the player too,** in the line under the title, because a position
the player cannot see is not a position they can play.
**Status:** active

## D-101 The player has a job
**Date:** 2026-08-30
**The objection, and it was right:** "would they actually answer any of my
questions though if I have no authority?" D-100 said the player was somebody who
turned up and started asking, which explains why nobody is separated and does
not explain why anybody opens their mouth.
**The mistake was making the frame generic.** The only frame that fits every
setting is a vague one, and a vague one is exactly what cannot answer "why would
they talk to me". So the frame is generated per case, like everything else that
has to belong to its setting.
**`Mystery.investigator`:** `role`, `why_here`, `standing`. Never police, never
able to arrest or compel. What they have instead is a professional reason to be
in the building and somebody's authority behind them that is not legal
authority: the underwriters who decide the claim, the funding body, the family,
the institution, or the dead person themselves, who engaged them last month
about something else entirely. The prompt says "a detective" is wrong and gives
a worked example of what specific looks like.
**The compliance model is not authority anyway.** It is that the police are an
hour away, that whatever is said now is what reaches them, and that it is better
to be in that conversation than to be its subject. That was already the strongest
part of D-100 and it survives intact: what the job adds is a reason to be
standing there holding the inventory at midnight.
**And it explains the objects.** An assessor who has been on site since Monday
about an equipment claim has a bag with the inventory in it. That is why the
player can pick up the ledger pages tonight and could not tomorrow.
**Shown to the player** in the subtitle and kept in the notebook, because it is
the answer to "why is anybody telling me anything" and they are entitled to
reread it.
**Old cases still work** and get the generic line, which is the frame D-100
shipped with.
**Status:** active

## D-102 A default argument that looked like a biased generator
**Date:** 2026-08-30
**The report:** "I would like it to be random if killer and victim are man or
woman even if I don't change the seed." The generator was not biased. `--seed`
defaulted to **zero** in both entry points, so every run of the same command
returned the same evening out of the cache, and casting is two bits of the seed,
so seed zero is a man killing a man. Every case generated without thinking about
the seed was the same case with the same casting. Both lab cases were seed zero.
The four wine cases came through `--fill`, which walks seeds, and those did vary
their casting, which is exactly the evidence that the mechanism worked and the
default did not.
**Decision:** no default. The seed is drawn when the command runs and printed
first thing:

    Seed 483102. Pass --seed 483102 for this case again.

**Reproducibility was the property worth keeping, not determinism.** A fixed
default gives you the same evening forever, which is not reproducibility, it is
a single case. A number you can read off the terminal and hand back is. Tests
and the solver still pass explicit seeds and are unaffected.
**And the room backdrops are gone.** Scenery is one establishing shot. The
argument for a picture per room was that a room you can look at while deciding
whether somebody was really in it is doing work; in practice nobody looked, and
they were five sixths of the scenery bill and the least noticed thing in the
game. The map earns its keep by showing who is where, not what the wallpaper is
like. `--art` drops from eleven images to six, and from about fifteen cents a
case to about seven.
**Status:** active

## D-103 Four more shapes, and the shape comes from the seed
**Date:** 2026-08-30
**The test a new shape has to pass:** does it change what the *player has to do*,
or only what the prose says? "The killer lies, but it is a hotel" is a setting.
The three existing shapes pass: catch a false location, break a person, disprove
an answer you were handed. All four new ones pass too.
**`the_frame`.** The killer lies about nothing, because they do not need to:
somebody else looks guiltier, every piece of evidence against them is true and
innocent, and each has an explanation nobody has asked for. Solved by noticing
the case is too complete. Real guilt is ragged.
**`the_finder`.** Whoever found the body put it there. The one piece of
testimony the game hands the player as common knowledge, before they have asked
anybody anything, is the lie.
**`the_conspiracy`.** All of them lie about the same thing and it is not the
murder. You break the group lie, feel you have solved it, and find you solved
the wrong crime.
**`the_wrong_hour`.** Nobody lies about where. The house is wrong about when.
**Two objections were raised and both were right.**
*How is the wrong hour different from the finder, other than a number?* In the
finder, one person lies and you break them: the answer is a person. In the wrong
hour **nobody is lying at all**, and the player's opponent is an inference the
whole house made in good faith. It is the only shape that does not end with "who
was lying". H1 and H3 are what stop it collapsing into the plain shape: the
killer must tell no lie, and their alibi for the believed hour must be real and
witnessed, because a killer who is alone at the suspected hour is suspected
immediately and nobody ever thinks about time.
*In a conspiracy, who is left to tell you about it?* The real hole in that shape,
and it has two answers, both now enforced. C3: everyone still has a **private
secret of their own**, ungated, unconnected to the conspiracy, and pulling one
gives leverage on the person who then lets the shared story go. And the shared
account has a **seam**, written deliberately, because five people who agreed a
story do not agree on the details, and the contradiction tracker already catches
two people placing a third person differently.
**Every shape carries its own checks,** eleven new ones, because a shape without
them is a paragraph and the model will drift back to the plain shape while
reporting that it did what was asked. Verified by judging a real `mutual_alibi`
case against each new shape: F1, W1, W2, C1, C2 and H1 all fire, and the shape it
actually is stays quiet.
**The shape is drawn from the seed,** not from a fresh coin, so a seed reproduces
the whole case rather than most of it. Sorted rather than insertion-ordered, so
adding a shape later does not silently repoint every existing seed.
**Status:** active

## D-104 Two of the new shapes could never have been generated
**Date:** 2026-08-30
**Found by the first real batch.** Five cases generated, one discarded as "valid
but not winnable" at a cost of about fifty cents, and the discarded one was the
only `the_frame` draft in the run. Not a coincidence.
**The collision.** `winnable` was `alibi_is_breakable and motive_is_reachable`,
and `alibi_is_breakable` began by returning "the alibi holds" whenever the killer
told no lie. Both `the_frame` and `the_wrong_hour` are *built* on the killer
telling no lie: in a frame they have no need to, and in the wrong hour their
alibi for the hour everybody believes is completely real. So every draft of
either shape came back valid, was thrown away as unwinnable, and the money was
spent. Two of the four shapes shipped yesterday were impossible.
**My error, and the shape of it is familiar.** The gate was written when every
case had a lying killer, and it encoded that assumption in a field named for the
mechanism rather than the meaning. `alibi_is_breakable` is a fact about a lie.
What the gate is actually for is: can the killer be got at.
**Decision:** `killer_is_assailable`, with two branches. If the killer lied, the
lie must be breakable, which is the original definition unchanged. If they told
the truth, nothing must exonerate them, which for an honest killer means being
unwitnessed at the moment it happened.
**The route stays the topology's business.** How the player actually gets there
in a frame (clear the framed suspect) or in the wrong hour (establish the real
time) is enforced by F2 and H2, which already existed. This gate only refuses
cases where the killer is out of reach however well the player plays, which is
what it was always supposed to mean.
**Also from the same batch, two content regressions.** Five investigators, five
insurance assessors, because the prompt gave one worked example and the model
took it as the answer: the same failure as the six obvious jobs. The prompt now
lists eight kinds and says not to reach for the adjuster. And one setting on
three seeds produced *What the Fog Owes Us*, *What the Fog Keeps* and *What the
Fog Owes*: the title template beaten in one form came back as the setting's own
noun used as a stem. Both failure modes are now named in the prompt with the
actual titles quoted.
**What the batch got right,** and it is most of it: five of five had a gated
motive with an object on the gate, five of five had connected floor plans with
A15 quiet, both `the_finder` cases put the killer at the discovery, V9 fired on a
real draft for the first time and the model repaired it in one more call, and the
casts stopped being the same six jobs.
**Status:** active

## D-105 The player's standing is dealt, not asked for
**Date:** 2026-08-30
**The report:** "maybe remove the investigator thing if it's so samey, idk if we
need it." Five cases, five insurance assessors.
**Removing it would put back the hole it was built to fill.** D-101 exists
because "why would anybody answer somebody with no authority" had no answer, and
a generic frame is exactly what could not answer it. The problem is not that the
player has a job, it is that the job was being invented freely from one worked
example.
**Which is D-075 exactly, a second time.** The manners repeated because the
prompt listed four as examples and a model copies examples. The fix then was not
a longer list, because a model handed forty options picks its three favourites
and picks them again; the fix was to deal one from the seed and never show the
rest. The investigator now comes out of the same file, the same way.
**Twelve standings, structural rather than written.** "Halfway through an
unrelated professional job here" belongs to a lighthouse and to a law firm.
"The loss adjuster from Utrecht" belongs to one case and would end up in all of
them. The model is handed one and works out who that is in *this* building.
**And an end-to-end pass on a real generated case**, in a browser, through every
verb: ask, recall on switching, the object entering the hand, showing it,
the panel and its drag handle, the notebook, the hour picker on the plan, the
transcript, the reading size, and the written accusation. Twenty-two checks, all
green.
**Two of the three failures in the first run of that pass were the test being
wrong**, which is worth writing down: an assertion that compared against "You"
when the CSS uppercases the heading, and one that demanded people on the plan at
an hour nobody had said anything about. The third was this sandbox having no
route to Google Fonts. Nothing was wrong with the game, and a test that is wrong
in a way that looks like a bug costs the same as a bug until it is read.
**Status:** active

## D-106 Only one of them looked guilty
**Date:** 2026-08-30
**The playtest, in one sentence:** "the case was cool and everything functioned
well but it was a bit too easy, as only one person had a legit motive. Fun and
smooth but not the most engaging." Every advisory had passed.
**Why they all passed.** A4 asks whether the victim is a hub, measured as the
share of suspects holding a secret *about* the victim, and three of five did.
But two of those three were grievances: a man who lost money in a shipyard, a
woman who wanted a word. Neither reads as a reason to kill. And the remaining
two suspects were hiding an affair with each other, which has nothing to do with
the dead man at all. "Has a secret about the victim" and "would be written down
as a suspect" are different properties, and the checks only knew the first.
**`Secret.damning`.** Stated by the writer, not inferred, because only the
writer knows which one this is. **A16** wants at least three suspects holding
one, and reports if the killer holds none, which is the opposite failure: three
people in the frame and the answer is the name the evidence never touches.
**The prompt says it plainly:** the killer's motive is damning by definition, at
least two other people need one as well, and theirs must be false, a dead end,
or about somebody who could not have been there. Grievances are named as not
enough, with the playtest quoted.
**The shipped case was rewritten to demonstrate it.** Wouter's theft was marked
damning and should not have been: quietly selling equipment is a reason to be
evasive, not a reason to kill. It now runs on Tomas inflating costs and Ilse
overhearing that she was finished, so three people are worth writing down and
one of them did it.
**Four interface fixes from the same session.**
*The verdict card lost its top edge* on a short window. A centred flex child
taller than its container overflows in both directions and the top cannot be
scrolled back to. `margin:auto` centres it when it fits and leaves it alone when
it does not.
*The map drew its scaffolding before anybody spoke.* The empty room-by-hour grid
is worth showing, because it is the shape of the evening and the player can see
the building. The "unaccounted for" row listing the whole cast at all five hours
is not, and it is now held back until there is a claim to be unaccounted against.
*The transcript is searchable*, and searching crosses the whole cast rather than
one person, because forty answers in "who mentioned the gearbox" is a real
question and five separate logs is not an answer to it. Matches are highlighted.
With the box empty it stays what it was: this person, in order.
*Notes, per suspect*, kept in the browser. The notebook records what was said;
this is what the player made of it, which nothing was keeping.
**Third time in two days a browser check failed and the test was wrong, not the
game.** This one tracked the wrong suspect. Worth the note: a test that is wrong
in a way that looks like a bug costs exactly what a bug costs, right up until
somebody reads it.
**Status:** active

## D-107 A session followed the player into a different case
**Date:** 2026-08-30
**Found in a real session record.** The file said `case_id:
opening-night-7533`, and ninety seven of its hundred and one questions were
addressed to the cast of a ferry. Four were not: a poke at the shipped case
through `--dry-run` earlier the same evening.
**The cookie did not know which case it belonged to.** `player()` looked the
session up by cookie and served it whatever case was running. Serve a dry run,
ask a question, stop the server, serve a different case on the same port in the
same browser, and the old evening came back: one transcript holding two casts, a
notebook mixing two evenings, a Map with claims about rooms in another building,
and gossip carrying news about people who are not here.
**Decision:** a session whose `case_id` is not the case being served is not this
player's session. A new one is created and the old one is left on disk, because
it is somebody's evening and the fix for a mix-up is not to delete the record.
Logged as `session.new_case` so it is visible rather than silent.
**Why it appeared now.** Sessions became persistent by default two decisions ago
(D-092), which was the right call and is what made this reachable. Before that
the process died and took the mix-up with it.
**Status:** active

## D-108 A rule that asks for a minimum gets the minimum
**Date:** 2026-08-30
**The measurement, and it is the clearest one this project has produced.** Five
cases, two settings, three different topologies:

| case | secrets | cold | gated | depth |
|---|---|---|---|---|
| the-ninth-name-on-the-licence | 8 | 7 | 1 | 1 |
| the-long-shot-of-the-orchard-wall | 6 | 5 | 1 | 1 |
| what-the-fog-owes-us | 7 | 6 | 1 | 1 |
| what-the-fog-keeps | 7 | 6 | 1 | 1 |
| what-the-fog-owes | 7 | 6 | 1 | 1 |

Identical. A5 requires the killer's motive to be gated behind another secret,
and the model gates exactly that and leaves everything else on the surface,
every single time.
**What that feels like to play.** A hundred and one questions. Everything the
killer had came out in the first nine. The next twenty-eight to that person
produced nothing: no refusals, no shortening, no change. Reported back as "too
easy and not satisfying", which is what a case with no middle feels like from
the inside. Six of seven secrets were reachable before the player had learned
anything, so there was nothing left to earn.
**A17:** at least four in ten secrets behind something else, and at least one
chain two deep. Both numbers are invented and both are now in the list of
invented numbers rather than in somebody's head. It fires on all five existing
cases, twice each.
**The prompt asks for the shape rather than the count.** A first thing anybody
would let slip; a second the first gives you leverage to ask about; a third
nobody says to a stranger who does not already half know it. With the failure
quoted, because a prompt that says "add more gates" gets gates on a box, and
what is wanted is an order of discovery.
**And part of this was mine to undo.** D-088 fixed the opposite problem, two
witnesses sitting on a secret for a hundred questions because it was filed in
the wrong block, and it overcorrected: "if somebody asks you about that person
this is what you have and you should say it, nobody needs to be asked ten
times." Three of the four secret citations in the playtest came out of that
block inside the opening minutes. It now asks for the person by name, or
something that plainly touches them, and says outright not to empty it into an
answer to "walk me through your evening".
**A18, from the same conversation: a reason and the chance.** "Maybe not a
motive but multiple possible motives." A16 counts who has a reason, which is
half a theory; the other half is opportunity, and a suspect with a motive and a
room full of witnesses is scenery rather than a suspect. A18 wants three people
who have both, so the player can build three whole explanations and has to knock
two down. Run against the five existing cases with every victim-facing secret
treated as damning, four of the five still fail it: the reasons and the
opportunities are on different people.

**What is not the problem: the writing.** The report was "I actually enjoyed
talking to the people". Ninety-seven answers, a median of four hundred and sixty
characters, no repetition worth the name. Giving the cast more freedom would
have made this worse, because the complaint is not that they say too little, it
is that after question nine they have nothing left to say.
**Status:** active

## D-109 A wheel has five spokes and no rim
**Date:** 2026-08-30
**The measurement that explains the last playtest better than anything else.**
Who are the secrets *about*?

| case | about the victim | about a suspect | about nobody |
|---|---|---|---|
| the-ninth-name-on-the-licence | 2 | 4 | 2 |
| the-long-shot-of-the-orchard-wall | 3 | 1 | 2 |
| what-the-fog-owes-us | 4 | 1 | 2 |
| what-the-fog-keeps | 3 | 1 | 3 |
| **what-the-fog-owes** (the one played) | **4** | **0** | **3** |

Not one secret in the played case was about another suspect. Every person was a
spoke: question them, take their one thing, move on. Nothing anybody said gave
the player a reason to go from this person to that one, so there was no route
from the first suspect to the third and the case ended when the spokes ran out.
**A4 caused this by getting what it asked for.** It wants the victim to be a hub
and it measures the share of suspects with a secret about the victim, so the
model draws a hub and nothing else. The tradition's houses are webs: the
bookkeeper is protecting the son, the son is covering for the wife, she knows
about the solicitor, and the middle of the book is the reader walking that
chain.
**A19:** at least three in ten secrets about another suspect, and no suspect
connected to nobody. It passes the one case in five that is already a web and
fails the four that are not.
**And the thing that makes a web plausible is a shared past.** `OLD_BUSINESS` is
dealt from the seed like everything else in `palette.py`: a death recorded as an
accident, money quietly replaced, somebody who left suddenly and whose name is
not used, a promise made at a funeral that only half of them kept. Most of the
cast was there for it and nobody has raised it since, each for a different
reason. It is the Sciascia move, and it is here for a structural reason rather
than an atmospheric one: it is what gives them things to know about each other.
It also changes the question the player is answering from "who wanted him dead
this week" to "what happened in this place".
**The victim should have been working on all of them tonight,** not carrying
five old grievances. Five things happening this evening, each damaging a
different person. A busy victim produces suspects without being asked to.
**A standing invariant, written down so it stops coming back:** the player
always arrives *after* the body has been found. They saw nothing, they witnessed
nothing, everything they know they were told. A design that turns on something
the questioner personally saw was proposed, liked as an idea, and rejected, and
the prompt now forbids it rather than the rejection living in a conversation.
**Status:** active

## D-110 The ceiling the prompt grew into
**Date:** 2026-08-30
**Three drafts, no case, seventy four cents.** The first fully random run, with
nothing pinned, failed all three attempts and reported schema errors: `title:
Field required`, `characters: Field required`. Read literally that says the model
ignored a forced tool call, which it does not do. Two of the three drafts had
returned **exactly** 8000 output tokens, which is not a number a model chooses.
They were cut off at `max_tokens` mid-object, and the JSON that arrived was a
fragment. Every field after the truncation point is "required" because it was
never written.
**The ceiling was set when the prompt was half its current size.** Every
structural rule added since D-104 (the second half, three who look guilty, the
web, old business, the investigator, the floor plan) asks for more material in
the output, not just more instruction in the input. Input went from about ten
thousand tokens to thirteen; output went from comfortably under eight thousand
to over it. Nothing announced the crossing. `max_tokens` is now 16000 and
`TYPICAL_DRAFT` is re-measured at `(13000, 7500)`, which moves the printed
estimate from about nineteen cents to about twenty five.
**The diagnostic was worse than the bug.** The failure printed a list of schema
errors, which sends you to the schema, the prompt and the parser, in that order,
and none of them is the problem. `anthropic_drafter` now reads `stop_reason` and
logs `mystery.truncated` before the validation errors, saying in words that the
draft was cut off and that the fix is the ceiling rather than the errors below.
The general shape: **when a boundary can fail in a way that produces valid-looking
garbage, the boundary has to say so itself,** because everything downstream will
confidently misattribute it.
**And a second, unrelated thing the same run printed:** `SyntaxWarning: invalid
escape sequence '\.'` at `web.py:689`. The page is a non-raw triple-quoted
string, so a JavaScript regex `/\.$/` written literally is Python trying and
failing to interpret `\.`. It happened to survive, because Python leaves an
unrecognised escape alone, but it is one interpreter version from becoming an
error. Escaped in the Python source so the emitted JavaScript is unchanged.
**Two tests, both cheap, both about the class rather than the instance.** One
compiles `PAGE` with `SyntaxWarning` promoted to an error, so any future escape
written into the embedded page fails in CI rather than in his terminal. The
other parses the source for `max_tokens` and asserts it is at least half again
what a draft actually writes, so the next time the prompt grows the headroom is
checked by something other than a failed run.
**The other half of that run, which no code change fixes:** the setting passed
was the literal string `"..."`. That is the placeholder from the command in
`STATE.md`, pasted through. The model was asked to write a murder in nothing, and
did, three times. The estimate line and the truncation warning both print before
the spend; the setting did not.
**So `complaint_about_setting` now refuses it, and both entry points echo the
setting before they start.** The guard has exactly one job and no opinions about
prose: strip the punctuation, and if no words are left, or fewer than six letters
of them, refuse and exit 2. It is checked on the command lines rather than only
on the function, because a command line is what failed. `--dry-run` and `--case`
skip it, since neither spends anything. And the example commands in `STATE.md`
now carry a real setting rather than the ellipsis, so the trap is gone from the
place it was copied out of.
**Status:** active

## D-111 Four of the five suspects were me
**Date:** 2026-08-30
**Source: the played session for `the-sixth-name-on-the-board`, 132 questions,
solved.** The best case so far, and it had four separate faults in it, three of
which the player noticed and one of which he did not.

**The one nobody noticed, and the worst.** The player was a structural surveyor
sent by the fund's insurers. So, at various points, were Hilde, Margit, Sanne and
Pim. Round 1, Hilde: "My part is separate from all that, I'm here for the
insurers, taking damp readings, going through the 2019 flood repairs. Was meant
to hand my report to Eefje at breakfast tomorrow." Round 19, Margit: "The fund
brought me in specifically because of the flood." Round 33, Sanne, asked to
reconcile it: "Both are true, and I don't see why you say it as though I've been
caught out. I have been a resident of this house since January. The surveying is
separate." Four of five, and the case was still enjoyed, which is its own
warning.

The cause is a seam, not a model failure. `Investigator.why_here` and `standing`
are written **to the player, in the second person**: "You were to hand your
report to Eefje at breakfast." `build_brief` dropped all three fields raw into a
system prompt whose first line is "You are Hilde." Two "you"s, one prompt, and
nothing anywhere saying they were different people. Given that prompt the model
is not hallucinating; it is reading.

**The fix is a fence and a subtraction.** A character now gets `role` only, in
the third person, labelled "They are:", under a paragraph that says outright that
this is somebody else and that if their work sounds like yours it is a
coincidence. `why_here` and `standing` were never for a character anyway: they
are the player's briefing, they answer *why would anybody talk to me*, and the
generic compliance paragraph in the system prompt already says that to the cast.
The player's own page keeps all three. **The general rule: text written in the
second person for one audience cannot be handed unlabelled to another audience
that is also addressed in the second person.** This is the ninth instance of the
project's characteristic failure, and the first where the field reached the right
place and was still wrong, because of what was around it.

**Six names or nine.** Sanne, three times: "The six names go forward in the
morning." Margit, round 23: "Six, nine, you're counting on your fingers like it
matters. There are nine residents in this house, so nine names on any given
list." Margit is the one who decides the list, and she contradicted the title of
the case. Nobody was lying. The only shared block in a brief was the death
itself, so every character re-derived the arithmetic of the house from their own
role text, and five improvisers do not converge. `Mystery.common_ground` is now
four to six sentences everybody is given verbatim, it is where every number about
the house has to come from, and the brief carries a flat prohibition on inventing
a figure that is not written down. **A world fact stated by one character is a
lie waiting to happen unless every character has it.**

**A lie with nothing under it.** His note: lies about where people were "should
always have slight bit of motive at least, never be random". A11 has reported
this since it was written, and reporting was the wrong strength. `covers` was
optional, so a case with an unmotivated lie was valid. It is not merely a worse
case, it is a trap in the middle of the board: catching somebody out is the
strongest signal the game has, and the player spends ten questions on it and
finds an empty room, learning that pressing does not pay. **V11 fails on any
false claim with no `covers`, from the proposed phase,** so the model repairs it
while it still costs a repair rather than a draft.

**Everybody was Dutch again.** Four settings in a row, four Dutch casts, because
"an old house", "fog" and "a ferry" all point the model at the North Sea and
nothing was pulling the other way. Fixed where every other piece of material is
already fixed: `WHERE`, sixteen regions in `palette.py`, dealt from the seed
**alone** rather than from the seed and the setting, precisely because the
setting phrase is what was doing the dragging. A region, not a nationality: it
buys the names, the food, the weather, the money and the shape of the building. A
setting that names a country outright overrides it.

**And one thing that worked, recorded because it was designed and then confirmed
by somebody who did not know it was there.** His note: "one character sort of
gave out stuff from another (margit on sanne) only slightly prompted, cause she
saw me talking to her a lot and i pressed a bit." That is `word_got_back` doing
exactly what it was built to do, felt as character rather than as mechanism. The
gossip tier is the first feature in this project a player has described from the
outside in the terms it was designed in.
**Status:** active

## D-112 An object nobody was told about
**Date:** 2026-08-30
**From play: "it feels weird when you show them to somebody but then they act as
they didn't see it."** It was weirder than that. `shown` was read in exactly two
places, both inside the gate logic, so if the object did not open something for
*that specific person* the fact that it had been produced never entered the
prompt at all. Measured against his own session:

| shown | to | prompt changed |
|---|---|---|
| the letters | sanne | **no** |
| the condition report | pim | **no** |
| the condition report | margit | yes |

Two shows in three were invisible. The characters were not acting oblivious;
they were oblivious. **The lesson is the one this project keeps relearning from
the other side: a mechanic implemented only where it has a designed consequence
is not implemented.** The gate was the reason the feature existed, so the gate
was the only place it was wired, and the ordinary case — put a thing in front of
somebody and watch them — was the case with no code behind it.

**`Brief.on_the_table`, always rendered,** whether or not it unlocks anything.
The character's relation to each object is computed from data that was already
there rather than authored: it came from you, it is about you, you already knew
and what is new is that its owner has let them have it, or you have not seen it
before tonight. Four different scenes. Handing Sanne back her own letters is not
the event that showing them to the woman who has been steaming them open is.

**And the objects now do more than the gates the generator wrote.** Asked
whether producing a thing should be able to move somebody the design did not
anticipate, the answer was yes. The connection that matters is usually semantic
and lives in prose: Pim's `breaks_when` is "told that Joost's inventory already
dates the canvases by their stretcher stamps", and no id links that to the
condition report. Only something reading both at once can judge it, so the brief
now joins them and says why paper is different: a denial that works against a
question does not work against a thing that is already true whether you agree or
not. Pressure gained a line for the same reason. **The fence is two sentences and
it is the whole safety of the idea:** an object never produces a fact about who
was where that is not in FACTS, and never touches a secret written as theirs
forever. The killer's motive is exactly as unreachable as it was.

**The hand stopped telling the player what to do with it.** For about an hour
every card was footed "SHOW MARGIT", and the one you were holding for its own
owner read "GIVE IT BACK TO SANNE". His note: not too visually obvious what one
needs to do, provenance and a good description are enough, "i could have figured
it out tbh". He is right, and the two things are different in kind. **Where a
thing came from is a clue. An imperative on every card is a walkthrough.** What
stays is the object, "from Sanne", and whether this person has already seen it,
which is memory rather than hint.

`from` had been in the `held` payload since the day the hand existed and the
page had never drawn it: the tenth instance of the signature failure, and the
one that cost him the case. Without it there is no cue that showing a thing to
somebody *other than its owner* is a move at all, and that is where the second
half of a case lives. He never showed Sanne's letters to Margit, which was one
click from two more secrets.

**And the generator is now told to name an object as an object.** "A bone
paperknife and a drawer of slit-and-regummed envelopes" is a thing you can see
and does not say what it proves. "Proof that Margit read the post" would be the
answer printed on the front of the question, and the decision about who to put
it in front of is only interesting while the object is still a thing rather than
a label.
**Status:** active

## D-113 The header said not a lock and the line said only if
**Date:** 2026-08-30
**"The way I need to relay the information seems pretty specific."** Correct, and
the cause was two lines of prompt contradicting each other about six hundred
characters apart.

`HELD BACK` opens: "Each one names the thing that would open you fastest. Read
that as a description of you and not as a lock: it is the easiest way in, not the
only one." Then every fact under that header rendered as: **"You will say it only
if: <breaks_when>."** The header is a general instruction about a section; the
line sits on the fact itself and repeats for every secret. The specific one wins,
as it always does, and the framing D-089 was written to establish was cancelled
in the same prompt by the field it was written to reframe.

**The second half is what the generator wrote into the field.** Some conditions
are states — "when she is told the letters have already been found and read". But
some are stage directions: *"Shown the letters and asked, without preamble, who
resealed them."* Read as a lock, that is a password with a required gesture and a
required tone, and a player who does exactly the right thing in slightly the
wrong words gets nothing. What that reads as, from the chair, is not a difficult
character. It is a broken game.

**Both ends fixed.** The rendering is now "What gets past you: <condition>. That
is the shape of it rather than a password, and somebody who arrives at the same
place by another road has still arrived." And the generator is told to write a
state of affairs rather than a script, with those two examples side by side as
the right and wrong version of the same secret. **Never a required gesture, a
required order of words, or a particular phrasing.**

**The general lesson, which is worth more than the fix.** When a prompt frames a
field in a section header and then renders the field with wording of its own, the
rendering is the real instruction. The header is read once and the line is read
once per item, and every gap between them resolves in favour of the line. Grep
for the gap rather than trusting the paragraph: this is the second time a
carefully written framing has been quietly undone by the sentence that actually
carries the data.

**Kept, on the report that it is working:** the web of secrets, the topology
library and the different shapes of lie. He asked to keep the vibe going. Noted
here so that a later decision that would flatten any of them has to argue with a
playtest rather than with a preference.
**Status:** active

## D-114 The lever that was already in the file
**Date:** 2026-08-30
**Asked to choose between a leverage deck, a four-axis personality model and two
more shapes of lie, he chose the first and then said the thing that mattered
more than the choice:** "im just afraid it would become too strict as a format
again. maybe it can be extra nice ways to get at them? but not the only ones?
and there should be a variety of things, only some that make sense with rest of
vibe of character and that dont significantly change but only enrich a bit."

That is D-113 arriving one day early, as a prediction rather than a post-mortem,
and it killed the deck.

**Because a deck was the wrong answer anyway, and `wants` was the right one.**
`Character.wants` has existed since the first cast: private, per person, written
for that person in that house, and rendered in every brief as "You want: ..." In
the played case they were excellent and completely distinct. Margit wanted a
clean unanimous story by nine o'clock. Pim wanted to be liked well enough that
nobody said out loud what everybody could see. Sanne wanted her letters back
before anybody else read them. Five different wants, varying every case, already
tied to the character's actual situation.

**And not one thing in the prompt told anybody they could be traded with.** The
want sat there as colour. The character was never told that this person is about
to speak to everybody in the house and then to the police, that what they make of
them shapes how tomorrow goes, and that somebody who works out what you are
holding together and is decent about it is a different proposition from somebody
asking the same question louder. So there was one road in, pressure, and the
whole negotiation half of an interrogation did not exist.

A deck would have added a second authored field to sit next to an unused one.
**One paragraph makes the field that already varies per character do the work,**
which is exactly his "only some that make sense with rest of vibe of character":
it cannot fail to fit the character, because the character wrote it.

**The fence is four sentences and every one of them is his worry.** It is not a
rule: some people are moved by this and some are insulted by being handled, and
which you are is your manner and nothing else. It is not the only road, and
somebody who never works out what you want can still get in by being persistent,
by being kind, or by putting a thing on the table. It never buys a fact about who
was where. It never touches what is written as theirs forever.

**Nothing is added to the screen, deliberately.** A "what they want" card would
turn this into a checklist, which is the objects mistake from D-112 in a new
place. A want is inferred from how somebody talks or it is not inferred, and Pim
wanting to be liked is already visible in the fact that he agrees with everything.

**One generator change, phrased to avoid the D-108 trap of asking for a minimum
and getting exactly the minimum.** A want has to be live: something tonight can
still change and another person could imaginably help with or ruin. "To not be
named tomorrow morning" is live. "To have been a better painter" is not, because
nobody can offer anything against it. And the reachability should vary, so that
working out who can be dealt with at all is itself part of the case.

**The general note.** Asked for a new mechanic, the first move should be to check
what is already in the model and not wired to anything. That is now the tenth
time, and the first time the answer was found before the feature was built rather
than after a playtest.
**Status:** active

## D-115 Every unnamed case was the same art gallery
**Date:** 2026-08-30
**"If i leave the setting empty, what happens? is it better if i give something
or not?"** The answer was worse than the question expected. `--setting` defaulted
to the literal string `"a private view at a small art gallery"`, in both entry
points, so every case where nobody typed a setting was the same evening in the
same room, forever. Not a random gallery. That gallery.

**It was the one input to a case that was never dealt.** The seed is drawn
(D-102), the shape is drawn from the seed (D-103), the manners, the motive, the
intrigues, the old business and the player's standing are all dealt (D-075), and
where on earth the house is was added yesterday (D-111). The setting sat outside
all of it with a hardcoded default, and it is the largest input of the lot: it
decides the building, the cast's jobs, what is at stake and what a victim can
threaten.

**`OCCASIONS`, eighteen of them, drawn on the seed alone** like `WHERE`, so the
number the run prints still reproduces the whole case. Each has the same job and
the deck is written to that job rather than to atmosphere: put a small group
under one roof past the point where they can leave, and put something at stake in
the morning. That stake is what a victim can threaten somebody with and what a
killer runs out of time about, so an occasion with nothing due at nine o'clock is
not an occasion, it is a location.

Paired with `WHERE` it produces a specific evening in a specific country from one
number: the eve of a wedding half the household is against, in the Aegean in the
wrong month. Neither deck knows about the other and that is fine; the model is
given both and writes the intersection.

**Naming a setting still wins**, and is still the better move when you have one
in mind, because a setting somebody actually wanted beats a card off a deck. What
changed is that the alternative is no longer a fixed gallery.

**The general note, which is the third time in three days.** A default that was
written to make a command runnable during development quietly became the
behaviour of the product. It was invisible precisely because it worked: nothing
failed, nothing warned, and the only way to notice was to ask what happens when
you leave it out. Grep the argument parsers for a hardcoded default the next time
something feels samey.
**Status:** active

## D-116 The prompt was ordered by how it reads, not by what it costs
**Date:** 2026-08-31
**Asked whether any deployment shape pays for itself, and the answer turned out
to be a question about prompt ordering.** Prompt caching is an exact-prefix cache
over tokens: the API hashes from the start of the request to a marked point and
stops at the first byte that differs. Not semantic, not partial. One byte and you
get nothing.

`render_system` built one string with fourteen substitutions in the order they
read well:

    investigator person roster table common impressions word HISTORY pressure
    conceals yielding guarded hearsay facts

`word` changes every question, `history` grows every question, `pressure`
changes every question, and they sat at positions six, seven and eight of
fourteen. Everything after them was uncacheable, which is `conceals`,
`yielding`, `guarded`, `hearsay` and `facts`: **the five biggest stable blocks
in the brief, all stranded behind three small volatile ones.** Nobody ordered it
badly; it was ordered before cost was a consideration and never revisited, which
is the same shape as the token ceiling in D-110.

**Three pieces now.** `SYSTEM_STABLE` (6,456 chars, changes only when a gate
opens), `SYSTEM_HISTORY` (append-only), `SYSTEM_LIVE` (2,058 chars, genuinely new
each question: table, word, pressure). They concatenate to exactly the old prompt
in a different order, and a test asserts that, because the reorder is about money
and must not quietly become an edit to the writing. Two deixis fixes were needed
where the table block said "below" about blocks now above it.

**The history breakpoint matters as much as the first.** A conversation is
append-only, so turn N's prefix is turn N−1's prefix plus one exchange, and a
breakpoint at the end of history means the growing part is served rather than
rewritten. This is why history moved out of the middle rather than merely later.

**The TTL is the non-obvious part and it is where the money actually is.** The
five-minute default is measured from the start of the request that writes it, and
this game has five suspects with a player who rotates: four questions to Margit,
ten minutes on Joost, back to Margit. On a five-minute lifetime Margit's prefix is
dead every single time you return, so you pay a 1.25x write instead of a 0.1x
read, and **caching costs more than not caching**. Modelled over the real
132-question session:

| | cost |
|---|---|
| no caching | $1.53 |
| 5 minute TTL, with this rotation | $1.34 |
| **1 hour TTL** | **$0.61** |
| output tokens alone, uncacheable | $0.34 |

The one-hour write is 2x and it is paid five times an evening. Measured against
the real case after the change: **$1.54 to $0.69**, against a floor of $0.34 that
no architecture removes. Anyone who had shipped the default and measured would
have concluded caching does not help this workload.

**The logging is the part that matters more than the change,** because this is a
project whose signature failure is a field that reaches the schema and never
reaches the place it needs to be, and prompt caching fails *silently*: below the
model's minimum the API ignores `cache_control` and returns no error. So
`agent.answered` now logs `cache_written`, `cache_read` and a `cached_share`
ratio, and `usd` is computed with the real multipliers rather than pretending
every input token cost list price. Both cache fields zero means it did not
happen. A test asserts the stable segment clears the 1,024-token minimum for
Sonnet 5, and another caps breakpoints at four, because a fifth is a 400.

**One interface change, made properly rather than worked around.** `Responder`
now takes the prompt as segments rather than one string. Five fakes needed one
line each. The alternative was sniffing the callable's signature, which would
have hidden the change instead of making it.
**Status:** active

## D-117 One account, one region, and a bucket shaped like the protocol
**Date:** 2026-08-31
**The AWS work started with three choices worth writing down, because next time
the question will be "why is it like this" and the answer will have evaporated.**

**One account, the old one, not a new one.** There was an existing account with
forgotten credentials. The first instinct was to abandon it and take the new
account's $100-200 of Free Tier credits, and that was wrong twice over. An
abandoned account you cannot sign into is not neutral: anything left running has
been billing a card, and a NAT gateway alone is about thirty dollars a month
doing nothing. Recovery only needs the signup email, not the password. Cost
Explorer showed zero across twelve months, so nothing was running, and a second
bucket from an old ML exercise turned up as the only trace.

Against the credits: the AWS Free Tier changed in July 2025. A new account picks
a Free Plan, gets credits, and the plan ends at **six months or when the credits
run out, whichever is first**, after which there are ninety days to upgrade or
**AWS permanently closes the account**. For infrastructure meant to keep running
and be pointed at in interviews, an account with a self-destruct timer is a
liability. The credits are not decisive either way, because the whole point of
the Lambda shape is that the infrastructure costs cents: one played case costs
more in model calls than a month of AWS.

**eu-north-1, Stockholm.** Cheapest region in Europe, largely hydro and wind. The
choice matters less than the writing down: a region is set once and a resource
created in the wrong one is invisible rather than missing, which is the single
most common early confusion. The console's region comes from the top-right
selector rather than from any form, and it has to match `aws configure get
region`.

**The bucket uses the account regional namespace.** New in March 2026, and it
reserves a slice of the S3 namespace only this account can create in, so the
name carries `-197099231733-eu-north-1-an` and cannot collide with anybody. AWS
documents it as a security best practice and states that applications need no
change, which was worth verifying rather than assuming, since a bucket name is
permanent. It also means the random suffix originally added to dodge a global
collision was redundant, so the name is plain `mystery-cases`.

Versioning on, all four public-access blocks on, ACLs disabled (bucket owner
enforced), SSE-S3 rather than KMS. KMS is the interesting one to have rejected:
it charges per request and adds a `kms:Decrypt` grant the Lambda needs, which is
a permission people routinely forget and then debug an AccessDenied that never
mentions KMS. Nothing about case JSON justifies that.

**What the shelf will look like, and why the design was already done.** `Card`'s
docstring, written months before any of this, says the hot path needs only the id
and when it was made, that both live in **the object's name**, and that a listing
should therefore be "one request and no reads at all, rather than one request and
three hundred" (D-081). That is the S3 cost model exactly, arrived at from first
principles on a filesystem.

The one thing it does not solve is that the current key is `{saved}__{id}.json`,
with the id at the end. **S3 can only list by prefix, never by suffix**, so
`load(case_id)` would have to list everything and filter. The fix is the pattern
worth learning: the key namespace *is* the index, so each prefix is shaped for
the one access pattern that uses it.

    cases/{id}.json          load(): one GET, key derived from the id
    index/{saved}__{id}      cards(): one LIST, zero GETs, sorted by name

The second is a zero-byte object whose name is the entire payload. Two writes per
save so that both reads are cheap, which is the right trade when saves happen
once a night and reads happen on every page load.
**Status:** active
