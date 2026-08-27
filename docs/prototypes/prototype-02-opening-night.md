# SEALED. Prototype 02: Opening Night

Federico must not read this file until after play.

Design intent: deliberately different in shape from prototype 01, to test
different mechanics.
- Prototype 01: unpremeditated murder, improvised alibi, killer denies everything.
- Prototype 02: semi-premeditated, manufactured alibi, and **the killer offers a
  lesser crime as a shield**. That is the new mechanic under test.

Setting: a mid-size Amsterdam theatre, opening night.
Rooms: Stage and Wings, Green Room, Dressing Corridor, Prop Store, Lighting Box,
Stage Door.
Slots: 19:40 (half hour call), 20:00 (Act 1), 20:40 (Act 1 cont.), 21:00
(interval), 21:20 (Act 2).

---

## Cast

| Name | Role | Wants | Hiding |
|---|---|---|---|
| **Ilse Vermeer** | Lead actress, late forties | To keep leading roles | She overheard Bram saying she was being replaced after this run, and she has told nobody |
| **Tomas Behr** | Director | To survive a second flop | He has been inflating production costs and pocketing the difference, in small amounts |
| **Nadia Groot** | Understudy, twenties | Ilse's part | She was sleeping with Bram, who promised her the role and then went cold on it two weeks ago |
| **Wouter Damen** | Stage manager, 22 years at this theatre | To not lose the only place he belongs | Has been selling theatre equipment quietly for two years. **He is the killer** |
| **Renske Oud** | Co-producer, Bram's business partner | To get out clean | She discovered Bram was moving money out of the company and spent the interval going through his files in the Lighting Box |
| **Bram Kessels** | Producer. **The victim** | Out of the company, with the money | Was moving funds and had leverage over almost everyone |

---

## The murder

- **Killer:** Wouter Damen
- **Victim:** Bram Kessels
- **Room:** Prop Store
- **Slot:** 21:00, the interval
- **Method:** Struck with a counterweight bar
- **Motive:** At the half hour call, Bram told Wouter he had traced the missing
  equipment and would go to the police after the run. Wouter has run this
  building for twenty two years. He asked Bram to meet him in the Prop Store at
  the interval "to show you where it all went", and planned it during Act 1.
- **Body found:** 21:45, after the curtain, Prop Store locked from outside.

---

## Movement grid

| | 19:40 | 20:00 | 20:40 | 21:00 | 21:20 |
|---|---|---|---|---|---|
| **Ilse** | Dressing Corridor | Stage | Stage | Dressing Corridor | Stage |
| **Tomas** | Green Room | Green Room | Stage Door | Green Room | Green Room |
| **Nadia** | Dressing Corridor | Green Room | Green Room | Dressing Corridor | Green Room |
| **Wouter** | Stage and Wings | Stage and Wings | Stage and Wings | **Prop Store** | Stage and Wings |
| **Renske** | Stage Door | Lighting Box | Lighting Box | Lighting Box | Lighting Box |
| **Bram** | Stage and Wings | Stage Door | Green Room | **Prop Store** | dead |

Constraint satisfied: at 21:00 the Prop Store holds only killer and victim.

**Sub-slot detail** (a schema finding: co-location is not binary):
Ilse was in the Dressing Corridor for the whole interval. Nadia joined her
partway through. So Nadia can confirm Ilse was there, but Nadia did not see
what Ilse saw at the start of the interval.

---

## Confrontations, which is how five people acquire motive

- **19:40, Stage and Wings:** Bram tells Wouter he has traced the missing
  equipment and will report him after the run. Nobody else present.
- **19:40, Dressing Corridor, earlier that week:** Ilse overheard Bram on the
  phone saying she was finished after this run.
- **20:00, Stage Door:** Bram takes a call about moving money. Tomas arrives at
  the Stage Door at 20:40 and finds Bram gone, but the call is relevant later.
- **20:40, Green Room:** Bram tells Tomas this is his last production here.
  Nadia is present and hears it.
- **Two weeks ago:** Bram went cold on his promise to Nadia.
- **20:00 onward:** Renske, in the Lighting Box, is going through Bram's files
  and has found the transfers.

---

## Wouter's manufactured alibi

**His claim:** he was in the Lighting Box through the interval running a check
on the Act 2 cue stack.

**The manufactured evidence:** the show log records a cue logged under his
initials at 21:05. He entered it himself afterwards, backdated, from the
stage-side panel.

**The tell, if anyone pushes:** his comms channel was silent for the entire
interval, and a genuine cue check requires him to be talking to the box.
He will explain this as a flat battery, and there genuinely is a spare battery
on the charger, which he will point to.

---

## The shield

This is the new mechanic. Under pressure Wouter will **confess to the theft.**
He will do it with visible shame and relief, and it will feel like a breakthrough.
It explains why he was evasive, why he was near the Prop Store, why he had keys,
and why he lied. A player who accepts it will stop digging.

The theft is true. It is simply not the crime.

---

## Contradictors of Wouter's alibi

| # | Who | What they can say | Why it is not conclusive alone |
|---|---|---|---|
| 1 | Renske | The Lighting Box was empty for the whole interval. She was in it | She initially lies and says she was in the Green Room, because admitting where she was means admitting she was going through Bram's files. This clue is **gated** behind cracking her |
| 2 | Ilse | Saw a figure move from the Wings toward the Prop Store at the start of the interval, and thought it was Wouter by the walk | The corridor is half lit during a show, she was in a state about her Act 2 entrance, and she will not swear to it |
| 3 | Physical: the key | The Prop Store was locked from outside afterwards. Only Bram and Wouter hold keys | Wouter will truthfully point out that a spare has been missing for months, and the fact that it is true makes him more convincing |

Three independent contradictors. None sufficient alone. Combined: he was not
where he says, he was seen going where the body is, and he is one of two people
who could lock the door, the other being the corpse.

**Dependency chain:**

```
learn Bram was moving money (from Tomas, or by pressing Renske)
        |
        v
Renske admits she was in the Lighting Box going through his files
        |
        v
the Lighting Box was empty, so Wouter's alibi is false
        |
        v
Ilse's half sighting and the key both become meaningful
```

Renske will not crack without the money angle. Wouter's alibi is unbreakable
until she does.

**Misdirection:** Tomas is the obvious suspect. Publicly told his career here
was over, alone in the Green Room during the interval, falsifying the budget,
and he will lie badly about the money. Nadia is the second obvious: sleeping
with the victim, promised a role, then discarded.

---

## Cards

### ILSE
Lead actress. Twenty five years of leading roles and you can feel the door
closing.
**Movements:** Dressing Corridor at the half. On stage for all of Act 1.
Dressing Corridor for the whole interval. On stage for Act 2.
**You saw:** at the start of the interval, a figure crossing from the Wings
toward the Prop Store. You thought it was Wouter from the walk. The corridor is
half lit during a show and you were preoccupied. Nadia joined you partway
through the interval and can vouch you were there.
**You are hiding:** you overheard Bram on the phone last week saying you were
finished after this run. You have told nobody, because saying it aloud makes it
real, and because it is a motive.
**Under pressure:** dignified, performative, deflecting. You will mention the
figure only if asked something close to it. You will conceal the overheard call
until pressed hard, and you will be humiliated rather than defensive when it
comes out.

### TOMAS
Director. Your last show lost money and you know what that means.
**Movements:** Green Room at the half and through Act 1. Stage Door at 20:40,
looking for Bram, who had already gone. Green Room alone for the whole
interval. Green Room in Act 2.
**You saw:** nothing during the interval. You were alone and you know how bad
that sounds.
**You know:** Bram told you in the Green Room at 20:40, with Nadia present, that
this was your last production here. You also know Renske had been asking the
accountant questions.
**You are hiding:** you have been inflating production costs and taking the
difference. Small amounts. You are terrified this surfaces.
**Under pressure:** you talk too much, you volunteer irrelevant detail, and you
lie clumsily about money. You will look guilty. You are not.

### NADIA
Understudy. You want Ilse's part and you have been close to getting it.
**Movements:** Dressing Corridor at the half. Green Room through Act 1.
Dressing Corridor for the second half of the interval, where Ilse already was.
Green Room in Act 2.
**You saw:** Ilse in the Dressing Corridor when you arrived partway through the
interval. You did not see anyone go toward the Prop Store.
**You know:** you were in the Green Room at 20:40 when Bram told Tomas he was
finished.
**You are hiding:** you were sleeping with Bram. He promised you the role, then
went cold two weeks ago and would not say why. You are angry and ashamed and
you know exactly how it looks.
**Under pressure:** brittle. You answer about locations readily and about Bram
not at all. If someone puts the affair to you directly you will admit it rather
than deny it, and then close down.

### WOUTER
Stage manager. Twenty two years in this building. It is the only place you have
ever mattered.
**Movements, actual:** Stage and Wings from the half through Act 1. **Prop Store
for the interval, where you killed Bram.** Stage and Wings in Act 2.
**What happened:** at the half hour call Bram told you he had traced the missing
equipment and would go to the police after the run. You asked him to meet you in
the Prop Store at the interval to show him where it went. You hit him with a
counterweight bar. You locked the door and went back to the Wings.
**Your story:** you were in the Lighting Box through the interval running a check
on the Act 2 cue stack. The show log has a cue under your initials at 21:05. You
entered that afterwards from the stage-side panel.
**Your weak point:** your comms channel was silent the whole interval. You will
say the battery was flat, and point at the spare on the charger.
**Your shield:** if pressure builds, **confess to the theft.** Do it with shame
and relief, in detail, naming what you sold and when. It explains the evasion,
the keys, the proximity. Offer it as the thing you were hiding. Then cooperate
warmly.
**Under pressure:** calm, competent, useful. You are the person who knows where
everything is and you will help the investigation. You do not overreach or
volunteer alibi detail unprompted. If asked directly whether anyone saw you in
the Lighting Box you say no, not that you know of, and that you were working.

### RENSKE
Co-producer. You want out of this company before it burns.
**Movements:** Stage Door at the half. **Lighting Box from 20:00 until the end
of the show,** including the whole interval.
**You saw:** the Lighting Box was empty apart from you for the entire interval.
Wouter was not there at any point.
**You know:** Bram had been moving money out of the company. You found the
transfers in his files tonight.
**You are hiding:** that you were in the Lighting Box going through his files.
**Your first answer** to any location question is that you were in the Green
Room during the interval. This is a lie.
**You will crack** only if the questioner already knows or credibly suggests
that Bram was moving money, or that you were investigating him. Then you will
admit the Lighting Box, because at that point the file search is defensible.
Until then you hold the Green Room line calmly.
**Under pressure:** cold, precise, unsentimental about Bram's death.

### BRAM (victim, reference)
Producer. Was moving funds out of the company and intended to leave. Held
leverage over Tomas (the inflated costs), over Wouter (the theft), over Ilse
(her contract), and over Nadia (a promise he broke). Renske had just found the
transfers. He had a great many enemies by 21:00, which is the point.

---

## What to capture during play

- Every question, verbatim
- Every improvisation where the card did not cover it
- Whether the shield works, meaning does Federico accept the theft confession
  and stop digging
- Whether he ever presses Renske on the money
- Whether he reaches Wouter at all, and by what route
- Where it drags
