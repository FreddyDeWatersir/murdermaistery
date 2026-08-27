# Playtest findings: prototype 02, Opening Night

Date: 26 August 2026
Format: text interrogation over chat. Claude played five suspects from written
cards. Federico played the detective, blind.
Result: **solved correctly in 28 questions across 8 rounds.**
Verdict: **fun.**

---

## 1. The headline

The core risk of this project was never technical. It was that a structured,
constraint-satisfying mystery would be *correct* and *boring*. That risk is
substantially retired. The game was enjoyable to play, the misdirection worked,
the solution felt earned rather than arbitrary, and the endgame had a real
moment in it.

Specifically, the thing I was least confident about held up. The rule that no
single clue may be individually conclusive did **not** read as the game
withholding. It read as suspects having their own reasons, which is the same
mechanical fact wearing a better costume. That rule stays.

## 2. The asterisk, and it is a large one

This playtest was contaminated in three ways, all of them mine.

1. **The notebook did detective work.** The decisive break of the case, Renske's
   false green room alibi colliding with Tomas's truthful one, was found in two
   questions because my notebook placed both claims in adjacent rows of a table.
   Eleven messages apart in prose, that catch is much harder and possibly does
   not happen.
2. **The italic commentary flagged significance.** Every round I stepped outside
   the fiction to point at what had just mattered. That is pacing assistance a
   real player does not get.
3. **I nudged.** At least twice I said something close to "you have enough to
   accuse."

So the honest statement is: *the game is fun when played with a competent
co-narrator flagging salience.* The next playtest must be blind. Claim log only,
no editorial, no out of fiction notes, no nudges. If it is still fun under those
conditions, the finding is real.

---

## 3. Findings

### F1. The creative layer is easy, the combinatorial layer is hard
Federico built a six person cast with interlocking motives in about ten minutes
and then could not construct the movement grid at all. That split is exactly the
split between what LLMs do well and badly.

**Design consequence:** three stage generation. LLM invents cast, wants, secrets,
and the murder. A deterministic solver lays out the grid against the solvability
constraints. LLM writes surface phrasing. See D-008.

### F2. Clues form a dependency graph, not a flat set
In both prototypes the killer was unreachable until an unrelated-looking secret
was cracked first. In prototype 01, Lelia's motive did not exist until the player
had found the affair. In prototype 02, Wouter's alibi could not be broken until
Renske was cracked, and Renske would not crack without the money.

**Design consequence:** clues carry prerequisites. The validator must check that
a path to the solution exists through the gates, and that no gate is a single
point of failure. See D-009.

### F3. A room is not an atom
Four separate times the grid was too coarse to answer a natural question.

- Nadia was "in the dressing corridor" but actually behind her own door for half
  of it, which is a completely different observational position
- Ilse was "in the dressing corridor" at the top end, able to see the wings
  crossing
- Renske was "in the lighting box" which turned out to need an annexe behind it
  where the files live
- Wouter was "in the prop store" for a slot in which he also walked to a van in
  the loading bay and back

**Design consequence:** location needs at least two levels, a place and a
position within it, and the derivation rule needs to know that being in a
corridor and being behind a door off it produce different observations. Four
independent occurrences in one evening is a requirement, not a detail.

### F4. Private knowledge is three-state, not two
Nadia let slip that she knew Ilse was being recast, something Ilse believed
nobody knew. That is a character revealing something she *does* know and would
rather not have said. It looks identical in a transcript to an agent leaking
something it should never have known, and it is the opposite thing.

**Design consequence:** the knowledge model needs at minimum: *does not know*,
*knows and will say*, *knows and will conceal*. Concealment needs a break
condition, and the break conditions observed were not uniform. Ilse's held four
rounds and broke under a direct, named, empathetic press. Nadia's broke sideways
under an emotional question she was not braced for.

This is the answer to the open question "how is private knowledge represented and
enforced at the agent boundary," and it came from play rather than from design.

### F5. Refusal must be a first class behaviour
Twice I invented ground truth mid-game because the player reached past what was
written: what was in the van, and why Bram went cold on Nadia two weeks earlier.
The second one knitted together the money, the cancelled meetings, the abandoned
promise and the audit timing so neatly that it felt like it had always been
there. It had not. I made it up in ninety seconds, with the entire ground truth
in front of me and a deliberate intention not to do that.

An agent with only its own card, no global view, and no incentive to be careful
will do this constantly and confidently, and will eventually hand the player a
fact that dissolves the case.

**Design consequence, and this is the most important engineering finding of the
evening:** ground truth must be complete with respect to every question the
player can reach. Where it is not, the agent must detect that it is off the map
and decline, rather than improvise. Refusal is a feature to be tested, not a
failure mode. This is directly testable in pytest and should be among the first
agent tests written.

### F6. Agents need wants, not just knowledge
Renske asked *me* a question, then opened a negotiation, then volunteered the
decisive evidence unprompted once she had a reason to want the case closed. None
of that was designed. It emerged from a card whose secret was in tension with its
self interest.

Every version of this project discussed so far models an agent as a knowledge
store that answers queries. The most alive moments came from a suspect who wanted
something the player had.

**Design consequence:** an agent needs a goal and a stake, not only a knowledge
set. Cheap to add, enormous effect.

### F7. Player stance changes what suspects give up
Ilse held her sighting for five rounds and released it when Federico named her
stakes accurately and framed the pressure as help. That is not an information
move, it is a social one.

**Design consequence:** if stance does not matter, the game is a search interface
with roleplay on top. This is probably the single largest difference between
"interrogation game" and "database query." Needs a model, even a crude one.

### F8. Bluffing exposes a hole in the private knowledge principle
Federico asserted to Wouter that none of his movements could be corroborated.
That was false: Wouter spent both acts in the prompt corner with cast crossing
past him all night. Wouter did not challenge it, because I was playing him from a
card that contained no view of the rest of the case.

**Design consequence:** if agents know only their own private knowledge, the
player can assert anything about the state of the investigation and it always
lands. Agents need read access to a shared public record, meaning what has been
established in front of them, what they have personally claimed, and what is
common knowledge in the fiction. This cuts against the original "each agent knows
only its own knowledge" principle and needs resolving carefully, because the
naive fix reintroduces exactly the leakage the principle exists to prevent.

### F9. The world is ground truth too
Federico stopped asking questions and went to look in the van. Nothing in the
design has any provision for this. Every version discussed is a chat window with
suspects in it.

**Design consequence:** inspectable objects, rooms, and documents need pinned
content in the ground truth, or the model will invent whatever seems dramatically
appropriate at the moment of inspection, which is the fastest available way to
break a mystery. This is F5 again in a different costume, and the fact that it
showed up twice by different routes means it is structural.

Also worth noting: the van corroborated the theft exactly as Wouter intended, and
made him more credible. Physical verification is not neutral. It can be weaponised
by a suspect who tells the truth about the wrong crime.

### F10. False premises need explicit handling
Twice the player embedded a false fact in a question. "When did you visit the prop
store" to a man who never went there, and "the money Tomas was sending" when Tomas
was sending none. Both times I had to decide on the spot how a suspect handles an
assumption baked into a question.

Three possible behaviours: silently accept and build on it, correct it, or refuse
to engage. Only one is right, and it varies by character and by stake. Renske
corrected hard because correcting served her. A suspect with no stake in the
player's accuracy would have let it stand.

**Design consequence:** a deliberate test category. Feed agents questions with
false premises and assert they neither adopt nor ignore them.

### F11. The notebook is the mechanic
Discussed above as a contamination source, but the design conclusion is separate
and important. The clue notebook is not a convenience feature for the frontend.
It is where deduction actually happens, because contradiction detection is a
memory problem before it is a reasoning problem.

**Open tension:** the project's contradiction tracker is specified to flag self
contradictions and cross character contradictions automatically. If the software
finds every contradiction for the player, the player has nothing left to do. That
is the difference between a notebook and a solver, and it is a game design
decision rather than an engineering one. Unresolved.

### F12. The killer's disposition is a design parameter
Prototype 01's killer denied everything. Prototype 02's killer confessed to a
lesser true crime as a shield, and it worked: it explained his evasion, his keys,
his proximity, and his lie, and it cost roughly five questions and two rounds of
misdirection. It also destroyed him, because he could not admit the theft and then
survive proof that the victim knew about it.

The two cases felt genuinely different to play, and the difference was structural
rather than cosmetic. This is the strongest available evidence about variety, see
section 4.

### F13. Hand built ground truth contained a contradiction, and only play found it
Prototype 02's grid placed Tomas at the stage door at 20:40 while the confrontation
notes placed him in the green room being sacked at 20:40. I did not notice while
writing it. I noticed while answering a question about it, and papered over it in
character.

This is the case for the validator, made by the validator's absence. A careful
author with the whole thing in front of him produced an internally inconsistent
timeline and did not catch it by reading. It was caught by interrogation, which is
to say by an adversarial process, which is to say by a test.

---

## 4. Variety: the open question

Federico's concern is whether generated mysteries will all feel the same. It is
the right thing to worry about, because sameness is what kills a daily game.

**What we know so far:** prototypes 01 and 02 felt clearly different, and the
difference was not the setting. It was the *shape of the solution* and the
*killer's disposition*. Gallery versus theatre is cosmetic. Denier versus shielder
is structural.

**Hypothesis to test tomorrow:** variety must be generated structurally, not
cosmetically. The LLM will happily produce infinite settings and character names
and will produce them well. That is the cheap axis. The expensive axis, and the
one that actually determines whether the fourth game feels like the first, is a
library of solution topologies from which the solver draws.

Candidate axes, roughly in order of how much they change the felt experience:

1. **Solution topology.** The alibi lie is one shape and we have now used it
   twice. Others: the wrong time of death, the misidentified victim, the
   accomplice, the killer who never lies at all and simply omits, the framing,
   the impossible room, the killer who is the one pushing hardest for a solution
2. **Killer disposition.** Denier, shielder, over-cooperator, framer, early
   confessor to a lesser thing, the one who volunteers the decisive clue against
   someone else
3. **Concealment taxonomy.** Both prototypes leaned heavily on sex and money.
   Shame, loyalty, fear, professional pride, protecting someone else, and simple
   embarrassment are all unused and all produce different interrogation textures
4. **Cast size and room topology.** Cheap parameters, moderate effect
5. **Setting and period.** Cheapest, and the axis the LLM is best at, and
   therefore the one to rely on least for actual variety

**Practical consequence:** the generator's first decision should be a draw from
the topology library, and everything else, including the cast, should be
generated *to fit that shape*. Cast first, shape second is the wrong order and
is how you get four different casts playing the same game.

---

## 5. Known gap: visualisation

Federico's note: the whole game ran as prose and there was no way to see the
state of it. Five suspects, five time slots, six rooms, and a growing pile of
claims is a spatial problem being handled in a linear medium.

Obvious candidates for the frontend, in rough order of value:

- The claim grid, suspects by time slot, filled in as claims are made, with
  contested cells marked
- A room map with movement traces the player can overlay per suspect
- The notebook as a first class panel rather than a chat transcript
- Visual marking of what is claim versus what is corroborated versus what is
  proven

This is a stage 3 conversation and should not be built before the notebook versus
solver question in F11 is decided, because that decision determines what the
interface is *for*.

---

## 6. Where this leaves the project

The core risk is provisionally retired, subject to a blind replay. Seven schema
and validator requirements now exist that were not in the original handoff, and
all seven came from one evening of paper and chat rather than from design
discussion. That is the argument for having done it this way, and it is worth
remembering the next time a schema-first instinct shows up.

**Next actions, in order:**

1. Blind replay of a third prototype, no notebook editorial, no out of fiction
   commentary, to check that the fun survives the removal of the co-narrator
2. Resolve F11, notebook versus solver, because it gates the interface
3. Design the ground truth schema, now with F2, F3, F4, F9 as hard requirements
4. Write the validator's bad-mystery fixture corpus, starting with the failure in
   F13 as the first test case
