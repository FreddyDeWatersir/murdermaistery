# Prototype 01: The Private View

Ground truth pack. Cast by Federico, grid and derivation worked out as a
demonstration of the algorithm the solver will implement.

Setting: a private view at a small Amsterdam gallery.
Rooms: Main Hall, Back Office, Storeroom, Courtyard, Cloakroom.
Time: five slots of twenty minutes, 20:00 to 21:20.

---

## 1. Cast

| Name | Role | Wants | Hiding |
|---|---|---|---|
| **Roos** | The artist, the star of the show | To sell well and be taken seriously | Stole her breakthrough ideas from a teenage artist abroad. Also sleeping with Gustav |
| **Gustav** | Rich collector, married to Lelia | To buy a Roos painting as a private memento of the affair | The affair with Roos |
| **Lelia** | Gustav's wife | To be seen as untouchable. Reputation above everything | Knows Gustav strays, tolerates it while it stays quiet. **She is the killer** |
| **Mihail** | Art critic and journalist. **The victim** | A story | Was already digging into Roos's plagiarism before tonight |
| **Alex** | Gallery owner, recently divorced | The show to succeed | How financially desperate he is. The gallery does not survive a bad night |
| **Marth** | Aspiring artist | To be the next Roos | Sleeping with Alex to get a slot in the next show |

Every one of the five suspects is concealing something. Only one of those
things is the murder. That is the property that makes interrogation
non-trivial, and it is the hardest rule for the validator to formalise.

---

## 2. The murder

- **Killer:** Lelia
- **Victim:** Mihail
- **Room:** Storeroom
- **Slot:** 21:00
- **Method:** Struck with a marble maquette from a crate, unplanned
- **Motive:** Mihail, having worked out that Gustav is sleeping with Roos, takes
  Lelia aside to tell her. He wants her reaction for the story. Lelia can live
  with a husband who strays. She cannot live with it printed. She kills him in
  the moment.

Note the shape: **the motive does not exist until 21:00.** This is an
unpremeditated murder, which is why Lelia has no prepared alibi and why her
cover story is improvised and therefore breakable.

---

## 3. Movement grid

This is the ground truth. Everything below is derived from it mechanically.

| | 20:00 | 20:20 | 20:40 | 21:00 | 21:20 |
|---|---|---|---|---|---|
| **Roos** | Main Hall | Storeroom | Cloakroom | Courtyard | Courtyard |
| **Gustav** | Main Hall | Storeroom | Main Hall | Cloakroom | Main Hall |
| **Lelia** | Main Hall | Main Hall | Main Hall | **Storeroom** | Main Hall |
| **Mihail** | Main Hall | Courtyard | Storeroom | **Storeroom** | dead |
| **Alex** | Back Office | Courtyard | Main Hall | Main Hall | Main Hall |
| **Marth** | Main Hall | Main Hall | Cloakroom | Courtyard | Main Hall |

Constraint satisfied: at 21:00 the Storeroom contains the killer and the victim
and nobody else.

What happens in each slot:

- **20:00** Opening remarks. Alex is alone in the Back Office on a call with his
  bank, which is why he has no alibi for the first slot and does not want to
  explain it.
- **20:20** Roos and Gustav slip into the Storeroom. Mihail takes Alex out to
  the Courtyard and asks pointed questions about where Roos's early work came
  from.
- **20:40** Roos repairs herself in the Cloakroom with Marth present. Mihail
  goes to the Storeroom and finds two glasses and Roos's scarf, and at the slot
  boundary he sees Gustav leaving it. He now has the affair.
- **21:00** At the boundary Mihail crosses the Main Hall, speaks to Lelia, and
  the two leave together. In the Storeroom he tells her. She kills him.
- **21:20** Lelia returns to the Main Hall composed. The body is found after
  21:40.

---

## 4. Derived knowledge

Co-location, applied mechanically. Everyone in a room in a slot knows that
everyone else in that room was there then.

| Slot | Room | Present |
|---|---|---|
| 20:00 | Main Hall | Roos, Gustav, Lelia, Mihail, Marth |
| 20:00 | Back Office | Alex, alone |
| 20:20 | Storeroom | Roos, Gustav |
| 20:20 | Main Hall | Lelia, Marth |
| 20:20 | Courtyard | Mihail, Alex |
| 20:40 | Main Hall | Gustav, Lelia, Alex |
| 20:40 | Cloakroom | Roos, Marth |
| 20:40 | Storeroom | Mihail, alone |
| 21:00 | Storeroom | Lelia, Mihail |
| 21:00 | Main Hall | Alex, alone |
| 21:00 | Cloakroom | Gustav, alone |
| 21:00 | Courtyard | Roos, Marth |
| 21:20 | Main Hall | Lelia, Alex, Gustav, Marth |
| 21:20 | Courtyard | Roos, alone |

**Boundary observations** (deliberately fuzzy, and a clue type the schema needs):

- Mihail sees Gustav leaving the Storeroom at the 20:20 to 20:40 boundary.
- Alex sees Lelia and Mihail leave the Main Hall together at the 20:40 to 21:00
  boundary.
- Gustav sees Mihail approach Lelia, but leaves for the Cloakroom before they go.

**Secret knowledge**, independent of location:

- Alex knows Mihail was asking about the provenance of Roos's early work.
- Marth knows Roos came into the Cloakroom at 20:40 flushed and rearranging her
  dress.
- Gustav knows Lelia is aware he strays.

**Physical trace:**

- Mihail's notebook is missing from the body. Lelia took it because it names
  Gustav. The player will read it as pointing at Roos, whose plagiarism was in
  it too. This is the strongest red herring in the case.

---

## 5. Solvability check

**Lelia's claim:** she stepped out to the Courtyard alone from about nine and
came back in a little after.

**Contradictors, and why each is individually deniable:**

| # | Who | What they can say | Why it is not conclusive alone |
|---|---|---|---|
| 1 | Alex | Saw Lelia leave the Main Hall with Mihail around nine | He pegs the time as "around nine, maybe just before", so it sits on a slot boundary. He is also evasive, because talking to anyone official means scrutiny of his finances |
| 2 | Roos | Was in the Courtyard at 21:00 and did not see Lelia | Absence of sighting, not presence elsewhere. She was at the far end, distracted, and she is lying about everything else |
| 3 | Marth | Same non-sighting, plus Lelia re-entered the Main Hall from the corridor side rather than the courtyard door | She admits she was not paying attention, and she is concealing the Alex arrangement |

Three independent contradictors. None sufficient alone. Combined, Lelia left
with the victim, was not where she says she was, and came back the wrong way.

**Why it is not obvious:** Gustav has no alibi at all for 21:00, alone in the
Cloakroom, and he is visibly lying about 20:20. He is the natural suspect and
the player will spend most of the game on him. Roos is lying too, and about
two separate things. Four of five suspects lie under questioning.

**The dependency chain, which is the structural discovery here:**

```
crack Roos or Gustav on the affair
        |
        v
understand why Mihail sought out Lelia specifically
        |
        v
Lelia has a motive that did not exist an hour earlier
        |
        v
her alibi is worth attacking
```

Lelia is not even a suspect until step two. A player who never cracks the
affair cannot solve the case, no matter how many questions they ask her. Clues
are gated behind other clues, and the schema has to represent that.

---

## 6. Cards

Read only your own card when answering as that character.

### ROOS
You are the artist. Tonight decides your career.
**Movements:** Main Hall until 20:20. Storeroom with Gustav 20:20 to 20:40.
Cloakroom 20:40 to 21:00, Marth was there. Courtyard from 21:00, with Marth
until 21:20, then alone.
**You saw:** nothing unusual. You did not see Lelia in the Courtyard at any
point after nine.
**You are hiding:** the affair with Gustav, and that your breakthrough series
came from a teenager whose work you saw abroad and never credited. Mihail had
been circling the second one for weeks.
**Under pressure:** you will claim you were in the Cloakroom from 20:20. You
will get defensive fast about the work, faster than about the affair.

### GUSTAV
You are wealthy, married to Lelia, and in love with Roos.
**Movements:** Main Hall until 20:20. Storeroom with Roos 20:20 to 20:40. Main
Hall 20:40 to 21:00. Cloakroom alone 21:00 to 21:20. Main Hall after.
**You saw:** Mihail come up to Lelia and say something quietly, just before
nine. You left before they did.
**You are hiding:** the affair. You wanted to buy a painting to keep.
**You know:** Lelia is aware you stray. You believe she does not mind much.
**Under pressure:** you have no alibi for nine and you know how that looks. You
will lie about 20:20 and stick to it, because admitting the affair in front of
your wife is worse to you than being suspected.

### LELIA
You killed Mihail. It was not planned.
**Movements:** Main Hall until 21:00. Storeroom 21:00 to 21:20 with Mihail.
Main Hall after.
**What happened:** Mihail asked to speak privately and told you Gustav is
sleeping with Roos, and that he intended to write about the gallery and the
people in it. You have tolerated years of this on the condition that nobody
ever knows. You hit him with a marble piece from an open crate. You took his
notebook and it is now in your bag.
**Your story:** you stepped out to the Courtyard alone for air from about nine
and came back in a little after.
**Under pressure:** you are calm and slightly bored. You do not volunteer. You
express mild distaste for Roos if asked, which is new, and you should not
explain why. If confronted with the Courtyard, you suggest they simply did not
notice you.

### ALEX
You own the gallery. The divorce took most of what you had and this show is
the difference between continuing and not.
**Movements:** Back Office alone until 20:20, on the phone to your bank.
Courtyard with Mihail 20:20 to 20:40. Main Hall from 20:40 onward.
**You saw:** Lelia and Mihail leave the Main Hall together around nine, maybe
just before. You were not really watching.
**You know:** Mihail spent the Courtyard conversation asking where Roos's early
work came from, which alarmed you, because you cannot afford a scandal.
**You are hiding:** the finances, and the arrangement with Marth.
**Under pressure:** you are helpful in manner and unhelpful in substance. You
will not volunteer the sighting of Lelia unless asked something close to it,
because you want this conversation over.

### MARTH
You are an aspiring artist. You intend to be in the next show.
**Movements:** Main Hall until 20:40. Cloakroom with Roos 20:40 to 21:00.
Courtyard with Roos 21:00 to 21:20. Main Hall after.
**You saw:** Roos came into the Cloakroom at 20:40 flushed and fixing her
dress. You were in the Courtyard at nine and Lelia was not there. When you
came back in at 21:20 Lelia came into the Main Hall from the corridor side,
not the courtyard door, though you were not paying close attention.
**You are hiding:** you are sleeping with Alex to secure a slot.
**Under pressure:** you notice everything and you offer very little, because
every question about where you were leads back to Alex.

### MIHAIL (the victim, for reference)
Art critic. Had been investigating the provenance of Roos's early work for
weeks. Tonight he found two glasses and a scarf in the Storeroom and saw
Gustav leaving it, and understood the affair. He went to Lelia for a reaction.
His notebook contained both stories.

---

## 7. What to capture while playing

- Every question asked, verbatim
- Every time a card did not cover the answer and you improvised
- Whether the player chased Gustav, and for how long
- Whether the player ever cracked the affair, and what question did it
- Whether they reached Lelia at all
- Where it dragged
