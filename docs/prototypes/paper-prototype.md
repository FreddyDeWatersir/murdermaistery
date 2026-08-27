# Paper prototype kit

Goal: find out whether interrogating a cast of suspects is actually fun, and
discover what the ground truth schema needs to contain, before writing any code.

Budget: one evening. Do not polish anything.

The order below is deliberately the order the generator will run in later.
Notice where you have to improvise, because every improvisation is a missing
field in the schema.

---

## Scenario seed

Use this unless you have a better idea. Do not spend the evening inventing a
setting.

**A private view at a small art gallery.** Rooms give natural movement, and
money, forgery and reputation give natural secrets.

- Rooms: Main Hall, Back Office, Storeroom, Courtyard, Cloakroom
- Cast: 5 suspects plus 1 victim
- Time: five slots of 20 minutes, 20:00 to 21:40
- The murder happens in slot 3 or 4, never slot 1 or 5

Five suspects and five slots is 25 cells. That is the most you can hold in your
head by hand, and it is already enough to be non-trivial.

---

## Step 1. Cast

For each of the 6 people (including the victim), write one line:

| Name | Role at the event | What they want | What they are hiding |
|---|---|---|---|
| | | | |
| | | | |
| | | | |
| | | | |
| | | | |
| | | | |

Rule: **every suspect hides something, and only one of those things is the
murder.** If four suspects have nothing to conceal, interrogation becomes four
cooperative witnesses and one obvious liar, and the game is dead. This is the
single most important line in the whole design.

---

## Step 2. The murder

- Killer:
- Victim:
- Room:
- Slot:
- Method:
- Motive: (must come from the "what they are hiding" column above)

---

## Step 3. The movement grid

This is the ground truth. Everything else is derived from it.

| | 20:00 | 20:20 | 20:40 | 21:00 | 21:20 |
|---|---|---|---|---|---|
| Suspect A | | | | | |
| Suspect B | | | | | |
| Suspect C | | | | | |
| Suspect D | | | | | |
| Suspect E | | | | | |
| Victim | | | | | |

Fill every cell with a room. The killer and victim must share a room in the
murder slot, and nobody else may be in that room in that slot.

Sanity check as you fill it: people cannot teleport, and if two people are
alone together in a slot they will each be the other's alibi, so use that
deliberately.

---

## Step 4. Derive what each person knows

This step is purely mechanical. Do it by rule, not by taste, because the
generator will have to do it by rule.

1. **Co-location.** For each slot, for each room, everyone in that room knows
   "X was in this room at this time" about everyone else there.
2. **Secrets.** Give two or three people one piece of knowledge unrelated to
   location, for example "the victim was being blackmailed" or "the gallery
   owner's insurance was renewed last week".
3. **Physical traces.** One or two objects that place someone somewhere. A
   dropped glove, a wine glass in the wrong room.
4. **The killer knows everything they did**, and must construct a false story.

---

## Step 5. The killer's alibi, and the solvability check

This is the part the validator will later enforce, so do it carefully by hand
once.

- The killer claims to have been in room **R'** during the murder slot.
- List every character whose knowledge contradicts that claim: anyone who was
  in R' then and did not see them, or who saw the killer somewhere else.

Two requirements:

- **At least two independent contradictors.** One is not enough or the game is
  a single lucky question.
- **No single contradictor is conclusive.** Each one alone must be explainable
  away.

Ways to make a clue non-conclusive, which is the actual craft here:

- The witness has their own secret, so they are plausibly lying
- The room was crowded, so "I did not see them" is weak
- The sighting is at a slot boundary, so the timing is arguable
- The witness only saw someone's back, or heard a voice

Write down which technique you used for each clue. The generator will need to
encode these as clue attributes, and this list is where that vocabulary comes
from.

---

## Step 6. Write the cards

One card per suspect, containing only:

- Who they are, what they want
- What they are hiding, and how hard they will fight to hide it
- Their own movements, slot by slot
- What they observed about others
- Any secret knowledge
- For the killer only: the false story, and what they will say if pressed

Do not write personality notes beyond a sentence. You are testing structure,
not prose.

---

## Step 7. Play it

You role-play all five suspects. Someone else interrogates. **Answer only from
the cards.** The moment you improvise, stop and put a mark on the capture sheet,
because you have just found a missing schema field.

If you have nobody to play with tonight, I can be the detective. You keep the
ground truth entirely to yourself and only answer in character, and I will ask
questions and try to solve it. That works fine in this chat and costs nothing.

---

## Capture sheet

Fill this in during and immediately after play. This is the actual output of
the evening, more than the mystery itself.

**Every question asked, verbatim:**

(list them. The vocabulary players naturally use is what the agent prompt has
to handle)

**Improvisations, where the cards did not cover the answer:**

(each one is a missing field)

**Contradictions the player found, and how:**

**Contradictions the player missed:**

**Time to solution, or point of giving up:**

**Where it got boring, and what they were doing at that moment:**

**Did the accusation feel earned or lucky?**

---

## What comes next

The schema is written from the capture sheet, not from imagination. The grid in
step 3 becomes the timeline type, the derivation rules in step 4 become the
knowledge generator, and the two requirements in step 5 become the first two
validator rules, with their failing tests written first.
