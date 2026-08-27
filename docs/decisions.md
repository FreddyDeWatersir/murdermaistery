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
