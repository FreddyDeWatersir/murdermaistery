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
