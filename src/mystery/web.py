"""Play in a browser instead of a terminal.

    uv run python -m mystery.web --setting "a private view at a small art gallery"

Then open http://localhost:8000.

One game, held in memory, one process. No database, no sessions, no auth: this
exists so that two people can find out whether the game is any good, which is the
only question that matters right now. Everything it does not do is deliberate.

`--share` binds to the local network so anyone on the same wifi can join by
opening a browser. They share one case and one notebook, which turns out to be
the right behaviour for two people solving something together rather than an
oversight to fix later.
"""

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from mystery.agent import Brief, Responder, ask, ask_stream, build_brief
from mystery.daily import todays_case, waiting
from mystery.gallery import ART, Gallery
from mystery.gallery import gallery as pick_gallery
from mystery.generator import (
    DRAFT_MODEL,
    VOICE_MODEL,
    GenerationFailed,
    GenerationRequest,
    anthropic_drafter,
    complaint_about_setting,
    fresh_seed,
    generate,
)
from mystery.interrogation import (
    Statement,
    Transcript,
    assertions_from,
    word_got_back,
)
from mystery.knowledge import analyse_alibi, derive
from mystery.library import S3Shelf, catalogue
from mystery.library import shelf as pick_shelf
from mystery.models import Mystery
from mystery.palette import occasion
from mystery.palette import questions as questions_for
from mystery.session import InMemorySessions, Session, Sessions
from mystery.session import sessions as pick_sessions
from mystery.solvable import analyse, report
from mystery.solver import solve_until_valid
from mystery.topology import DEFAULT as DEFAULT_TOPOLOGY
from mystery.topology import LIBRARY, assess, drawn
from mystery.topology import get as get_topology

log = structlog.get_logger()

CACHE = Path("var/mysteries")


def _unique(rows: list[dict]) -> list[dict]:
    """Distinct lines, in a stable order. `leads` can produce the same sentence
    twice, and a set will not hold a dict."""
    seen: dict[str, dict] = {}
    for row in rows:
        seen.setdefault(row["text"], row)
    return [seen[text] for text in sorted(seen)]


def _initials(characters: list) -> dict[str, str]:
    """Short tags for the timeline grid, one per character, all distinct.

    Initials only work as stand-ins if no two people share a pair, so a
    collision grows the tag along the surname: two Vermeers become IV and IVE
    rather than two identical squares the player cannot tell apart.
    """
    tags: dict[str, str] = {}
    taken: set[str] = set()
    for character in characters:
        parts = [p for p in character.name.replace("-", " ").split() if p] or ["?"]
        tag = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else parts[0][1:2])).upper()
        rest = parts[-1][1:].upper()
        while tag in taken and rest:
            tag, rest = tag + rest[0], rest[1:]
        while tag in taken:
            tag += "'"
        taken.add(tag)
        tags[character.id] = tag
    return tags


# How many questions there are before the police arrive (D-128).
#
# The police being "an hour away" has been fiction since the compliance model was
# written: nothing counted, nothing ran out, and a player asked a hundred and
# thirty two questions in one evening. Two things follow from making it real.
#
# The design one: a question that costs nothing is a question you do not have to
# think about, so the interesting move — work out who is worth pressing, and on
# what — never has to be made. Scarcity is what turns asking into choosing.
#
# The other one is that this is also the cost control. A played evening is voice
# calls, and it is the only number in the project that both improves the game and
# pays for it, which is a suspicious coincidence and worth naming rather than
# pretending it was purely taste.
#
# Zero means "deal it from the seed" (D-129). A single global forty was wrong
# twice: too tight, since two real evenings ran to 132 and 106 questions and were
# enjoyed, and leaning on a cost argument that did not survive being checked —
# with prompt caching a hundred question evening is about fifty four cents. A cap
# nobody reaches creates no scarcity and a cap that always bites is just a
# shorter game, so it varies per case, in a wide band, and the briefing says it.
QUESTIONS = 0

# What is left when the game starts saying so. Not a countdown from the first
# question: a clock you can see the whole time is a clock you play against
# instead of playing the game.
GETTING_LATE = 12


class Case:
    """What was generated, and never changes again (D-077).

    The mystery, everything derived from it, and the pictures. Built once and
    shared by everybody playing it, because none of it is anybody's private
    business: the briefs are per character, not per player, and two people
    asking the same suspect the same question are entitled to the same facts.
    """

    def __init__(
        self,
        mystery: Mystery,
        id: str = "",
        portraits: dict[str, str] | None = None,
        scenery: dict[str, str] | None = None,
        setting: str = "",
        seed: int = 0,
        budget: int = 0,
    ) -> None:
        self.id = id or mystery.title
        self.mystery = mystery
        # What the evening is, in the words the case was generated from. The
        # briefing screen says it; nothing else needs it (D-126).
        self.setting = setting
        # How long before the police arrive, dealt from the case's own seed
        # (D-129), so it is a property of the evening rather than a setting.
        self.budget = budget or questions_for(seed)
        self.portraits = portraits or {}
        self.scenery = scenery or {}
        self.knowledge = derive(mystery)
        self.briefs = {
            c.id: build_brief(mystery, self.knowledge, c.id)
            for c in mystery.characters
            if c.id != mystery.victim
        }
        # Where the pictures actually are (D-121). A folder on a laptop, a
        # bucket on a deployment, and the routes below do not know which.
        self.gallery: Gallery | None = None


class Game:
    """One player, one case: a view rather than a thing.

    Cheap to build, because everything expensive is on the `Case` and everything
    mutable is on the `Session`. One of these exists for the length of a request
    and is thrown away, which is what lets a single process serve people who are
    not solving the same evening together.
    """

    def __init__(
        self,
        case: Case | Mystery,
        responder: Responder,
        portraits: dict[str, str] | None = None,
        scenery: dict[str, str] | None = None,
        session: Session | None = None,
        budget: int = QUESTIONS,
    ) -> None:
        # A bare mystery still works and makes its own case. Most of the tests
        # and every terminal path have no interest in any of this.
        self.case = (
            case
            if isinstance(case, Case)
            else Case(case, portraits=portraits, scenery=scenery)
        )
        self.responder = responder
        self.session = session or Session(case_id=self.case.id)
        # Zero means the case decides, from its own seed (D-129). Anything else
        # is somebody overriding it with `--questions`.
        self.budget = budget or self.case.budget

    @property
    def mystery(self) -> Mystery:
        return self.case.mystery

    @property
    def briefs(self):
        return self.case.briefs

    @property
    def knowledge(self):
        return self.case.knowledge

    @property
    def setting(self) -> str:
        return self.case.setting

    @property
    def portraits(self) -> dict[str, str]:
        return self.case.portraits

    @property
    def scenery(self) -> dict[str, str]:
        return self.case.scenery

    @property
    def transcript(self) -> Transcript:
        return self.session.transcript

    @property
    def solved(self) -> bool:
        return self.session.solved

    @solved.setter
    def solved(self, value: bool) -> None:
        self.session.solved = value

    @property
    def names(self) -> dict[str, str]:
        """Everything the notebook might have to name.

        Objects go in beside people (D-131), because a thing's path is
        reconstructed from testimony exactly the way a person's is, and the grid
        that shows one has to be able to show the other. Without this the
        timeline prints a raw id where the murder weapon should be.
        """
        return {
            **{c.id: c.name for c in self.mystery.characters},
            **{t.id: t.name for t in self.mystery.things},
        }

    @property
    def times(self) -> dict[str, str]:
        return {s.id: s.label for s in self.mystery.slots}

    @property
    def places(self) -> dict[str, str]:
        return {p.id: p.name for p in self.mystery.places}

    def history(self, who: str) -> list[tuple[str, str]]:
        """What this character has already said, so they can stay consistent."""
        return [
            (s.question, s.speech) for s in self.transcript.statements if s.speaker == who
        ]

    @property
    def held(self) -> list[dict]:
        """What the player is carrying (D-087).

        Derived, never stored. An object exists because the secret it belongs to
        has surfaced, so the inventory is a view over the transcript and cannot
        drift out of step with it the way a second list would.
        """
        found = self.transcript.surfaced_secrets()
        names = self.names
        return [
            {
                "id": secret.id,
                "name": secret.evidence,
                "from": names.get(secret.holder, secret.holder),
            }
            for secret in self.mystery.secrets
            if secret.evidence and secret.id in found
        ]

    def brief_for(self, who: str) -> "Brief":
        """This character's brief, as it stands for this player.

        The shared one on the `Case` is the baseline, built as though nothing has
        been produced to anybody. It stays shared, because that is true for
        almost every character in almost every session. Somebody who has been
        shown something gets theirs rebuilt, which is pure computation over data
        already in memory and costs nothing worth caching.
        """
        seen = self.session.seen_by(who)
        brief = (
            self.case.briefs[who]
            if not seen
            else build_brief(self.mystery, self.knowledge, who, shown=seen)
        )

        # What the house has been saying (D-099). Recomputed per question rather
        # than stored, because it is a view over the transcript and a stored
        # copy is a second version of the same fact waiting to disagree with the
        # first. The shared brief on the `Case` is never mutated: this is one
        # player's evening, and two people playing the same case are not in the
        # same building.
        heard = word_got_back(self.transcript, self.mystery, self.knowledge, who)
        if not heard:
            return brief
        return replace(brief, word=heard)

    def show(self, who: str, secret_id: str) -> bool:
        """Put an object in front of somebody. Returns whether they have now seen it.

        Refuses anything the player is not actually holding, because the page is
        not the authority on what the player has found: a crafted request must
        not be able to open a gate the transcript never opened.
        """
        if secret_id not in {item["id"] for item in self.held}:
            return False
        self.session.show(who, secret_id)
        log.info("game.shown", to=who, evidence=secret_id)
        return True

    @property
    def asked(self) -> int:
        return self.transcript.rounds

    @property
    def left(self) -> int:
        """Questions before the police arrive. Never negative (D-128)."""
        return max(0, self.budget - self.asked)

    @property
    def out_of_time(self) -> bool:
        return self.left <= 0

    def ask_stream(self, who: str, question: str):
        """The same question, answered a piece at a time (D-142).

        Yields the new text as it arrives and records the statement at the end,
        which is the only ordering that works: the transcript is what the
        notebook and the ledger are built from, and half an answer is not a
        statement about anything.
        """
        brief = self.brief_for(who)
        reply = None
        for event in ask_stream(
            brief,
            question,
            self.responder,
            history=self.history(who),
            ledger=self.transcript.ledger(self.mystery, who),
        ):
            if "text" in event:
                yield event["text"]
            if "reply" in event:
                reply = event["reply"]
        if reply is None:
            return
        self.transcript.record(
            Statement(
                round=self.transcript.rounds + 1,
                speaker=who,
                question=question,
                speech=reply.speech,
                assertions=assertions_from(brief, reply),
                refused=reply.refused,
                cited=list(reply.used),
            )
        )

    def ask(self, who: str, question: str) -> str:
        brief = self.brief_for(who)
        # The ledger is what they have committed to; the history is only the
        # last few exchanges (D-140). Both are views over the transcript,
        # recomputed per question rather than stored, for the same reason
        # `word_got_back` is: a stored copy is a second version waiting to
        # disagree with the first.
        reply = ask(
            brief,
            question,
            self.responder,
            history=self.history(who),
            ledger=self.transcript.ledger(self.mystery, who),
        )
        self.transcript.record(
            Statement(
                round=self.transcript.rounds + 1,
                speaker=who,
                question=question,
                speech=reply.speech,
                assertions=assertions_from(brief, reply),
                refused=reply.refused,
                cited=list(reply.used),
            )
        )
        return reply.speech

    def notebook(self) -> dict:
        names, times, places = self.names, self.times, self.places

        # Objects come off the notebook (D-139). They stayed in the case and in
        # the briefs, so a suspect can still say where the bangle was, but they
        # are no longer tracked on the grid: measured over a played case they
        # were cited five times in seventy-one questions and never started a
        # thread, because a player cannot ask about a thing they do not know
        # exists. Filtering here rather than in four places downstream is what
        # keeps the grid, the plan and the person pages agreeing with each other.
        cast = {c.id for c in self.mystery.characters}

        claims: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for statement in self.transcript.statements:
            for a in statement.assertions:
                if a.subject not in cast:
                    continue
                claims.setdefault((a.subject, a.slot), set()).add((statement.speaker, a.place))

        grid = [
            {
                "subject": names.get(subject, subject),
                "time": times.get(slot, slot),
                "place": places.get(place, place),
                "source": "themselves" if speaker == subject else names.get(speaker, speaker),
                "disputed": len({p for _, p in said}) > 1,
            }
            for (subject, slot), said in sorted(claims.items())
            for speaker, place in sorted(said)
        ]

        # Slot order, so a person's evening reads top to bottom rather than
        # alphabetically by the label somebody happened to write.
        rank = {s.id: s.index for s in self.mystery.slots}

        conflicts = [
            {
                "text": (
                    f"{names.get(c.subject, c.subject)} at {times.get(c.slot, c.slot)}: "
                    f"{names.get(c.first[0], c.first[0])} says "
                    f"{places.get(c.first[1], c.first[1])}, "
                    f"{names.get(c.second[0], c.second[0])} says "
                    f"{places.get(c.second[1], c.second[1])}"
                ),
                "kind": "changed their story" if c.is_self_contradiction else "disagreement",
                # Everybody the disagreement touches, so a person's own page can
                # show the ones that are about them (D-135). The subject is in
                # here as well as the two speakers: being the person two other
                # people disagree about is the thing worth seeing on your page.
                "who": sorted({c.subject, c.first[0], c.second[0]}),
            }
            for c in self.transcript.contradictions()
            if c.subject in cast
        ]

        # A lead is about two people: the one whose story is unconfirmed, and
        # the one who could confirm it. Which of them is which decides what the
        # line means on a page, so the ids travel with the sentence (D-135)
        # rather than the page fishing for a name inside the prose.
        leads = self.transcript.leads(self.mystery, self.knowledge)
        holes = _unique(
            [
                {
                    "text": (
                        f"{names.get(x.claimant, x.claimant)} says "
                        f"{places.get(x.place, x.place)} at {times.get(x.slot, x.slot)}, but "
                        f"{names.get(x.silent_witness, x.silent_witness)} described that room "
                        f"then and did not mention them"
                    ),
                    "of": x.claimant,
                    "ask": x.silent_witness,
                }
                for x in leads
                if x.witness_has_spoken
            ]
        )
        unasked = _unique(
            [
                {
                    "text": (
                        f"{names.get(x.claimant, x.claimant)} says "
                        f"{places.get(x.place, x.place)} at {times.get(x.slot, x.slot)}. "
                        f"Nobody has confirmed it. Ask "
                        f"{names.get(x.silent_witness, x.silent_witness)}"
                    ),
                    "of": x.claimant,
                    "ask": x.silent_witness,
                }
                for x in leads
                if not x.witness_has_spoken
            ]
        )


        # Per-person transcripts, so a player can reread one conversation rather
        # than scrolling a single mixed log looking for who said what.
        logs: dict[str, list[dict]] = {c.id: [] for c in self.mystery.characters}
        for s in self.transcript.statements:
            logs.setdefault(s.speaker, []).append({"q": s.question, "a": s.speech})

        # Where everyone is *claimed* to have been, as a timeline rather than a
        # snapshot (D-062). Rooms down the side, slots across, people reduced to
        # initials so a whole evening fits in a panel. The old version showed one
        # slot at a time, which is the wrong shape: an alibi is read by comparing
        # slots, and a player flicking between five tabs is holding the grid in
        # their head, which is the job the notebook was supposed to take over.
        tags = _initials(self.mystery.characters)
        timeline: dict[str, dict[str, list[dict]]] = {}
        accounted: dict[str, set[str]] = {s.id: set() for s in self.mystery.slots}
        for (subject, slot), said in claims.items():
            told = {p for _, p in said}
            accounted.setdefault(slot, set()).add(subject)
            for place in sorted(told):
                sources = sorted({names.get(sp, sp) for sp, p in said if p == place})
                timeline.setdefault(slot, {}).setdefault(place, []).append(
                    {
                        "id": subject,
                        "tag": tags.get(subject, "??"),
                        "name": names.get(subject, subject),
                        # Two people put them in two different rooms at this
                        # moment. One of them is wrong and that is the game.
                        "disputed": len(told) > 1,
                        # One person's word, or two. A claim somebody else
                        # corroborated is a different object to a claim about
                        # yourself, and the grid should not flatten them.
                        "firm": len(sources) > 1,
                        "source": ", ".join(sources),
                    }
                )

        # Nobody has placed these people at this hour. Not innocence, not guilt:
        # a hole in what the player has been told, which is worth seeing.
        missing = {
            s.id: [
                {"tag": tags[c.id], "name": c.name}
                for c in self.mystery.characters
                if c.id not in accounted.get(s.id, set())
            ]
            for s in self.mystery.slots
        }

        # ---- one page per person (D-135) -------------------------------------
        # The notebook was a timeline with a story printed beside it: nine tenths
        # of it was person-place-slot, which is the axis the case is deliberately
        # least decided by. Two more axes were added (a thing's path, D-131, and
        # an account of a scene, D-132) and neither had anywhere to be read.
        #
        # So the notebook is now built around the person rather than the grid.
        # Four questions per suspect, which are the four a player actually holds
        # in their head: what have they admitted, what has anybody else said
        # about them, what have they said about everybody else, and what have
        # they refused. The grid stays, one row deep, inside their own page.
        given = self.transcript.who_gave_up()
        surfaced = self.transcript.surfaced_secrets()
        asked_of = self.transcript.spoken_to()
        refusals: dict[str, int] = {}
        for statement in self.transcript.statements:
            if statement.refused:
                refusals[statement.speaker] = refusals.get(statement.speaker, 0) + 1

        def _rows(pairs: list[tuple[str, str, str, bool]]) -> list[dict]:
            return [
                {"time": times.get(s, s), "place": places.get(p, p), "who": w, "odd": d}
                for s, p, w, d in sorted(pairs, key=lambda r: (rank.get(r[0], 99), r[1]))
            ]

        people = []
        for c in self.mystery.characters:
            own: list[tuple[str, str, str, bool]] = []
            heard: list[tuple[str, str, str, bool]] = []
            told: list[tuple[str, str, str, bool]] = []
            for (subject, slot), said in claims.items():
                disputed = len({p for _, p in said}) > 1
                for speaker, place in said:
                    if subject == c.id and speaker == c.id:
                        own.append((slot, place, "their own word", disputed))
                    elif subject == c.id:
                        heard.append((slot, place, names.get(speaker, speaker), disputed))
                    elif speaker == c.id:
                        told.append((slot, place, names.get(subject, subject), disputed))

            # What has come out of, or about, this person. A secret they gave up
            # themselves reads differently to one somebody else handed over, and
            # the notebook has never distinguished them.
            admits = [
                {
                    "text": s.summary,
                    "from": "they told you" if given.get(s.id) == c.id
                    else names.get(given.get(s.id, ""), "somebody else"),
                    "mine": given.get(s.id) == c.id,
                }
                for s in self.mystery.secrets
                if s.id in surfaced and s.holder == c.id
            ]
            about = [
                {"text": s.summary, "from": names.get(given.get(s.id, ""), "somebody")}
                for s in self.mystery.secrets
                if s.id in surfaced and s.about == c.id and s.holder != c.id
            ]

            people.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "tag": tags.get(c.id, "??"),
                    "role": c.role,
                    "dead": c.id == self.mystery.victim,
                    "asked": asked_of.get(c.id, 0),
                    "refused": refusals.get(c.id, 0),
                    "own": _rows(own),
                    "heard": _rows(heard),
                    "told": _rows(told),
                    "admits": admits,
                    "about": about,
                }
            )

        return {
            "grid": grid,
            "people": people,
            "conflicts": conflicts,
            "holes": holes,
            "unasked": unasked,
            "questions": self.transcript.rounds,
            # What is left before the police arrive (D-128). Sent every time so
            # the page never has to count, and so the count survives a reload.
            "left": self.left,
            "budget": self.budget,
            "late": self.left <= GETTING_LATE,
            "over": self.out_of_time,
            "logs": logs,
            # What the player is carrying, and who has already been made to look
            # at it (D-087). Both live here rather than in /state because both
            # change as the evening goes and /state is fetched once.
            "held": self.held,
            "shown": {who: list(ids) for who, ids in self.session.shown.items()},
            # Everything that has actually come out, which is what the
            # accusation offers as possible motives (D-065).
            "found": [
                {"id": secret.id, "text": secret.summary}
                for secret in self.mystery.secrets
                if secret.id in self.transcript.surfaced_secrets()
            ],
            "timeline": timeline,
            "missing": missing,
            "tags": [
                {"tag": tags[c.id], "name": c.name, "dead": c.id == self.mystery.victim}
                for c in self.mystery.characters
            ],
        }

    def accuse(self, who: str, why: str | None = None) -> dict:
        """Name a killer, and name what you think they did it for.

        A name on its own was a one-bit answer to a case with one hidden
        variable, and a coin flip beat a bad player (D-065). Naming the motive
        as well means the timeline gets you to the person and only the secrets
        get you to the reason, so "right person, wrong reason" becomes its own
        ending rather than being scored as a win.
        """
        self.solved = True
        m, names, places, times = self.mystery, self.names, self.places, self.times

        motive = next(
            (s for s in m.secrets if s.holder == m.killer and s.is_motive),
            next((s for s in m.secrets if s.holder == m.killer), None),
        )
        analysis = analyse_alibi(m, self.knowledge)

        lie = None
        if m.false_claim:
            truth = m.placements.get(m.false_claim.character, {}).get(m.false_claim.slot)
            lie = (
                f"{names.get(m.false_claim.character, m.false_claim.character)} claimed the "
                f"{places.get(m.false_claim.place, m.false_claim.place)} at "
                f"{times.get(m.false_claim.slot, m.false_claim.slot)}. They were in the "
                f"{places.get(truth, truth)}."
            )

        # The reason is written in the player's own words and is not marked
        # (D-092). Twice now a player worked out exactly why the killer did it
        # and picked a secret the code did not consider the motive, because the
        # reason was spread across two of them. Grading it needed the case to
        # agree with itself about which sentence counted, which it does not, and
        # a player who understands the case does not need to be told they are
        # wrong on a technicality. So the charge is quoted back beside the truth
        # and the player marks their own.
        found = self.transcript.surfaced_secrets()

        return {
            "correct": who == m.killer,
            "charged": (why or "").strip(),
            "accused": names.get(who, who),
            "killer": names.get(m.killer, m.killer),
            "questions": self.transcript.rounds,
            "motive": motive.summary if motive else None,
            "lie": lie,
            # Everybody who lied, and what each lie was actually for. The point
            # of the reveal now is not only "it was him", it is "here is what
            # the other two were hiding, which is why you could not tell".
            "lies": [
                {
                    "name": names.get(c.character, c.character),
                    "claimed": places.get(c.place, c.place),
                    "time": times.get(c.slot, c.slot),
                    "truth": places.get(
                        m.placements.get(c.character, {}).get(c.slot), "?"
                    ),
                    "covering": next(
                        (x.summary for x in m.secrets if x.id == c.covers), ""
                    ),
                    "killer": c.character == m.killer,
                }
                for c in m.false_claims
            ],
            # Everything that did come out, next to everything that did not, so
            # the player can see their own reasoning laid against the case.
            "surfaced": [
                s.summary for s in m.secrets if s.id in found
            ],
            "witnesses": [
                {
                    "name": names.get(p, p),
                    "asked": self.transcript.asked(p),
                }
                for p in analysis.contradictors
            ],
            # What never came out, measured by citation rather than by whether
            # the holder happened to be mentioned. The old version counted a
            # secret as found because somebody had placed its holder in a room.
            "missed": [
                f"{names.get(s.holder, s.holder)}: {s.summary}"
                for s in m.secrets
                if s.id not in found
            ],
        }


class Question(BaseModel):
    who: str
    text: str


class Produced(BaseModel):
    who: str
    evidence: str


class Accusation(BaseModel):
    who: str
    why: str | None = None


COOKIE = "mystery_session"


def build_app(
    case: Case | Game,
    responder: Responder | None = None,
    sessions: Sessions | None = None,
    budget: int = QUESTIONS,
    together: bool = False,
) -> FastAPI:
    """One case, any number of people playing it separately (D-077).

    `together` puts everybody in one session, which is the old behaviour and the
    right one for two people in a room with one notebook between them. Off, each
    visitor gets their own transcript, keyed by a cookie, which is the only way
    a public URL makes any sense.

    Passing a `Game` still works and means `together`: it is one player's view,
    so serving it serves that view to everyone.
    """
    app = FastAPI()

    if isinstance(case, Game):
        store: Sessions = sessions or InMemorySessions()
        shared: Session | None = case.session
        store.save(shared)
        responder = responder or case.responder
        case = case.case
        together = True
    else:
        store = sessions or InMemorySessions()
        shared = store.create(case.id) if together else None

    if responder is None:
        raise ValueError("build_app needs a responder unless it is given a Game")

    the_case: Case = case
    answer: Responder = responder

    def player(request: Request, response: Response) -> Game:
        """The session this request belongs to, made if it does not exist yet."""
        if shared is not None:
            return Game(the_case, answer, session=shared, budget=budget)

        found = store.get(request.cookies.get(COOKIE, ""))

        # A session belongs to a case, and the cookie did not know that (D-107).
        # Serve a dry run, poke at it, stop the server, serve a different case on
        # the same port in the same browser, and the old session came back: one
        # transcript holding two casts, a notebook mixing two evenings, and
        # gossip carrying news about people who are not in the building. Found in
        # a real session record whose `case_id` named a case four of its hundred
        # and one questions belonged to.
        if found is not None and found.case_id and found.case_id != the_case.id:
            log.info("session.new_case", was=found.case_id, now=the_case.id)
            found = None

        if found is None:
            found = store.create(the_case.id)
            response.set_cookie(
                COOKIE, found.id, httponly=True, samesite="lax", max_age=60 * 60 * 12
            )
        return Game(the_case, answer, session=found, budget=budget)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/state")
    def state(request: Request, response: Response) -> dict:
        game = player(request, response)
        return {
            "title": game.mystery.title,
            "victim": game.names.get(game.mystery.victim, ""),
            "suspects": [
                {
                    "id": c.id,
                    "name": c.name,
                    # `wants` and `manner` are not sent. A tooltip on the cast
                    # chips was showing every suspect's private motive, which is
                    # the game handing over its own answer (D-074).
                    "role": c.role,
                    "gender": c.gender,
                    "look": c.look,
                    "portrait": (
                        f"/portrait/{c.id}.png" if c.id in game.portraits else None
                    ),
                }
                for c in game.mystery.characters
                if c.id != game.mystery.victim
            ],
            "times": [
                {"id": s.id, "label": s.label}
                for s in sorted(game.mystery.slots, key=lambda s: s.index)
            ],
            "places": [
                {
                    "id": p.id,
                    "name": p.name,
                    "adjacent": list(p.adjacent),
                    "scene": f"/scene/{p.id}.png" if p.id in game.scenery else None,
                }
                for p in game.mystery.places
            ],
            "scene": "/scene/setting.png" if "setting" in game.scenery else None,
            # Who the player is tonight (D-101). Shown, because a position the
            # player cannot see is not a position they can play.
            "you": (
                {
                    "role": game.mystery.investigator.role,
                    "why": game.mystery.investigator.why_here,
                    "standing": game.mystery.investigator.standing,
                }
                if game.mystery.investigator
                else None
            ),
            "discovery": (
                {
                    "finder": game.names.get(
                        game.mystery.discovery.finder, game.mystery.discovery.finder
                    ),
                    "place": game.places.get(
                        game.mystery.discovery.place, game.mystery.discovery.place
                    ),
                    "summary": game.mystery.discovery.summary,
                }
                if game.mystery.discovery
                else None
            ),
            # What everybody in the building would say the same way (D-111).
            # The suspects have had this verbatim since it existed; the player
            # had to infer it from five people talking (D-126).
            "common": list(game.mystery.common_ground),
            # What they asked you for (D-129). Stated plainly, and about two in
            # five are wrong about something, which the player is not told.
            "commission": game.mystery.commission,
            "occasion": game.setting,
            "notebook": game.notebook(),
        }

    def _picture(kind: str, filename: str):
        """One route body for faces and rooms (D-121).

        A gallery that can hand out a link says so and the browser is sent
        straight there, which keeps a megabyte and a half of PNG out of the
        application entirely. One that cannot returns the bytes instead, which
        is what a folder on this machine does.
        """
        from fastapi.responses import RedirectResponse
        from fastapi.responses import Response as Sent

        names = the_case.portraits if kind == "portraits" else the_case.scenery
        name = names.get(filename.removesuffix(".png"))
        store = the_case.gallery
        if not name or store is None:
            return Sent(status_code=404)

        link = store.link(the_case.id, kind, name)
        if link:
            # 307 rather than 302: the link expires, so nothing should cache the
            # redirect and hand somebody a dead URL an hour from now.
            return RedirectResponse(link, status_code=307)

        data = store.read(the_case.id, kind, name)
        return Sent(status_code=404) if data is None else Sent(data, media_type="image/png")

    @app.get("/portrait/{filename}")
    def portrait(filename: str):
        return _picture("portraits", filename)

    @app.get("/scene/{filename}")
    def scene(filename: str):
        return _picture("scenery", filename)

    @app.post("/ask")
    def ask_endpoint(question: Question, request: Request, response: Response) -> dict:
        game = player(request, response)
        # Refused here rather than in the page, because the page is not the
        # authority on anything and a budget the browser enforces is not a
        # budget (D-128). The model is never called, so an exhausted evening
        # costs nothing at all.
        if game.out_of_time:
            return {
                "speech": "",
                "over": True,
                "notebook": game.notebook(),
            }
        speech = game.ask(question.who, question.text)
        store.save(game.session)
        return {"speech": speech, "left": game.left, "notebook": game.notebook()}

    @app.post("/ask/live")
    def ask_live(question: Question, request: Request, response: Response):
        """The same answer, sent as it is spoken (D-142).

        Server-sent events over POST, so the page reads it with `fetch` rather
        than `EventSource`, which only does GET. `/ask` stays exactly as it was:
        it is what the suite uses, it is the fallback when a stream breaks, and
        a responder with no `.stream` reaches the same code either way.
        """
        game = player(request, response)
        if game.out_of_time:
            body = json.dumps({"over": True, "notebook": game.notebook()})
            return StreamingResponse(
                iter([f"data: {body}\n\n"]), media_type="text/event-stream"
            )

        def events():
            try:
                for piece in game.ask_stream(question.who, question.text):
                    yield f"data: {json.dumps({'text': piece})}\n\n"
            except Exception as problem:  # noqa: BLE001 - the page needs to hear about it
                log.warning("web.stream_failed", error=str(problem))
                yield f"data: {json.dumps({'failed': True})}\n\n"
                return
            store.save(game.session)
            done = {"done": True, "left": game.left, "notebook": game.notebook()}
            yield f"data: {json.dumps(done)}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/show")
    def show_endpoint(produced: Produced, request: Request, response: Response) -> dict:
        """Put an object in front of somebody (D-087).

        A turn in its own right, not a question: nothing is said, nothing is
        recorded in the transcript, and no model is called, so it costs nothing.
        What changes is the brief this character is handed from here on.
        """
        game = player(request, response)
        opened = game.show(produced.who, produced.evidence)
        store.save(game.session)
        return {"opened": opened, "notebook": game.notebook()}

    @app.post("/accuse")
    def accuse_endpoint(
        accusation: Accusation, request: Request, response: Response
    ) -> dict:
        game = player(request, response)
        verdict = game.accuse(accusation.who, accusation.why)
        store.save(game.session)
        return verdict

    return app


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interrogation</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bodoni+Moda:opsz,wght@6..96,400;6..96,600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500&display=swap">
<style>
:root{--bg:#0b0d12;--deep:#070810;--panel:#141822;--panel2:#1b2029;--ink:#eceef4;
--muted:#8992a4;--rule:#252b38;--warm:#d9a24e;--cool:#7fa9ee;--bad:#e0736b;
/* Text that sits ON an accent rather than beside it. Dark here, light on the
   notebook's paper, which is the only reason it has to be a token (D-146). */
--contrast:#0b0d12;
--display:"Bodoni Moda",Didot,serif;--body:"IBM Plex Sans",system-ui,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,monospace}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--deep);color:var(--ink);font-family:var(--body);
overflow:hidden;user-select:none}
#scene{position:fixed;inset:0;display:flex;flex-direction:column;
background:radial-gradient(ellipse at 50% 34%,#1a2030 0%,#0b0d12 62%,#070810 100%);
transition:right .32s cubic-bezier(.2,.8,.2,1)}
/* The generated backdrop, if there is one (D-069). Two layers so a room can
   cross-fade in over the setting rather than snapping, and both sit under a
   heavy vignette because every word on this screen has to stay readable over
   whatever the image turned out to be. */
#backdrop,#backdrop2{position:absolute;inset:0;background-size:cover;
background-position:center;opacity:0;transition:opacity .9s ease;z-index:0}
#shade{position:absolute;inset:0;z-index:1;pointer-events:none;
background:radial-gradient(ellipse at 50% 38%,rgba(7,8,16,.30) 0%,
rgba(7,8,16,.66) 52%,rgba(7,8,16,.90) 100%)}
#top,#stage,#box,#bar{position:relative;z-index:2}
#where{position:absolute;right:22px;top:54px;z-index:3;font-family:var(--mono);
font-size:10.5px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);
opacity:0;transition:opacity .5s}
#where.on{opacity:.85}
th.rm.clickable{cursor:pointer;color:var(--cool)}
th.rm.clickable:hover{text-decoration:underline}
#scene.shifted{right:min(var(--book),92vw)}
@media(max-width:760px){#scene.shifted{right:0}}
#top{padding:14px 20px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;
z-index:3}
#top h1{font-family:var(--display);font-weight:400;font-size:22px;margin:0}
#top .sub{color:var(--muted);font-size:12.5px}
#top .right{margin-left:auto;display:flex;gap:8px;align-items:center}
#stage{flex:1;position:relative;display:flex;align-items:flex-end;
justify-content:center;min-height:0}
/* A generated portrait is a square image with its own dark ground, and over a
   backdrop that reads as a sticker with a visible edge (D-072). Feathering the
   image into whatever is behind it costs nothing and is the difference between
   a person standing in a room and a photograph taped to one. */
#photo{width:min(46vh,340px);display:none;
transition:transform .5s cubic-bezier(.2,.8,.2,1),opacity .35s;
transform-origin:bottom center;filter:drop-shadow(0 24px 60px rgba(0,0,0,.75));
-webkit-mask-image:radial-gradient(ellipse 62% 58% at 50% 44%,#000 58%,transparent 100%);
mask-image:radial-gradient(ellipse 62% 58% at 50% 44%,#000 58%,transparent 100%)}
#photo.enter{opacity:0;transform:translateY(22px) scale(.97)}
#portrait{width:min(46vh,340px);transition:transform .5s cubic-bezier(.2,.8,.2,1),
opacity .35s;transform-origin:bottom center;filter:drop-shadow(0 24px 60px rgba(0,0,0,.75))}
#portrait.enter{opacity:0;transform:translateY(22px) scale(.97)}
#portrait.rattled,#photo.rattled{animation:shake .5s}
@keyframes shake{0%,100%{transform:translateX(0)}20%{transform:translateX(-5px)}
40%{transform:translateX(5px)}60%{transform:translateX(-3px)}80%{transform:translateX(3px)}}
#box{margin:0 auto 0;width:min(920px,94%);background:linear-gradient(180deg,
rgba(20,24,34,.97),rgba(11,13,18,.99));border:1px solid var(--rule);
border-bottom:none;border-radius:10px 10px 0 0;padding:20px 26px 22px;
min-height:158px;z-index:2;box-shadow:0 -18px 60px rgba(0,0,0,.6)}
#nameplate{font-family:var(--display);font-size:23px;font-weight:600;
letter-spacing:.01em;margin-bottom:2px}
#nameplate small{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);font-weight:400;margin-left:10px}
#said{font-size:16.5px;line-height:1.62;min-height:3.2em;max-width:70ch}
/* The player's own voice, so it reads as neither the role label above it (mono,
   uppercase) nor the answer below it (plain). Italic display face, quietly. */
#said .asked{display:block;font-family:var(--display);font-style:italic;
font-size:13.5px;color:var(--muted);margin:7px 0 9px;max-width:60ch}
#said .asked em{font-style:normal;font-family:var(--mono);font-size:10px;
letter-spacing:.1em;text-transform:uppercase;opacity:.7;margin-left:8px}
#said .cursor{display:inline-block;width:.5em;height:1em;background:var(--cool);
vertical-align:-.12em;animation:blink .8s steps(2) infinite}
@keyframes blink{50%{opacity:0}}
#bar{width:min(920px,94%);margin:0 auto;background:var(--panel);
border:1px solid var(--rule);border-radius:0 0 10px 10px;padding:12px 14px;
display:flex;gap:10px;align-items:center;flex-wrap:wrap;z-index:2}
#cast{display:flex;gap:8px;flex-wrap:wrap}
.chip{background:none;border:1px solid var(--rule);border-radius:8px;padding:4px 8px 4px 4px;
display:flex;align-items:center;gap:7px;cursor:pointer;color:var(--muted);
font-family:var(--body);font-size:13px}
.chip svg{width:30px;height:36px;border-radius:5px;display:block}
.chip:hover{border-color:var(--muted);color:var(--ink)}
.chip.on{border-color:var(--cool);color:var(--ink);background:rgba(127,169,238,.09)}
#q{flex:1 1 260px;font-family:var(--body);font-size:15px;background:var(--deep);
color:var(--ink);border:1px solid var(--rule);padding:10px 13px;border-radius:6px}
#q:focus{outline:none;border-color:var(--cool)}
button{font-family:var(--body);font-size:13px;background:var(--panel2);color:var(--ink);
border:1px solid var(--rule);padding:7px 12px;border-radius:6px;cursor:pointer}
button:hover{border-color:var(--muted)}
button.accuse{border-color:var(--bad);color:var(--bad)}
.badge.late{color:var(--warm);border-color:var(--warm)}
.badge.spent{color:#c9564e;border-color:#c9564e}
.badge{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted)}
.badge b{color:var(--bad)}
/* The panel's width is a variable so it can be dragged (D-098). Everything that
   has to agree with it reads the same property: the panel, and the shift that
   keeps the portrait out from under it. */
/* The notebook is paper (D-146). The room is dark and the thing in your hands
   is not: it is the one surface in this game that belongs to the player rather
   than to the house, and the whole palette flips inside it. Every token is
   redefined here, so every component in the panel follows without knowing that
   anything happened, which is the point of having had tokens at all.

   Warm off-white, not white. The grain is three offset gradients rather than an
   image, and the ruled margin is a single faded line down the left the way it
   is on a legal pad. Restraint on purpose: a texture you notice is a texture
   that is too strong. */
#book{--panel:#f2ece0;--panel2:#e9e1d1;--ink:#211e18;--muted:#6d6559;
--rule:#cec4ae;--warm:#8a5712;--cool:#2b5794;--bad:#a3342a;--contrast:#f7f2e6;
position:fixed;top:0;right:0;bottom:0;width:min(var(--book),92vw);
color:var(--ink);
background-color:#f2ece0;
background-image:
  linear-gradient(90deg,transparent 27px,rgba(163,52,42,.22) 27px,
    rgba(163,52,42,.22) 28px,transparent 28px),
  radial-gradient(circle at 18% 12%,rgba(150,128,92,.10) 0,transparent 38%),
  radial-gradient(circle at 82% 63%,rgba(120,104,74,.09) 0,transparent 44%),
  linear-gradient(178deg,#f5efe4 0%,#efe8da 46%,#e9e1d2 100%);
border-left:1px solid #cec4ae;
box-shadow:-14px 0 34px rgba(0,0,0,.42),inset 1px 0 0 rgba(255,255,255,.55);
padding:22px 22px 22px 38px;overflow-y:auto;z-index:5;
transform:translateX(100%);transition:transform .32s cubic-bezier(.2,.8,.2,1);
user-select:text}
#book.open{transform:none}
/* The handle is a sibling of the panel rather than a child of it, and fixed
   rather than absolute. Inside a panel that scrolls, an absolutely positioned
   full-height handle covers only the first screenful and then scrolls away with
   the content, so it is missing exactly when the notebook is long enough that
   you want to widen it. It is wider than it looks, so it can be grabbed without
   aiming. */
#grip{position:fixed;top:0;bottom:0;width:11px;z-index:6;cursor:col-resize;
right:min(var(--book),92vw);margin-right:-5px;display:none}
#book.open~#grip,#grip.on{display:block}
#grip::after{content:"";position:absolute;left:4px;top:0;bottom:0;width:3px;
background:transparent;transition:background .15s}
#grip:hover::after,body.dragging #grip::after{background:var(--cool)}
@media(max-width:760px){#grip{display:none!important}}
/* While dragging, nothing animates and nothing selects: a panel easing towards
   the pointer feels broken, and a drag that highlights the transcript is worse. */
body.dragging{user-select:none;cursor:col-resize}
body.dragging #book,body.dragging #scene{transition:none}
#tabs{display:flex;gap:6px;margin-bottom:18px;position:sticky;top:-22px;
background:var(--panel);padding:6px 0 10px;z-index:2;
/* Reaches past the panel's own padding so nothing scrolls out beside it, and
   carries the ruled margin across itself so the line is not interrupted. */
margin-left:-38px;margin-right:-22px;padding-left:38px;padding-right:22px}
#book #tabs{background-image:linear-gradient(90deg,transparent 27px,
rgba(163,52,42,.22) 27px,rgba(163,52,42,.22) 28px,transparent 28px)}
#tabs button{flex:1;font-size:12px;padding:6px 4px}
#tabs button.on{background:var(--cool);color:var(--contrast);border-color:var(--cool);font-weight:500}
/* The timeline grid. Scrolls sideways on a phone rather than squeezing the
   columns until the initials wrap. */
.tlwrap{overflow-x:auto;margin:0 -4px;padding:0 4px}
table.tl{border-collapse:separate;border-spacing:3px;font-family:var(--mono);
font-size:11px;width:100%}
table.tl th{font-weight:500;color:var(--muted);font-size:9.5px;letter-spacing:.09em;
text-transform:uppercase;padding:2px 4px;text-align:center;white-space:nowrap}
table.tl th.rm{text-align:left;max-width:96px;white-space:normal;line-height:1.3}
table.tl td{background:var(--panel2);border:1px solid var(--rule);border-radius:5px;
min-width:44px;height:34px;padding:3px;text-align:center;vertical-align:middle}
table.tl tr.gap td{background:transparent;border-style:dashed}
table.tl tr.gap th.rm{color:var(--muted);opacity:.7}
.pin{display:inline-block;background:var(--cool);color:var(--contrast);font-size:10.5px;
font-weight:600;letter-spacing:.03em;border-radius:3px;padding:2px 4px;margin:1px;
cursor:default}
.pin.bad{background:var(--bad);color:var(--contrast)}
.pin.off{background:transparent;color:var(--muted);opacity:.75;border:1px solid var(--rule);font-weight:400}
.pin.dead{background:var(--muted);color:var(--contrast)}
/* Corroborated by somebody other than the person themselves. */
.pin.firm{box-shadow:0 0 0 1.5px var(--ink)}
.key{margin-top:12px;display:flex;flex-wrap:wrap;gap:5px 12px;font-size:11.5px;
color:var(--muted)}
.key span b{font-family:var(--mono);color:var(--ink);font-weight:600;margin-right:4px}
.qa{margin-bottom:14px}
.qa .qq{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-bottom:3px}
.qa .aa{font-size:13px;line-height:1.55}
#book h2{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin:22px 0 8px;font-weight:500}
#book h2:first-of-type{margin-top:0}
#book mark{background:#f4e39b;color:#3b3421}
/* On paper the ruled line under a row is ink, not a panel edge. */
#book td{border-bottom-color:rgba(70,60,42,.22)}
#book .item{box-shadow:0 1px 0 rgba(255,255,255,.5) inset}
#book #mynotes,#book #find{background:rgba(255,255,255,.45)}
table{width:100%;border-collapse:collapse;font-size:12px;font-family:var(--mono)}
td{padding:4px 5px;border-bottom:1px solid var(--rule);vertical-align:top}
tr.disputed td{color:var(--bad)}
.item{background:var(--panel2);border-left:2px solid var(--rule);padding:8px 11px;
margin-bottom:7px;font-size:12.5px;line-height:1.5;border-radius:0 4px 4px 0}
.item.pick{cursor:pointer;border-left-color:var(--cool)}
.item.pick:hover{background:var(--rule)}
.item.hard{border-left-color:var(--bad)}
.item.soft{border-left-color:var(--warm)}
.item.cold{border-left-color:var(--rule);color:var(--muted)}
.empty{color:var(--muted);font-size:12.5px}
/* One page per person (D-135). The row of names is the notebook's spine: who
   the page is about, and how much you have asked them. */
#dossiers{display:flex;flex-wrap:wrap;gap:4px;margin:0 0 14px}
.dt{background:var(--panel2);border:1px solid var(--rule);border-radius:5px;
padding:5px 9px;color:var(--muted);font-family:var(--mono);font-size:11px;
cursor:pointer;display:flex;align-items:center;gap:6px}
.dt:hover{color:var(--ink)}
.dt.on{color:var(--ink);border-color:var(--cool);background:var(--panel)}
.dt span{font-size:9.5px;color:var(--muted);font-variant-numeric:tabular-nums}
.dt.on span{color:var(--cool)}
.dossier h3{font-family:var(--display);font-size:21px;font-weight:400;
margin:0 0 12px}
.dossier h3{margin-bottom:2px}
.who-is{color:var(--muted);font-size:12.5px;margin-bottom:12px}
.dossier h4{font-family:var(--mono);font-size:10px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin:18px 0 6px;font-weight:500}
.dossier table{margin-bottom:4px}
/* A centred flex child taller than the viewport loses its top edge, and the
   overflow cannot be scrolled back to because it is above the start of the box.
   `margin:auto` on the card centres it when it fits and leaves it alone when it
   does not, which is the fix rather than `align-items:center` (D-106). */
#brief{position:fixed;inset:0;background:rgba(5,6,9,.97);display:none;
justify-content:center;padding:24px;overflow-y:auto;z-index:11;user-select:text}
#brief.on{display:flex}
#brief .card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:34px 38px;max-width:660px;width:100%;margin:auto;height:max-content}
#brief h2{font-family:var(--display);font-size:32px;margin:0 0 2px;font-weight:400}
/* The case cover (D-144). The establishing shot, used as a picture rather than
   as wallpaper, with the title set over it. */
#brief .cover{position:relative;margin:-30px -30px 0;height:210px;
border-radius:10px 10px 0 0;background:var(--panel2) center/cover no-repeat;
display:flex;align-items:flex-end;overflow:hidden}
#brief .cover::after{content:"";position:absolute;inset:0;
background:linear-gradient(180deg,rgba(7,8,16,.30) 0%,rgba(7,8,16,.55) 45%,
rgba(20,24,34,.97) 100%)}
#brief .coverink{position:relative;z-index:1;padding:0 30px 16px;width:100%}
#brief .cover h2{font-size:40px;line-height:1.04;margin:0 0 6px;
text-shadow:0 2px 18px rgba(0,0,0,.6)}
#brief .cover .where{margin:0}
/* No establishing shot for this case: the band collapses to the title rather
   than holding open two hundred pixels of nothing. */
#brief .cover.bare{height:auto;background:none;margin-bottom:0}
#brief .cover.bare::after{display:none}
#brief .cover.bare .coverink{padding:8px 30px 0}
#brief .cover.bare h2{font-size:34px;text-shadow:none}
#brief .faces{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0 22px}
#brief .mug{display:flex;flex-direction:column;align-items:center;gap:5px;width:52px}
#brief .mug img,#brief .mug svg{width:46px;height:56px;border-radius:5px;
object-fit:cover;display:block;filter:grayscale(.45) contrast(1.04);
border:1px solid var(--rule)}
#brief .mug em{font-family:var(--mono);font-size:9.5px;font-style:normal;
color:var(--muted);letter-spacing:.04em}
#brief .where{font-family:var(--mono);font-size:10px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin-bottom:24px}
#brief h4{font-family:var(--mono);font-size:10px;letter-spacing:.14em;
text-transform:uppercase;color:var(--cool);margin:22px 0 7px;font-weight:400}
#brief p{margin:0 0 9px;line-height:1.6;font-size:14px}
#brief ul{margin:0;padding-left:17px}
#brief li{margin-bottom:6px;line-height:1.55;font-size:14px}
#brief .roster{display:grid;grid-template-columns:auto 1fr;gap:3px 14px;font-size:13px}
#brief .roster b{font-weight:600;white-space:nowrap}
#brief .roster span{color:var(--muted)}
#brief .clock{color:var(--warm)}
#brief .go{margin-top:28px;background:var(--cool);border:0;border-radius:7px;
padding:11px 22px;font-family:var(--display);font-size:15px;color:#08090c;
cursor:pointer}
#brief .go:hover{filter:brightness(1.1)}
#briefagain{background:none;border:0;color:var(--muted);font-family:var(--mono);
font-size:10px;letter-spacing:.1em;text-transform:uppercase;cursor:pointer;padding:0}
#briefagain:hover{color:var(--ink)}
#reveal{position:fixed;inset:0;background:rgba(5,6,9,.95);display:none;
justify-content:center;padding:24px;overflow-y:auto;z-index:9;user-select:text}
#reveal.on{display:flex}
#reveal .card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:32px;max-width:640px;width:100%;margin:auto;height:max-content}
#reveal h3{font-family:var(--display);font-size:34px;margin:0 0 4px;font-weight:400}
/* The staged ending (D-143). Acts arrive one at a time; a click brings the
   rest. Motion is short and only ever upward, so the page never looks like it
   is loading: it looks like somebody laying cards down. */
#revealcard.staged{background:none;border:0;padding:32px 8px 64px;max-width:660px}
#revealcard.staged .act{opacity:0;transform:translateY(14px);
transition:opacity .55s ease,transform .55s cubic-bezier(.2,.8,.2,1);
background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:22px 26px;margin-bottom:14px}
#revealcard.staged .act.in{opacity:1;transform:none}
@media (prefers-reduced-motion:reduce){
  #revealcard.staged .act{transition:opacity .2s linear;transform:none}
}
#revealcard .act h2:first-child{margin-top:0}
/* The verdict is the moment, so it gets the room the rest does not. */
#revealcard .verdict{text-align:center;padding:40px 26px 34px}
#revealcard .verdict .face{width:132px;height:132px;object-fit:cover;
border-radius:50%;filter:grayscale(.5) contrast(1.05);
border:1px solid var(--rule);margin-bottom:18px}
#revealcard .verdict .said{font-family:var(--mono);font-size:10.5px;
letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
#revealcard .verdict h3{font-size:46px;line-height:1.05;margin:0 0 10px}
#revealcard .verdict.right h3{color:var(--warm)}
#revealcard .verdict.wrong h3{color:var(--bad)}
#revealcard .verdict .who{font-size:15px;color:var(--ink);margin-bottom:14px}
#revealcard .verdict .tally{font-family:var(--mono);font-size:10.5px;
letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}
#revealcard .item .tag{display:block;font-family:var(--mono);font-size:9.5px;
letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin-bottom:4px}
#find{width:100%;background:var(--panel2);border:1px solid var(--rule);
border-radius:6px;padding:7px 11px;color:var(--ink);font-family:var(--body);
font-size:13px;margin-bottom:12px}
#find:focus{outline:none;border-color:var(--cool)}
#mynotes{width:100%;background:var(--panel2);border:1px solid var(--rule);
border-radius:6px;padding:10px 12px;color:var(--ink);font-family:var(--body);
font-size:13.5px;line-height:1.55;resize:vertical}
#mynotes:focus{outline:none;border-color:var(--cool)}
.qa .whose{font-family:var(--mono);font-size:9.5px;letter-spacing:.13em;
text-transform:uppercase;color:var(--cool);margin-bottom:4px}
mark{background:var(--warm);color:var(--contrast);border-radius:2px;padding:0 2px}
#reveal textarea{width:100%;background:var(--panel2);border:1px solid var(--rule);
border-radius:7px;padding:11px 13px;color:var(--ink);font-family:var(--body);
font-size:15px;line-height:1.55;resize:vertical}
#reveal textarea:focus{outline:none;border-color:var(--cool)}
#hours{display:flex;gap:5px;flex-wrap:wrap;margin:2px 0 6px}
.hr{background:none;border:1px solid var(--rule);border-radius:6px;
padding:4px 9px;color:var(--muted);font-family:var(--mono);font-size:10.5px;
letter-spacing:.04em;cursor:pointer}
.hr:hover{color:var(--ink);border-color:var(--muted)}
.hr.on{color:var(--ink);border-color:var(--cool);background:var(--panel2)}
#plan{width:100%;height:auto;display:block;margin:0;overflow:visible}
/* Rooms share walls, so a door is a break in the wall: a short segment drawn
   over it, thicker than the wall itself (D-134). `.far` is the honest exception,
   a door the lattice could not give a shared wall to. */
#plan .door{stroke:var(--cool);stroke-width:5;stroke-linecap:butt;opacity:.9}
#plan .door.far{stroke-width:2;opacity:.45;stroke-dasharray:4 4}
#plan .room rect{fill:var(--panel2);stroke:var(--rule);stroke-width:1.5}
#plan .room.clickable rect{cursor:pointer}
#plan .room.seen rect{stroke:var(--muted)}
/* Inside the room, top left, the way a name is written on a plan (D-134). */
#plan text.rn{fill:var(--muted);font-family:var(--mono);font-size:9px;
letter-spacing:.06em;text-anchor:start;text-transform:uppercase}
#plan .room.seen text.rn{fill:var(--ink)}
#plan text.who{fill:var(--ink);font-family:var(--mono);font-size:11px;
font-weight:600;text-anchor:middle}
#plan text.who.bad{fill:var(--bad)}
#plan text.who.dead{fill:var(--muted)}
#plan text.who.firm{text-decoration:underline}
#plan .room.clickable{cursor:pointer}
#plan .room.clickable:hover rect{stroke:var(--warm)}
#plan .room.clickable:hover text.rn{fill:var(--warm)}
/* Reading size (D-091). Three steps, applied to the text people actually read
   for an hour rather than to the whole page: scaling everything moves the
   portrait and the layout, and the complaint was legibility, not zoom. */
body.big #said{font-size:19px;line-height:1.66}
body.big #said .asked{font-size:15px}
body.big .item{font-size:14px;line-height:1.55}
body.big table{font-size:13.5px}
body.big #book{font-size:14px}
body.big .thing{font-size:13.5px}
body.huge #said{font-size:22px;line-height:1.7}
body.huge #said .asked{font-size:17px}
body.huge .item{font-size:16px;line-height:1.6}
body.huge table{font-size:15px}
body.huge #book{font-size:16px}
body.huge .thing{font-size:15px}
body.huge #nameplate{font-size:26px}
/* The things you are carrying (D-087). A row under the cast, empty until the
   first secret with an object behind it surfaces, so it costs nothing visually
   in a case that has none. */
#hand{display:flex;gap:7px;flex-wrap:wrap;width:100%;align-items:center;
padding-top:10px;border-top:1px solid var(--rule);margin-top:2px}
#hand.gone{display:none}
#hand .label{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted)}
.thing{background:var(--panel2);border:1px solid var(--rule);border-radius:7px;
padding:5px 10px;font-size:12px;cursor:pointer;color:var(--ink);
font-family:var(--display);display:flex;align-items:center;gap:8px}
.thing:hover{border-color:var(--cool)}
.thing small{font-family:var(--mono);font-size:9px;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted)}
.thing i{font-style:italic;font-size:11px;color:var(--muted);white-space:nowrap}
.thing.spent{opacity:.45;cursor:default}
.thing.spent:hover{border-color:var(--rule)}
</style></head><body>
<div id="scene">
  <div id="backdrop"></div><div id="backdrop2"></div><div id="shade"></div>
  <div id="where"></div>
  <div id="top">
    <h1 id="title">…</h1><span class="sub" id="sub"></span>
    <div class="right">
      <span class="badge" id="count">0 questions</span>
      <button id="briefagain" title="What you were told when you arrived">Briefing</button>
      <button id="mute">Sound on</button>
      <button id="textsize" title="Reading size">A</button>
      <button id="booktoggle">Notebook</button>
    </div>
  </div>
  <div id="stage"><svg id="portrait" viewBox="0 0 200 250"></svg>
    <img id="photo" alt=""></div>
  <div id="box">
    <div id="nameplate">—</div>
    <div id="said" class="empty">Pick someone below and ask them something.</div>
  </div>
  <div id="bar">
    <div id="cast"></div>
    <input id="q" placeholder="Ask a question" autocomplete="off">
    <button class="accuse" id="accusebtn">Accuse</button>
    <div id="hand" class="gone"></div>
  </div>
</div>
<div id="grip" title="Drag to resize, double-click to reset"></div>
<aside id="book"><div id="pages"></div></aside>
<div id="brief"><div class="card" id="briefcard"></div></div>
<div id="reveal"><div class="card" id="revealcard"></div></div>
<script>
const $=i=>document.getElementById(i);
let S=null,who=null,busy=false,typer=null,sound=true,lastConflicts=0;
let tab='book',NB={grid:[],conflicts:[],holes:[],unasked:[],logs:{},timeline:{},
  missing:{},tags:[],found:[],held:[],shown:{},people:[]};
// Whose page the notebook is showing (D-135). Not the same as `who`: you read
// one person's page while talking to another, which is most of the game.
let page=null;

/* ---------- procedural portraits -------------------------------------- */
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);
h=Math.imul(h,16777619)}return Math.abs(h)}
const SKIN=['#f0cdb0','#e3b492','#c99070','#a9714f','#8a5638','#f5d9c4','#d9a684','#6f4630'];
const HAIR=['#241c18','#4a3527','#7a5638','#b08046','#2b2b33','#5d5049','#8f8f97','#3a2230'];
const CLOTH=['#2c3550','#3a2f3f','#204040','#463526','#332f45','#1f3a34','#4a2c2c','#2a3b4a'];
const ACCENT=['#7fa9ee','#d9a24e','#9d8ce0','#6fbfa8','#e08b7a','#c0a06a','#7fc0d9','#c98fb0'];

function portraitSVG(id,look,gender){
  /* `look` is a sentence the generator wrote. Reading a man/woman cue out of it
     stops the drawn faces being a coin flip, which players noticed. */
  const l=(look||'').toLowerCase();
  const fem=(gender||'').toLowerCase().startsWith('w')||
    (!gender&&/\b(woman|women|she|her|lady|girl|mrs|ms|miss)\b/.test(l));
  const masc=/\b(man|men|he|his|him|gentleman|boy|mr)\b/.test(l);
  const h=hash(id)+(fem?7:masc?3:0);
  const skin=SKIN[h%8],hair=HAIR[(h>>3)%8],cloth=CLOTH[(h>>6)%8],accent=ACCENT[(h>>9)%8];
  const pool=fem?[1,2,3,5]:masc?[0,4,0,4]:[0,1,2,3,4,5];
  const style=pool[(h>>12)%pool.length], glasses=((h>>15)%4)===0,
        collar=((h>>17)%3)===0;
  const uid=id.replace(/[^a-z0-9]/gi,'');
  const hairs=[
    `<path d="M56 96C56 58 74 40 100 40s44 18 44 56c0-22-14-30-44-30S56 74 56 96Z" fill="${hair}"/>`,
    `<path d="M54 100C50 56 72 36 100 36s50 20 46 64c-4-30-10-40-24-44-10 16-40 12-48 4-8 8-14 18-20 40Z" fill="${hair}"/>`,
    `<path d="M56 92c0-40 20-56 44-56s44 16 44 56c-6-26-18-34-44-34S62 66 56 92Z" fill="${hair}"/><path d="M52 92c-6 30-2 54 4 66-14-24-16-52-4-66Z" fill="${hair}"/><path d="M148 92c6 30 2 54-4 66 14-24 16-52 4-66Z" fill="${hair}"/>`,
    `<path d="M58 88c2-34 20-52 42-52s40 18 42 52c-8-20-16-28-42-28S66 68 58 88Z" fill="${hair}"/><ellipse cx="100" cy="34" rx="16" ry="10" fill="${hair}"/>`,
    `<path d="M60 84c4-30 20-48 40-48s36 18 40 48c-10-14-22-20-40-20s-30 6-40 20Z" fill="${hair}"/>`,
    `<path d="M56 98C54 58 74 38 100 38s46 20 44 60c-4-24-8-36-20-42-6 14-32 16-46 6-10 6-18 16-22 36Z" fill="${hair}"/><path d="M46 98c-6 34 0 62 8 74-18-26-20-58-8-74Z" fill="${hair}"/>`];
  return `
  <defs>
    <linearGradient id="g${uid}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${accent}" stop-opacity=".22"/>
      <stop offset="1" stop-color="${accent}" stop-opacity="0"/>
    </linearGradient>
  </defs>
  <rect x="0" y="0" width="200" height="250" rx="12" fill="url(#g${uid})"/>
  <path d="M18 250c4-46 32-66 82-66s78 20 82 66Z" fill="${cloth}"/>
  ${collar?`<path d="M78 188l22 22 22-22 10 6-32 32-32-32Z" fill="${accent}" opacity=".85"/>`:''}
  <rect x="88" y="150" width="24" height="36" rx="10" fill="${skin}"/>
  <ellipse cx="58" cy="112" rx="7" ry="10" fill="${skin}"/>
  <ellipse cx="142" cy="112" rx="7" ry="10" fill="${skin}"/>
  <ellipse cx="100" cy="108" rx="44" ry="52" fill="${skin}"/>
  ${hairs[style]}
  <ellipse class="eye" cx="84" cy="110" rx="4.6" ry="5" fill="#191b22"/>
  <ellipse class="eye" cx="116" cy="110" rx="4.6" ry="5" fill="#191b22"/>
  <path d="M76 98c5-3 12-3 16-1" stroke="#191b22" stroke-width="2.4" fill="none" stroke-linecap="round" opacity=".75"/>
  <path d="M108 97c5-2 12-2 16 1" stroke="#191b22" stroke-width="2.4" fill="none" stroke-linecap="round" opacity=".75"/>
  ${glasses?`<g stroke="#20242e" stroke-width="2.6" fill="none" opacity=".9">
    <rect x="70" y="101" width="27" height="19" rx="8"/><rect x="103" y="101" width="27" height="19" rx="8"/>
    <path d="M97 110h6"/></g>`:''}
  <ellipse id="mouth" cx="100" cy="136" rx="9" ry="2.6" fill="#5c3b3b"/>`;
}

/* ---------- the blip --------------------------------------------------- */
let actx=null;
function blip(pitch){
  if(!sound)return;
  try{
    actx=actx||new (window.AudioContext||window.webkitAudioContext)();
    const o=actx.createOscillator(),g=actx.createGain();
    o.type='square';
    o.frequency.value=pitch*(0.97+Math.random()*0.06);
    g.gain.setValueAtTime(0.045,actx.currentTime);
    g.gain.exponentialRampToValueAtTime(0.0008,actx.currentTime+0.045);
    o.connect(g);g.connect(actx.destination);
    o.start();o.stop(actx.currentTime+0.05);
  }catch(e){}
}
function chime(){
  if(!sound)return;
  try{
    actx=actx||new (window.AudioContext||window.webkitAudioContext)();
    [740,988].forEach((f,i)=>{
      const o=actx.createOscillator(),g=actx.createGain();
      o.type='triangle';o.frequency.value=f;
      const t=actx.currentTime+i*0.09;
      g.gain.setValueAtTime(0.07,t);
      g.gain.exponentialRampToValueAtTime(0.0008,t+0.4);
      o.connect(g);g.connect(actx.destination);o.start(t);o.stop(t+0.42);
    });
  }catch(e){}
}

/* ---------- typewriter -------------------------------------------------
   Fed by a queue rather than by a finished string (D-142). The model's words
   arrive over a stream, so the box drains whatever it has been given and waits
   for more, instead of waiting for all of it and then pretending to type.

   The drain rate floats. At a steady rate the box either falls behind a fast
   answer and is still typing a minute after the model finished, or runs dry
   between chunks and stutters. So it aims to empty in about a second: a long
   backlog is spent faster, a short one slower, and the reading speed stays
   somewhere a person can follow. */
let pending='', streaming=false, mouth=null;

function openSay(asked){
  const el=$('said');el.className='';
  if(typer)clearInterval(typer);
  pending='';streaming=true;
  mouth=document.getElementById('mouth');
  el.innerHTML=(asked?'<span class="asked">\u201c'+esc(asked)+'\u201d</span>':'')+
    '<span class="body"></span><span class="cursor"></span>';
  return el.querySelector('.body');
}

function runSay(body,pitch){
  let n=0;
  typer=setInterval(()=>{
    if(!pending.length){
      if(!streaming)return;              // waiting on the model, keep the cursor
      return closeIfDone();
    }
    // Somewhere between 8ms and 34ms a character, so the backlog clears in
    // about a second however big it is.
    const take=Math.max(1,Math.round(pending.length/40));
    const chunk=pending.slice(0,take);pending=pending.slice(take);
    body.textContent+=chunk;n+=chunk.length;
    if(mouth)mouth.setAttribute('ry',(n%3===0)?'5.5':'2.6');
    if(/[a-z0-9]/i.test(chunk[0])&&n%2===0)blip(pitch);
    closeIfDone();
  },17);
  function closeIfDone(){
    if(streaming||pending.length)return;
    clearInterval(typer);typer=null;
    $('said').querySelector('.cursor')?.remove();
    if(mouth)mouth.setAttribute('ry','2.6');
  }
  $('said')._finish=()=>{
    body.textContent+=pending;pending='';streaming=false;closeIfDone();
  };
}

/* If the player has clicked to skip the typing, the queue is closed and the
   rest of the stream goes straight onto the screen. */
function pushSay(text){
  if(typer){pending+=text;return}
  const body=$('said')?.querySelector('.body');
  if(body)body.textContent+=text;
}
function endSay(){streaming=false}

/* The whole answer at once: a recall, a fallback, anything not streamed. */
function say(text,pitch,asked){
  const body=openSay(asked);
  runSay(body,pitch);
  pushSay(text);endSay();
}

document.addEventListener('click',e=>{
  if(typer&&!e.target.closest('#bar,#book,#reveal,#top'))$('said')._finish()});

/* ---------- the panel edge (D-098) -------------------------------------- */
/* Width lives in a CSS variable, so the drag sets one property and the panel and
   the shifted stage both follow it. Clamped: too narrow and the timeline
   columns wrap into nonsense, too wide and there is no game left to look at. */
const BOOK_MIN=300,BOOK_MAX=880,BOOK_DEFAULT=430;

function setBook(px){
  const wide=Math.max(BOOK_MIN,Math.min(BOOK_MAX,Math.round(px)));
  document.documentElement.style.setProperty('--book',wide+'px');
  return wide;
}

function grabEdge(){
  const grip=$('grip');
  if(!grip)return;
  grip.addEventListener('pointerdown',e=>{
    e.preventDefault();
    grip.setPointerCapture(e.pointerId);
    document.body.classList.add('dragging');
    const move=ev=>setBook(window.innerWidth-ev.clientX);
    const done=ev=>{
      grip.releasePointerCapture(e.pointerId);
      document.body.classList.remove('dragging');
      grip.removeEventListener('pointermove',move);
      grip.removeEventListener('pointerup',done);
      grip.removeEventListener('pointercancel',done);
      save('book',String(setBook(window.innerWidth-ev.clientX)));
    };
    grip.addEventListener('pointermove',move);
    grip.addEventListener('pointerup',done);
    grip.addEventListener('pointercancel',done);
  });
  // The way back, for anyone who has dragged it somewhere silly.
  grip.addEventListener('dblclick',()=>save('book',String(setBook(BOOK_DEFAULT))));
}

/* ---------- reading size ----------------------------------------------- */
/* Served from the player's own machine, so browser storage is the right place
   for a per-person preference: it survives a restart and belongs to nobody
   else. Wrapped, because a browser set to refuse site data throws here. */
let size='',atSlot='',find='';
function save(k,v){try{localStorage.setItem('mystery.'+k,v)}catch(e){}}
function load(k){try{return localStorage.getItem('mystery.'+k)}catch(e){return null}}
function setSize(v){
  size=(v==='big'||v==='huge')?v:'';
  document.body.className=size;
  $('textsize').textContent={'':'A',big:'A+',huge:'A++'}[size];
}

/* ---------- app -------------------------------------------------------- */
function pitchOf(id){return 300+(hash(id)%9)*46}
function nameOf(id){const s=S.suspects.find(x=>x.id===id);return s?s.name:id}

function showPortrait(id){
  const s=S.suspects.find(x=>x.id===id);
  const svg=$('portrait'),img=$('photo');
  svg.classList.add('enter');img.classList.add('enter');
  setTimeout(()=>{
    if(s&&s.portrait){
      img.src=s.portrait;img.style.display='block';svg.style.display='none';
      img.classList.remove('enter');
    }else{
      svg.innerHTML=portraitSVG(id,s?s.look:'',s?s.gender:'');
      svg.style.display='block';img.style.display='none';
      svg.classList.remove('enter');
    }
  },60);
}

/* The box under the portrait belongs to whoever is in the portrait. Recall
   what *this* person last said, not whatever was on screen a moment ago: the
   whole game is who said what, and leaving one suspect's words under another
   one's face is the game lying to the player. */
function recall(id){
  const el=$('said');
  if(typer){clearInterval(typer);typer=null}
  const log=(NB.logs||{})[id]||[];
  if(!log.length){
    el.className='empty';
    el.textContent='You have not asked '+nameOf(id).split(' ')[0]+' anything yet.';
    return;
  }
  const last=log[log.length-1];
  el.className='';
  // Said before, not being said now, so no typewriter. The question comes with
  // it, because an answer read cold an hour later needs to know what it answers.
  // The count points at the Transcript tab, which holds the rest of it.
  const earlier=log.length>1
    ?'<em>'+(log.length-1)+' earlier</em>':'';
  el.innerHTML='<span class="asked">“'+esc(last.q)+'”'+earlier+'</span>'+
    '<span class="body">'+esc(last.a)+'</span>';
}

/* The things you are carrying, and whether the person in front of you has
   already been made to look at each one (D-087). Redrawn on every answer and on
   every switch, because both change what this row should say. */
function paintHand(){
  const row=$('hand'),held=(NB.held||[]);
  if(!held.length){row.className='gone';row.innerHTML='';return}
  row.className='';
  const seen=new Set(((NB.shown||{})[who])||[]);
  const to=who?nameOf(who).split(' ')[0]:'';
  row.innerHTML='<span class="label">You have</span>'+held.map(h=>{
    const done=seen.has(h.id);
    // Where it came from was in this payload from the day the hand existed and
    // was never drawn (D-112). Without it there is no cue that showing a thing
    // to somebody other than its owner is the move, which is where the whole
    // second half of a case lives.
    const src=h.from?esc(h.from.split(' ')[0]):'';
    // Where it came from, and nothing else. An earlier version footed every card
    // with "SHOW MARGIT" and "GIVE IT BACK TO SANNE", which is the game telling
    // you the move rather than letting you find it: the provenance is the clue,
    // the imperative was a walkthrough (D-112). What stays is the one thing that
    // is memory rather than hint: whether this person has already seen it.
    return '<button class="thing'+(done?' spent':'')+'" data-ev="'+esc(h.id)+'"'+
      (done?' disabled':'')+' title="'+esc(h.name)+(src?' — from '+src:'')+'">'+
      esc(h.name)+(src?'<i>from '+src+'</i>':'')+
      (done?'<small>'+to+' has seen it</small>':'')+'</button>';
  }).join('');
  row.querySelectorAll('.thing:not(.spent)').forEach(b=>{
    b.onclick=()=>produce(b.dataset.ev);
  });
}

async function produce(evidence){
  if(busy||!who)return;
  busy=true;
  const name=(NB.held||[]).find(h=>h.id===evidence);
  try{
    const r=await (await fetch('/show',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({who:who,evidence:evidence})})).json();
    paintBook(r.notebook);
    if(r.opened){
      // Not a line of dialogue: nobody has said anything yet. It is the table
      // state changing, and the next question is the one that lands.
      $('said').className='';
      $('said').innerHTML='<span class="asked">You put '+esc(name?name.name:'it')+
        ' in front of '+esc(nameOf(who))+'.</span>'+
        '<span class="body">They look at it. Ask them.</span>';
      $('q').focus();
    }
  }catch(e){}
  busy=false;
}

function select(id){
  who=id;
  document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c.dataset.id===id));
  showPortrait(id);
  const s=S.suspects.find(x=>x.id===id);
  $('nameplate').innerHTML=esc(s.name)+(s.role?'<small>'+esc(s.role)+'</small>':'');
  recall(id);
  paintHand();
  $('q').focus();
}


/* ---------- the briefing ------------------------------------------------
   What a person arriving at this house would already have been told, in one
   place, before they start asking (D-126). All of it was in `/state` already
   and the page was dribbling it into a one-line subtitle: who you are, who
   found the body and where, and the handful of facts the whole household
   shares. A player was reconstructing from five people what everybody in the
   building could have told them at the door.

   Not a tutorial and not a hint. Nothing here is a secret, nothing here is
   evidence, and the suspects have had every word of it from the beginning. */
function paintBrief(){
  const d=S.discovery, you=S.you;
  /* Place names arrive as they are written on the plan, and about half of them
     already start with "the". */
  const at=n=>String(n||'').replace(/^[Tt]he\\s+/,'');
  const roster=S.suspects.map(s=>
    '<b>'+esc(s.name)+'</b><span>'+esc(s.role||'')+'</span>').join('');
  const common=(S.common||[]).map(c=>'<li>'+esc(c)+'</li>').join('');
  /* The cover (D-144). The establishing shot has been generated for every case
     since D-069 and was only ever used as a backdrop behind the interface, at
     ten per cent opacity under a vignette. Here it gets to be a picture: the
     case named over it in display type, the occasion under that, and the cast
     lined up below, which is the shape every mystery paperback has had for a
     hundred years and the first thing a player sees. */
  const faces=S.suspects.map(x=>
    '<span class="mug" title="'+esc(x.name)+'">'+
    (x.portrait?'<img src="'+esc(x.portrait)+'" alt="">'
      :'<svg viewBox="0 0 200 250">'+portraitSVG(x.id,x.look,x.gender)+'</svg>')+
    '<em>'+esc(x.name.split(' ')[0])+'</em></span>').join('');

  $('briefcard').innerHTML=
    '<div class="cover'+(S.scene?'':' bare')+'"'+
    (S.scene?' style="background-image:url('+esc(S.scene)+')"':'')+
    '><div class="coverink"><h2>'+esc(S.title)+'</h2>'+
    (S.occasion?'<div class="where">'+esc(S.occasion)+'</div>':'')+
    '</div></div>'+
    '<div class="faces">'+faces+'</div>'+
    (you&&you.role?'<h4>You</h4><p>'+esc(you.role.replace(/\\.$/,''))+'.</p>'+
      (you.why?'<p>'+esc(you.why)+'</p>':'')+
      (you.standing?'<p>'+esc(you.standing)+'</p>':''):'')+
    (S.commission?'<h4>What you were asked for</h4><p>'+esc(S.commission)+'</p>':'')+
    '<h4>What happened</h4>'+
    (d?'<p><b>'+esc(S.victim)+'</b> is dead. '+esc(d.finder)+' found the body in the '+
        esc(at(d.place))+'.</p><p>'+esc(d.summary)+'</p>'
      :'<p><b>'+esc(S.victim)+'</b> is dead, and one of the people here did it.</p>')+
    '<p>You arrived after that. You saw none of it, and everything you are about '+
    'to be told, you are being told.</p>'+
    (S.notebook&&S.notebook.budget
      ?'<p class="clock">The police are on the road. You have about <b>'+
        S.notebook.budget+'</b> questions before they are at the door.</p>':'')+
    '<h4>Who is here</h4><div class="roster">'+roster+'</div>'+
    (common?'<h4>What everybody knows</h4><ul>'+common+'</ul>':'')+
    '<button class="go" id="briefgo">Begin</button>';
  $('briefgo').onclick=()=>{$('brief').classList.remove('on');save('briefed',S.title)};
}
function showBrief(){paintBrief();$('brief').classList.add('on')}

async function boot(){
  S=await (await fetch('/state')).json();
  if(S.scene)showScene(S.scene,'');
  $('title').textContent=S.title;
  /* The player's own position, stated (D-100). It is load-bearing now: the
     suspects talk to each other and watch how you go about this, and none of
     that makes sense if you might be the police. */
  $('sub').textContent=(S.discovery
    ? S.victim+' is dead. '+S.discovery.finder+' found the body in the '+
      S.discovery.place+'.'
    : S.victim+' is dead. One of them did it.')+
    (S.you&&S.you.role?' You are '+S.you.role.replace(/^(An?|The) /i,
      m=>m.toLowerCase()).replace(/\\.$/,'')+'.':'')+
    ' The police are on their way and you are not the police.';

  const cast=$('cast');
  S.suspects.forEach(s=>{
    const b=document.createElement('button');
    b.className='chip';b.dataset.id=s.id;b.title=s.role||'';
    b.innerHTML=(s.portrait
      ?'<img src="'+s.portrait+'" style="width:30px;height:36px;border-radius:5px;'+
       'object-fit:cover;display:block">'
      :'<svg viewBox="0 0 200 250">'+portraitSVG(s.id,s.look,s.gender)+'</svg>')+'<span>'+
      esc(s.name.split(' ')[0])+'</span>';
    b.onclick=()=>select(s.id);
    cast.appendChild(b);
  });
  $('q').onkeydown=e=>{if(e.key==='Enter')send()};
  $('mute').onclick=()=>{sound=!sound;$('mute').textContent=sound?'Sound on':'Sound off'};
  setSize(load('size')||'');
  setBook(parseInt(load('book'),10)||BOOK_DEFAULT);
  grabEdge();
  $('textsize').onclick=()=>{
    const next={'':'big',big:'huge',huge:''}[size];
    setSize(next);save('size',next);
  };
  $('booktoggle').onclick=()=>{
    const open=$('book').classList.toggle('open');
    $('scene').classList.toggle('shifted',open);
    $('grip').classList.toggle('on',open);
  };
  $('accusebtn').onclick=()=>who&&accuse(who);
  $('briefagain').onclick=showBrief;
  paintBook(S.notebook);
  select(S.suspects[0].id);
  /* Shown once per case rather than once ever: a different evening is a
     different briefing, and a returning player mid-case does not want it
     again. */
  if(load('briefed')!==S.title)showBrief();
}

async function send(){
  const inp=$('q'),text=inp.value.trim();
  if(!text||busy||!who)return;
  busy=true;inp.value='';
  const asked=who;
  // The question lands before the answer does, so the box is already this
  // person's while they think about it. The cursor sits there until the first
  // words arrive, which is what a person waiting looks like (D-142).
  const body=openSay(text);
  runSay(body,pitchOf(asked));
  let heardAny=false;
  try{
    const res=await fetch('/ask/live',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({who:asked,text:text})});
    if(!res.ok||!res.body)throw new Error('no stream');
    const reader=res.body.getReader(),dec=new TextDecoder();
    let buf='',tail=null;
    while(true){
      const {value,done}=await reader.read();
      if(done)break;
      buf+=dec.decode(value,{stream:true});
      // Server-sent events: blank-line separated, one `data:` line each.
      let cut;
      while((cut=buf.indexOf('\\n\\n'))>=0){
        const line=buf.slice(0,cut).replace(/^data: ?/,'');
        buf=buf.slice(cut+2);
        if(!line)continue;
        const ev=JSON.parse(line);
        if(ev.text){pushSay(ev.text);heardAny=true}
        if(ev.failed)throw new Error('stream failed');
        if(ev.over||ev.done)tail=ev;
      }
    }
    endSay();
    if(tail&&tail.over){
      /* The server refused it, so nothing was asked and no model was called.
         The accusation is still open: the evening ends, the case does not. */
      $('said').innerHTML='<span class="asked">\u201c'+esc(text)+'\u201d</span>'+
        '<span class="body">You do not get to ask it. There are cars on the '+
        'gravel and somebody is already at the door. Whatever you think you '+
        'know, you know it now.</span>';
      paintBook(tail.notebook);
      busy=false;return;
    }
    if(tail){
      const before=lastConflicts;
      paintBook(tail.notebook);
      if(tail.notebook.conflicts.length>before){
        chime();
        ['portrait','photo'].forEach(k=>{$(k).classList.add('rattled');
          setTimeout(()=>$(k).classList.remove('rattled'),520)});
      }
    }
  }catch(e){
    // A stream can die for reasons that have nothing to do with the model, and
    // an evening should not end because a proxy buffered something. The plain
    // route is still there and still records the statement.
    //
    // Only when nothing was heard, though. Once words have arrived the server
    // has already called the model and is going to record the statement, so
    // asking again would charge for the same question twice and put it in the
    // transcript twice. A missing notebook refresh is the cheaper failure.
    endSay();
    if(heardAny){busy=false;inp.focus();return}
    try{
      const r=await (await fetch('/ask',{method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({who:asked,text:text})})).json();
      say(r.speech||'(no answer came back)',pitchOf(asked),text);
      if(r.notebook)paintBook(r.notebook);
    }catch(e2){say('(no answer came back)',pitchOf(asked),text)}
  }
  busy=false;inp.focus();
}

function paintBook(n){
  NB=n;lastConflicts=n.conflicts.length;
  /* A clock, not a tally (D-128). A number that only goes up is a score; a
     number that goes down makes every question a decision. */
  const left=(n.left==null?null:n.left);
  $('count').innerHTML=
    (left==null?n.questions+(n.questions===1?' question':' questions')
      :(left>0?left+' question'+(left===1?'':'s')+' left':'The police are here'))+
    (n.conflicts.length?' \u00b7 <b>'+n.conflicts.length+' contradiction'+
      (n.conflicts.length>1?'s':'')+'</b>':'');
  $('count').classList.toggle('late',!!n.late && !n.over);
  $('count').classList.toggle('spent',!!n.over);
  if(n.over){
    $('q').disabled=true;
    $('q').placeholder='The police are here. You can still name somebody.';
  }
  paintHand();
  render();
}

function render(){
  const n=NB;
  let h='<div id="tabs">'+
    [['book','Notebook'],['log','Transcript'],['map','Map']].map(([k,l])=>
      '<button data-tab="'+k+'" class="'+(tab===k?'on':'')+'">'+l+'</button>').join('')+
    '</div>';
  if(tab==='book')h+=viewBook(n);
  if(tab==='log')h+=viewLog(n);
  if(tab==='map')h+=viewMap(n);
  $('pages').innerHTML=h;
  document.querySelectorAll('#tabs button').forEach(b=>
    b.onclick=()=>{tab=b.dataset.tab;render()});
  document.querySelectorAll('th.rm.clickable,#plan .room.clickable').forEach(b=>
    b.onclick=()=>showScene(b.dataset.scene,b.dataset.room));
  document.querySelectorAll('#hours .hr').forEach(b=>
    b.onclick=()=>{atSlot=b.dataset.slot;render()});
  document.querySelectorAll('#dossiers .dt').forEach(b=>
    b.onclick=()=>{page=b.dataset.who;render()});
  const box=$('find');
  if(box){
    // Re-rendered on every keystroke would lose the caret, so the field keeps
    // its own state and only the rows below it are redrawn.
    box.oninput=()=>{find=box.value;const at=box.selectionStart;render();
      const again=$('find');if(again){again.focus();again.setSelectionRange(at,at)}};
  }
  // The notes box now lives on whichever person's page is open, which is not
  // always the person being questioned (D-135), so it carries its own subject.
  const mine=$('mynotes');
  if(mine)mine.oninput=()=>save(noteKey(mine.dataset.who||who),mine.value);
}

/* The notebook, built around the person rather than the grid (D-135).

   It used to open with a table of every claim anybody had made, which is the
   axis the case is deliberately least decided by, and the two other axes we
   added — where a thing was, what somebody says happened in a room — had
   nowhere at all to be read. A player was handed a spreadsheet and told the
   answer was not in the spreadsheet.

   So: one page per suspect, and the page answers the four questions a player
   actually holds in their head. What have they admitted. What has anybody else
   said about them. What have they said about everybody else. What will they not
   say. The evening's grid is still there, one row deep, on the page of the
   person whose evening it is. */
function viewBook(n){
  let h='';
  /* Who you are, kept where you can reread it (D-101). It is the answer to
     "why is anybody telling me anything", and the player is entitled to it. */
  if(S.you)h+='<h2>You</h2><div class="item soft">'+esc(S.you.role)+
    (S.you.why?'<br><span class="empty">'+esc(S.you.why)+'</span>':'')+
    (S.you.standing?'<br><span class="empty">'+esc(S.you.standing)+'</span>':'')+
    '</div>';

  const people=(n.people||[]).filter(p=>!p.dead);
  if(!people.length)return h+'<div class="empty">Nothing established yet.</div>';
  if(!people.some(p=>p.id===page))page=(people.find(p=>p.id===who)||people[0]).id;

  // Who the page is about. The tab carries what has been asked of them, which
  // is the one number that tells you where you have not been looking.
  h+='<div id="dossiers">'+people.map(p=>
    '<button class="dt'+(p.id===page?' on':'')+'" data-who="'+esc(p.id)+'">'+
    esc(p.name.split(' ')[0])+'<span>'+p.asked+'</span></button>').join('')+'</div>';

  const p=people.find(x=>x.id===page);
  const mine=(n.conflicts||[]).filter(c=>(c.who||[]).includes(p.id));
  // On their own page "their own word" is in every row, so it is not in any.
  const rows=(r,src)=>'<table>'+r.map(x=>'<tr class="'+(x.odd?'disputed':'')+
    '"><td>'+esc(x.time)+'</td><td>'+esc(x.place)+'</td>'+
    (src?'<td>'+esc(x.who)+'</td>':'')+'</tr>').join('')+'</table>';
  const none=t=>'<div class="empty">'+t+'</div>';

  h+='<div class="dossier"><h3>'+esc(p.name)+'</h3>'+
    (p.role?'<div class="who-is">'+esc(p.role)+'</div>':'');

  h+='<h4>What they admit</h4>';
  h+=p.own.length?rows(p.own,false)
    :none('They have not put themselves anywhere yet.');
  if(p.admits.length)h+=p.admits.map(a=>'<div class="item'+(a.mine?'':' soft')+'">'+
    esc(a.text)+'<br><span class="empty">'+
    (a.mine?'they told you':esc(a.from)+' told you')+'</span></div>').join('');

  h+='<h4>What others say about them</h4>';
  h+=p.heard.length?rows(p.heard,true)
    :none('Nobody else has placed them anywhere.');
  if(p.about.length)h+=p.about.map(a=>'<div class="item soft">'+esc(a.text)+
    '<br><span class="empty">from '+esc(a.from)+'</span></div>').join('');

  h+='<h4>What they say about everyone else</h4>';
  h+=p.told.length?rows(p.told,true)
    :none('They have not placed anybody but themselves.');

  if(mine.length)h+='<h4>Where it does not add up</h4>'+mine.map(c=>
    '<div class="item hard">'+esc(c.text)+'<br><span class="empty">'+esc(c.kind)+
    '</span></div>').join('');

  // Two ways a lead touches a page. On the page of the person whose story it
  // is, it is a gap in their account. On the page of the person who could
  // settle it, it is a question you have not asked yet.
  const open=(n.holes||[]).filter(x=>x.of===p.id||x.ask===p.id);
  const ask=(n.unasked||[]).filter(x=>x.of===p.id||x.ask===p.id);
  if(p.refused)h+='<div class="item cold">Refused to answer '+p.refused+
    (p.refused===1?' time':' times')+'</div>';
  if(open.length)h+='<h4>Accounts that do not line up</h4>'+open.map(x=>
    '<div class="item soft">'+esc(x.text)+'</div>').join('');
  if(ask.length)h+='<h4>'+(ask.some(x=>x.ask===p.id)?'Worth asking them':
    'Nobody has confirmed this')+'</h4>'+ask.map(x=>
    '<div class="item cold">'+esc(x.text)+'</div>').join('');

  h+='<h4>Your notes</h4><textarea id="mynotes" data-who="'+esc(p.id)+
    '" rows="4" placeholder="What you make of them, what to come back to'+
    '\u2026">'+esc(noteFor(p.id))+'</textarea>';
  return h+'</div>';
}

/* The transcript, searchable, and across everybody rather than one person
   (D-106). Forty answers in, "who mentioned the gearbox" is a real question and
   scrolling five separate logs is not an answer to it. With no search it stays
   what it was: this person, in order. */
function viewLog(n){
  const logs=n.logs||{}, term=find.trim().toLowerCase();
  let h='<h2>'+(term?'Everything anybody said about it':
    'Everything '+esc(nameOf(who))+' has said')+'</h2>'+
    '<input id="find" placeholder="Search the transcript" value="'+esc(find)+'">';

  const rows=[];
  Object.keys(logs).forEach(id=>{
    if(!term&&id!==who)return;
    (logs[id]||[]).forEach(x=>{
      if(term&&!(x.q+' '+x.a).toLowerCase().includes(term))return;
      rows.push({id:id,q:x.q,a:x.a});
    });
  });

  if(!rows.length)h+='<div class="empty">'+(term?'Nothing matches that.':
    'You have not asked them anything yet.')+'</div>';
  else h+=rows.map(r=>'<div class="qa">'+
    (term?'<div class="whose">'+esc(nameOf(r.id))+'</div>':'')+
    '<div class="qq">'+mark(r.q,term)+'</div>'+
    '<div class="aa">'+mark(r.a,term)+'</div></div>').join('');

  return h+notes();
}

function mark(text,term){
  if(!term)return esc(text);
  const at=text.toLowerCase().indexOf(term);
  if(at<0)return esc(text);
  return esc(text.slice(0,at))+'<mark>'+esc(text.slice(at,at+term.length))+
    '</mark>'+mark(text.slice(at+term.length),term);
}

/* Somewhere to write down what you think, per person, kept in this browser
   (D-106). The notebook records what was said; this is the other half, which is
   what you made of it. */
function notes(){
  if(!who)return '';
  return '<h2>Your notes on '+esc(nameOf(who).split(' ')[0])+'</h2>'+
    '<textarea id="mynotes" data-who="'+esc(who)+'" rows="5" placeholder="What '+
    'you make of them, what to come back to\u2026">'+esc(noteFor(who))+'</textarea>';
}

function noteKey(id){return 'note.'+(S.title||'case')+'.'+id}
function noteFor(id){return load(noteKey(id))||''}

/* The floor plan, with the evening running through it (D-096).
   One moment at a time: pick an hour and the rooms fill with whoever has been
   placed in them. The plan on its own was a picture of a building, which is not
   a question anybody was asking. The question is "where was everyone at nine",
   and that needs the two halves in one picture.

   Rooms are drawn as rooms rather than dots: a box you can put people in. The
   layout is a depth-first walk of the plan arranged round an ellipse, so
   connected rooms end up near each other and the picture does not rearrange
   itself between renders. */
function plan(n){
  const P=S.places||[];
  if(!P.some(p=>(p.adjacent||[]).length))return '';

  const times=S.times||[];
  if(!times.length)return '';
  if(!times.some(t=>t.id===atSlot))atSlot=times[0].id;

  const by={};P.forEach(p=>by[p.id]=p);
  const order=[],seen={};
  (function walk(id){
    if(!id||seen[id]||!by[id])return;
    seen[id]=1;order.push(id);
    (by[id].adjacent||[]).forEach(walk);
  })(P[0].id);
  P.forEach(p=>{if(!seen[p.id])order.push(p.id)});

  /* ---- the floor plan (D-134) -----------------------------------------
     This used to place every room on an ellipse and draw lines between the
     adjacent ones, which is a graph diagram wearing a plan's clothes: every
     building in every case came out as the same ring of boxes with the same
     spokes across the middle.

     A plan is not in the data — `adjacent` is a door graph and a door graph has
     no geometry — so one has to be solved for. A physics settle was tried first
     and produced a tidy scatter: boxes floating a wall apart with dead air
     between them, which is a graph again, just a nicer-looking one. What makes a
     drawing read as a building is that the rooms TOUCH. So rooms are packed onto
     a lattice instead: one room per cell, neighbours take the cell next door, and
     a door is drawn as a break in the shared wall rather than a wire in the gap.

     Breadth-first from the busiest room, cells chosen in a fixed compass order
     and scored on how compact they keep the footprint, so the same house draws
     the same way every time it is opened and a player's memory of the plan stays
     worth something. A door that could not be given a shared wall (the graph is
     not always planar, let alone rectangular) is drawn as a dashed run between
     the two rooms: a corridor, honestly marked as the exception. */
  const W=560,H=300;
  const doorsOf={};
  P.forEach(p=>doorsOf[p.id]=(p.adjacent||[]).filter(q=>by[q]&&q!==p.id));

  // Busiest room first: the hall or landing everything hangs off, usually.
  const roots=order.slice().sort((a,b)=>
    (doorsOf[b].length-doorsOf[a].length)||(order.indexOf(a)-order.indexOf(b)));
  const cell={},taken={};
  const key=(x,y)=>x+','+y;
  const put=(id,x,y)=>{cell[id]={x:x,y:y};taken[key(x,y)]=id};
  const STEPS=[[1,0],[0,1],[-1,0],[0,-1]];

  // How far this cell would stretch the footprint. Lower is tidier.
  function cost(x,y){
    let x0=x,x1=x,y0=y,y1=y;
    for(const id in cell){
      const c=cell[id];
      x0=Math.min(x0,c.x);x1=Math.max(x1,c.x);
      y0=Math.min(y0,c.y);y1=Math.max(y1,c.y);
    }
    return (x1-x0+1)*(y1-y0+1)*2+Math.abs(x)+Math.abs(y);
  }
  function freeNear(x,y){          // nearest empty cell, spiralling outward
    for(let r=1;r<12;r++)
      for(let dx=-r;dx<=r;dx++)for(let dy=-r;dy<=r;dy++){
        if(Math.max(Math.abs(dx),Math.abs(dy))!==r)continue;
        if(!taken[key(x+dx,y+dy)])return {x:x+dx,y:y+dy};
      }
    return {x:x,y:y+12};
  }

  put(roots[0],0,0);
  const queue=[roots[0]];
  while(queue.length){
    const id=queue.shift(),c=cell[id];
    doorsOf[id].forEach(q=>{
      if(cell[q])return;
      let best=null;
      STEPS.forEach(s=>{
        const x=c.x+s[0],y=c.y+s[1];
        if(taken[key(x,y)])return;
        const k=cost(x,y);
        if(!best||k<best.k)best={x:x,y:y,k:k};
      });
      const spot=best||freeNear(c.x,c.y);
      put(q,spot.x,spot.y);queue.push(q);
    });
  }
  // Rooms with no door to the rest of the house still have to go somewhere.
  order.forEach(id=>{if(!cell[id]){const s=freeNear(0,0);put(id,s.x,s.y)}});

  /* The walk places every room in one pass and never reconsiders, which leaves
     doors stranded: two rooms with a door between them sitting three cells
     apart. Some of that is unavoidable — a triangle of rooms cannot be drawn on
     a grid at all, the lattice is bipartite and a three-cycle is not — but most
     of it is just the order things happened to be placed in. So: a short local
     search. Every room tries every free cell around the footprint and every swap
     with another room, and keeps the move only if the plan gets tidier. Strictly
     downhill, fixed order, no randomness, so it stays deterministic. */
  function score(){
    let bad=0,far=0,x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
    order.forEach(id=>{
      const c=cell[id];
      x0=Math.min(x0,c.x);x1=Math.max(x1,c.x);
      y0=Math.min(y0,c.y);y1=Math.max(y1,c.y);
      doorsOf[id].forEach(q=>{
        const d=Math.abs(c.x-cell[q].x)+Math.abs(c.y-cell[q].y);
        if(d>1)bad++;
        far+=d;
      });
    });
    return bad*1000+far*10+(x1-x0+1)*(y1-y0+1);
  }
  function reseat(){
    const spots=[];
    let x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
    order.forEach(id=>{const c=cell[id];
      x0=Math.min(x0,c.x);x1=Math.max(x1,c.x);
      y0=Math.min(y0,c.y);y1=Math.max(y1,c.y)});
    for(let x=x0-1;x<=x1+1;x++)for(let y=y0-1;y<=y1+1;y++)
      if(!taken[key(x,y)])spots.push([x,y]);
    return spots;
  }
  for(let round=0;round<40;round++){
    let moved=false,best=score();
    for(const id of order){
      const home=cell[id];
      for(const [x,y] of reseat()){
        delete taken[key(home.x,home.y)];put(id,x,y);
        if(score()<best){best=score();moved=true;break}
        delete taken[key(x,y)];put(id,home.x,home.y);
      }
      if(moved)break;
      for(const other of order){
        if(other===id)continue;
        const there=cell[other];
        put(id,there.x,there.y);put(other,home.x,home.y);
        if(score()<best){best=score();moved=true;break}
        put(id,home.x,home.y);put(other,there.x,there.y);
      }
      if(moved)break;
    }
    if(!moved)break;
  }

  const cxs=order.map(id=>cell[id].x),cys=order.map(id=>cell[id].y);
  const gx0=Math.min(...cxs),gy0=Math.min(...cys);
  const cols=Math.max(...cxs)-gx0+1,rows=Math.max(...cys)-gy0+1;
  const CW=Math.min(146,(W-24)/cols),CH=Math.min(78,(H-24)/rows);
  const offX=(W-cols*CW)/2-gx0*CW,offY=(H-rows*CH)/2-gy0*CH;
  const at={};
  order.forEach(id=>{
    at[id]={x:offX+cell[id].x*CW,y:offY+cell[id].y*CH,gx:cell[id].x,gy:cell[id].y};
  });

  // Each door once: adjacency is symmetric by the time it reaches the browser.
  const drawn={};let edges='';
  const DOOR=Math.min(22,Math.min(CW,CH)*0.34);
  P.forEach(p=>(p.adjacent||[]).forEach(q=>{
    const k=[p.id,q].sort().join('|');
    if(drawn[k]||!at[q]||!at[p.id])return;
    drawn[k]=1;
    const a=at[p.id],b=at[q];
    const dx=b.gx-a.gx,dy=b.gy-a.gy;
    if(Math.abs(dx)+Math.abs(dy)===1){
      // Sharing a wall: the door is the gap in it.
      const mx=(a.x+b.x)/2+CW/2,my=(a.y+b.y)/2+CH/2;
      const x1=dx?mx:mx-DOOR/2,x2=dx?mx:mx+DOOR/2;
      const y1=dx?my-DOOR/2:my,y2=dx?my+DOOR/2:my;
      edges+='<line x1="'+x1.toFixed(1)+'" y1="'+y1.toFixed(1)+'" x2="'+
        x2.toFixed(1)+'" y2="'+y2.toFixed(1)+'" class="door"/>';
    }else{
      /* No shared wall to break. A line between the two centres would cross
         whatever rooms lie between, which is worse than saying nothing, so each
         room gets a short dashed stub on the wall facing the other: a way out of
         this room towards that one, without pretending to draw the route. */
      const acx=a.x+CW/2,acy=a.y+CH/2,bcx=b.x+CW/2,bcy=b.y+CH/2;
      const vx=bcx-acx,vy=bcy-acy;
      const flat=Math.abs(vx)*CH>Math.abs(vy)*CW;   // which wall it leaves by
      const sx=flat?Math.sign(vx)*CW/2:0,sy=flat?0:Math.sign(vy)*CH/2;
      const stub=(cx0,cy0,dir)=>{
        const ex=cx0+sx*dir,ey=cy0+sy*dir;
        return '<line x1="'+(ex-sx*dir*0.30).toFixed(1)+'" y1="'+
          (ey-sy*dir*0.30).toFixed(1)+'" x2="'+ex.toFixed(1)+'" y2="'+
          ey.toFixed(1)+'" class="door far"/>';
      };
      edges+=stub(acx,acy,1)+stub(bcx,bcy,-1);
    }
  }));

  const here=((n.timeline||{})[atSlot])||{};
  const dead=new Set((n.tags||[]).filter(k=>k.dead).map(k=>k.tag));
  let rooms='';
  P.forEach(p=>{
    const q=at[p.id];if(!q)return;
    const inside=here[p.id]||[];
    rooms+='<g class="room'+(inside.length?' seen':'')+(p.scene?' clickable':'')+
      '" data-scene="'+esc(p.scene||'')+'" data-room="'+esc(p.name)+'">'+
      '<rect x="'+q.x.toFixed(1)+'" y="'+q.y.toFixed(1)+
      '" width="'+CW.toFixed(1)+'" height="'+CH.toFixed(1)+'"/>'+
      // "Dressing Corridor" in a narrow cell would run out through the wall.
      '<text class="rn" font-size="'+
      Math.max(6,Math.min(9,(CW-16)/(p.name.length*0.66))).toFixed(1)+
      '" x="'+(q.x+8).toFixed(1)+'" y="'+
      (q.y+15).toFixed(1)+'">'+esc(p.name)+'</text>'+
      inside.map((x,i)=>{
        const span=(inside.length-1)*21;
        return '<text class="who'+(x.disputed?' bad':(dead.has(x.tag)?' dead':''))+
          (x.firm?' firm':'')+'" x="'+(q.x+CW/2-span/2+i*21).toFixed(1)+'" y="'+
          (q.y+CH-13).toFixed(1)+'"><title>'+esc(x.name+', from '+x.source)+
          '</title>'+esc(x.tag)+'</text>';
      }).join('')+'</g>';
  });

  // The dead man is left off this line. "Nobody has placed the victim at this
  // hour" is true and useless, and after the murder it is true of every hour.
  const gone=new Set((n.tags||[]).filter(k=>k.dead).map(k=>k.tag));
  const nobody=(((n.missing||{})[atSlot])||[]).filter(x=>!gone.has(x.tag));
  const scrub='<div id="hours">'+times.map(t=>
    '<button class="hr'+(t.id===atSlot?' on':'')+'" data-slot="'+esc(t.id)+'">'+
    esc(t.label)+'</button>').join('')+'</div>';

  return '<h2>The building</h2>'+scrub+
    '<svg id="plan" viewBox="0 0 '+W+' '+H+'">'+rooms+edges+'</svg>'+
    (nobody.length?'<div class="empty" style="margin:2px 0 0">Nobody has placed '+
      nobody.map(x=>esc(x.name)).join(', ')+' at this hour.</div>':'')+
    '<div class="empty" style="margin:6px 0 18px">A break in a wall is a door. '+
    'Red means two '+
    'people put them in different rooms at this hour, and a ringed tag was '+
    'confirmed by somebody other than themselves.'+
    (P.some(p=>p.scene)?' Click a room to stand in it.':'')+'</div>';
}

function viewMap(n){
  /* The whole evening at once: rooms down the side, the clock across the top,
     people as initials. A snapshot of one slot could not show a movement, and a
     movement is the only thing on this screen worth seeing. */
  const T=n.timeline||{}, M=n.missing||{}, K=n.tags||[];
  const dead=new Set(K.filter(k=>k.dead).map(k=>k.tag));
  let h=plan(n)+'<h2>Where they say they were</h2><div class="tlwrap"><table class="tl">'+
    '<tr><th></th>'+S.times.map(t=>'<th>'+esc(t.label)+'</th>').join('')+'</tr>';
  S.places.forEach(p=>{
    h+='<tr><th class="rm'+(p.scene?' clickable" data-scene="'+esc(p.scene)+
      '" data-room="'+esc(p.name):'')+'">'+esc(p.name)+'</th>'+S.times.map(t=>{
      const cell=((T[t.id]||{})[p.id])||[];
      return '<td>'+cell.map(x=>'<span class="pin'+(x.disputed?' bad':
        (dead.has(x.tag)?' dead':''))+(x.firm?' firm':'')+'" title="'+
        esc(x.name+', from '+x.source)+
        '">'+esc(x.tag)+'</span>').join('')+'</td>';
    }).join('')+'</tr>';
  });
  // Before a single claim exists, every person is unaccounted for at every
  // hour, which fills the row with the whole cast five times over and says
  // nothing (D-106). The empty grid above is worth showing: it is the shape of
  // the evening and the player can see the building. This row is not.
  if(Object.keys(T).length)
  h+='<tr class="gap"><th class="rm">unaccounted for</th>'+S.times.map(t=>
    '<td>'+((M[t.id]||[]).map(x=>'<span class="pin off" title="'+esc(x.name)+
      ' — nobody has placed them here yet">'+esc(x.tag)+'</span>').join(''))+
    '</td>').join('')+'</tr>';
  // Closed unconditionally. It used to be closed inside the `if` above, so on an
  // empty notebook the table and its wrapper were left open and the browser
  // hoisted the legend and the caption out past the grid, putting them in front
  // of the thing they explain. Only visible before the first answer, which is
  // exactly when a new player is looking.
  h+='</table></div>';
  h+='<div class="key">'+K.map(k=>'<span><b>'+esc(k.tag)+'</b>'+esc(k.name)+
    (k.dead?' (the deceased)':'')+'</span>').join('')+'</div>';
  return h+'<div class="empty" style="margin-top:12px">Only what somebody has '+
    'told you. Red means two people put them in different rooms at that hour. '+
    'The bottom row is where your questions have not reached. A ringed tag was '+
    'confirmed by somebody other than themselves.'+
    (S.places.some(p=>p.scene)?' Click a room to stand in it.':'')+'</div>';
}

function accuse(id){
  /* Two questions, not one (D-065). The timeline gets you to the person and the
     secrets get you to the reason. The reason is written rather than picked
     (D-092): nothing marks it, and afterwards you read what you wrote against
     what was true and decide for yourself whether you had it. */
  let h='<h3>Charge '+esc(nameOf(id))+'</h3>'+
    '<p>In your own words: what did they do it for? Nothing here is marked. '+
    'You will see the whole case afterwards and can judge your own answer '+
    'against it. This ends the game.</p>'+
    '<textarea id="why" rows="4" placeholder="They killed him because\u2026"></textarea>'+
    '<div style="margin-top:18px;display:flex;gap:10px">'+
    '<button id="press" class="accuse">Charge '+esc(nameOf(id).split(' ')[0])+'</button>'+
    '<button id="backout">Not yet</button></div>';
  $('revealcard').innerHTML=h;$('reveal').classList.add('on');
  $('why').focus();
  $('press').onclick=()=>charge(id,$('why').value);
  $('backout').onclick=()=>{$('reveal').classList.remove('on')};
}

/* The ending, played rather than printed (D-143).

   Everything below used to arrive as one panel: the verdict, the motive, the
   lies, the witnesses and the secrets, all at once, in the same typeface, in
   the order the code happened to build them. It is the moment the whole hour
   was for and it read like a receipt.

   So it is a sequence now. The verdict lands on its own, against the face of
   whoever you charged. Then what you wrote, against what was true. Then the
   lies, then the people who could have broken them, then what you never found.
   A click takes the rest at once, because a player who wants the answer should
   never have to wait for a transition. */
async function charge(id,why){
  const r=await (await fetch('/accuse',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({who:id,why:why||null})})).json();

  const charged=S.suspects.find(x=>x.id===id);
  const acts=[];

  acts.push('<div class="act verdict'+(r.correct?' right':' wrong')+'">'+
    (charged&&charged.portrait
      ?'<img class="face" src="'+esc(charged.portrait)+'" alt="">'
      :'')+
    '<div class="said">You charged '+esc(nameOf(id))+'.</div>'+
    '<h3>'+(r.correct?'You named him.':'Wrong.')+'</h3>'+
    '<div class="who">The killer was <b>'+esc(r.killer)+'</b>.</div>'+
    '<div class="tally">'+r.questions+
    (r.questions===1?' question':' questions')+' asked</div></div>');

  if(r.charged||r.motive){
    let h='<div class="act"><h2>The reason</h2>';
    if(r.charged)h+='<div class="item soft"><span class="tag">what you wrote</span>'+
      esc(r.charged)+'</div>';
    if(r.motive)h+='<div class="item '+(r.correct?'hard':'cold')+
      '"><span class="tag">what it was</span>'+esc(r.motive)+'</div>';
    if(r.charged&&r.motive)h+='<p class="empty">Nobody is marking this. Read the '+
      'two and decide whether you had it.</p>';
    acts.push(h+'</div>');
  }

  if(r.lie||(r.lies||[]).length){
    let h='<div class="act"><h2>What was not true</h2>';
    if(r.lie)h+='<div class="item hard">'+esc(r.lie)+'</div>';
    if((r.lies||[]).length>1)h+=r.lies.map(l=>
      '<div class="item '+(l.killer?'hard':'soft')+'"><b>'+esc(l.name)+'</b> said the '+
      esc(l.claimed)+' at '+esc(l.time)+'. They were in the '+esc(l.truth)+'.'+
      (l.covering?'<br><span class="empty">Covering: '+esc(l.covering)+'</span>':'')+
      '</div>').join('');
    acts.push(h+'</div>');
  }

  if(r.witnesses.length)acts.push('<div class="act"><h2>Who could have broken it</h2>'+
    r.witnesses.map(w=>'<div class="item '+(w.asked?'soft':'cold')+'">'+esc(w.name)+
    ' \u2014 '+(w.asked?('asked '+w.asked+'x'):'you never asked them')+
    '</div>').join('')+'</div>');

  if((r.surfaced||[]).length)acts.push('<div class="act"><h2>What you got out of them'+
    '</h2>'+r.surfaced.map(x=>'<div class="item soft">'+esc(x)+'</div>').join('')+
    '</div>');

  if(r.missed.length)acts.push('<div class="act"><h2>Secrets you never found</h2>'+
    r.missed.map(m=>'<div class="item cold">'+esc(m)+'</div>').join('')+'</div>');

  const card=$('revealcard');
  card.className='staged';
  card.innerHTML=acts.join('');
  $('reveal').classList.add('on');
  $('reveal').scrollTop=0;

  const parts=[...card.querySelectorAll('.act')];
  let next=0, timer=null;
  function show(){
    if(next>=parts.length){clearInterval(timer);timer=null;return}
    parts[next++].classList.add('in');
  }
  function all(){
    while(next<parts.length)parts[next++].classList.add('in');
    clearInterval(timer);timer=null;
  }
  setTimeout(()=>{show();if(r.correct)chime();timer=setInterval(show,1100)},420);
  $('reveal').addEventListener('click',all,{once:true});
}

/* Cross-fade the backdrop between the establishing shot and a room (D-069).
   Two layers alternating: whichever is hidden gets the new image and fades up,
   so a room arrives over the place rather than replacing it with a blink. */
let backTop=false;
function showScene(url,label){
  if(!url)return;
  const next=$(backTop?'backdrop':'backdrop2'), prev=$(backTop?'backdrop2':'backdrop');
  next.style.backgroundImage='url("'+url+'")';
  next.style.opacity='1';prev.style.opacity='0';
  backTop=!backTop;
  const w=$('where');
  w.textContent=label;w.className=label?'on':'';
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
boot();
</script></body></html>
"""


def _lan_address() -> str:
    """This machine's address on the local network.

    Opening a UDP socket to a public address is the usual trick: nothing is
    sent, but the OS has to pick which interface it would use, and that is the
    one other people on this wifi can reach.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        probe.close()


def _estimate(mystery, quality: str, faces: bool, rooms: bool) -> float:
    """What the pictures for this case are about to cost.

    Six images: a portrait for each living member of the cast, and one
    establishing shot of the place. It was eleven until the per-room backdrops
    were dropped (D-102), which is where five sixths of the scenery bill went
    and where almost none of the attention did.
    """
    from mystery.portraits import PRICES as FACES
    from mystery.scenery import PRICES as ROOMS

    total = 0.0
    if faces:
        total += FACES[quality] * len([c for c in mystery.characters if c.id != mystery.victim])
    if rooms:
        total += ROOMS[quality]
    return total


def _draw(args, announce: bool = True) -> None:
    """Fill in whatever was left off the command line, and say what was drawn.

    Called only by the branch that actually builds a case. `--cases`, `--daily`
    and `--case` announced a seed, a shape and an occasion that reached nothing,
    which reads like provenance and is not (D-120).
    """
    if args.seed is None:
        args.seed = fresh_seed()
        if announce:
            print(f"  Seed {args.seed}. Pass --seed {args.seed} for this case again.")
    if args.topology is None:
        args.topology = drawn(args.seed)
        if announce:
            print(f"  Shape: {args.topology}. {get_topology(args.topology).blurb}.")
    if args.setting is None:
        args.setting = occasion(args.seed)
        if announce:
            print(f"  Occasion: {args.setting}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a mystery in a browser.")
    parser.add_argument(
        "--setting",
        default=None,
        help="what the gathering is. Drawn from the seed when omitted (D-115)",
    )
    parser.add_argument("--cast", type=int, default=5)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--places", type=int, default=5)
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="pin the case. Left off, a fresh one is drawn and printed, so an "
        "evening you liked can be asked for again by number",
    )
    parser.add_argument(
        "--topology",
        default=DEFAULT_TOPOLOGY,
        choices=sorted(LIBRARY),
        help="the shape of the solution. Different shapes are different puzzles, "
        "which is what makes a second case worth playing (D-067)",
    )
    parser.add_argument(
        "--model",
        default=VOICE_MODEL,
        help="model for the suspects, called once per question. A stronger one "
        "lies better and costs more",
    )
    parser.add_argument(
        "--generator-model",
        default=DRAFT_MODEL,
        help="model that writes the case. Called once, so the strong one is "
        "nearly free here and decides everything you will play",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--portraits",
        action="store_true",
        help="generate character portraits with OpenAI. Needs OPENAI_API_KEY. "
        "Falls back to the drawn faces on any failure",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="play the case shipped with the code instead of generating one. Costs "
        "nothing to start, and the suspects still answer for real",
    )
    parser.add_argument(
        "--scenery",
        action="store_true",
        help="generate a backdrop for the setting and each room with OpenAI. "
        "Needs OPENAI_API_KEY. Falls back to the painted gradient on any failure",
    )
    parser.add_argument(
        "--art",
        action="store_true",
        help="both of the above. Two flags for 'make it look nice' was one too many",
    )
    parser.add_argument(
        "--case",
        help="play a case you have already got, by name. No model, no waiting, "
        "and it keeps whatever art it was given",
    )
    parser.add_argument(
        "--cases", action="store_true", help="list the cases on the shelf and stop"
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="serve today's case, drawn from the buffer. Never generates: if the "
        "buffer is empty it says so, because a visitor must not be the thing that "
        "decides to spend money on a model",
    )
    parser.add_argument(
        "--art-quality",
        default="low",
        choices=["low", "medium", "high"],
        help="how much to spend on pictures. Low is about fifteen cents a case, "
        "medium four times that, high fifteen times. Low is the default because "
        "the backdrops sit under a heavy vignette anyway (D-082)",
    )
    parser.add_argument(
        "--anyway",
        action="store_true",
        help="play a case the solvability analysis says cannot be won",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="serve on the local network so other people on the same wifi can play",
    )
    parser.add_argument(
        "--forget",
        action="store_true",
        help="do not keep sessions on disk. On by default: a transcript is the "
        "most useful thing a playtest produces and it used to be thrown away",
    )
    parser.add_argument(
        "--questions",
        type=int,
        default=0,
        help="override how many questions before the police arrive. Left off, "
        "the case deals its own from its seed, somewhere between forty five and "
        "a hundred and fifty, and the briefing says which (D-129)",
    )
    parser.add_argument(
        "--together",
        action="store_true",
        help="everyone shares one notebook, which is what two people in a room "
        "solving one case actually want. Off, each visitor gets their own",
    )
    args = parser.parse_args(argv)

    # One shelf for this process, chosen once, from the environment (D-119).
    # `MYSTERY_BUCKET` set puts every case in S3; unset is the folder on this
    # machine. Nothing below this line knows which it got.
    store = pick_shelf()
    if isinstance(store, S3Shelf):
        print(f"  Shelf: s3://{store.bucket}")

    if args.cases:
        print(catalogue(store))
        return 0

    if args.daily:
        case = todays_case(store)
        if case is None:
            print("  There is no case for today and the buffer is empty.")
            print("  Run: uv run python -m mystery.cli --fill --setting \"...\"")
            return 1
        print(f"  Today's case: {case.id}. {len(waiting(store))} waiting behind it.")
        return _serve(case.mystery, case.id, case.setting, case.title, args)

    # A saved case skips everything above the solver: it was solved and checked
    # on the day it was made (D-073).
    if args.case:
        saved = store.load(args.case)
        return _serve(saved.mystery, saved.id, saved.setting, saved.title, args)

    _draw(args, announce=not args.dry_run)
    if args.dry_run:
        print("  Dry run: the shipped example case. No model, no spend, nothing kept.")

    # Before anything is spent, and only on the paths that spend (D-110).
    complaint = None if args.dry_run else complaint_about_setting(args.setting)
    if complaint:
        print(complaint)
        return 2

    request = GenerationRequest(
        setting=args.setting,
        cast_size=args.cast,
        slot_count=args.slots,
        place_count=args.places,
        topology=args.topology,
        seed=args.seed,
    )

    print(f"Setting: {args.setting}")
    print("Building a mystery. This takes about half a minute.")
    try:
        from mystery.example import OPENING_NIGHT

        drafter = (
            (lambda request, complaints: OPENING_NIGHT)
            if args.dry_run
            else anthropic_drafter(model=args.generator_model)
        )
        draft = generate(request, drafter=drafter, cache_dir=None if args.dry_run else CACHE)
    except GenerationFailed as failure:
        print(failure)
        return 1

    # A draft that solves badly is not a draft to throw away (D-147). Drafting
    # is forty cents of the strongest model; solving is arithmetic and free, so
    # the free half is the half to retry. Same seed order every time, so the
    # command still reproduces the case.
    solved, used, violations = solve_until_valid(draft, seed=args.seed or 0)
    if used != (args.seed or 0):
        print(f"  Arranged on the {used - (args.seed or 0) + 1}th try. "
              f"Nothing was re-drafted and nothing was spent.")
    if violations:
        print("That mystery came out broken, on every arrangement tried.")
        for violation in violations:
            print(f"  [{violation.rule}] {violation.message}")
        # The draft is cached, so re-running this exact command will fail the
        # same way for ever. Say where it is: a failure worth looking at is
        # worth keeping, and one worth forgetting is one file to delete.
        print(f"\n  The draft is at var/mysteries/{request.cache_key()}.json")
        return 1

    # Until now nothing in the browser game ever ran the advisories: every case
    # went straight from "valid" to "playable", and thirteen quality checks and
    # a solvability analysis sat there unused while cases were played (D-068).
    findings = assess(solved, args.topology)
    winnable = analyse(solved).winnable

    if findings:
        print("\n  What is wrong with this one:")
        for finding in findings:
            print(f"    [{finding.check}] {finding.message}")

    if not winnable and not args.anyway:
        print("\n  " + report(solved))
        print(
            "\n  This case cannot be solved. Try another seed, or --anyway to play "
            "it regardless."
        )
        return 1

    # Kept before anybody plays it, so a case that turns out to be good is still
    # there tomorrow whatever happens to the prompt in between. A dry run keeps
    # nothing: it is the same example case every time, and saving it filled a
    # real bucket with copies of it under new ids (D-120).
    if args.dry_run:
        return _serve(solved, "dry-run", args.setting, solved.title, args)

    kept = store.save(solved, args.setting, args.topology, args.seed)
    print(f"\n  Saved as {kept.id}. Come back to it with --case {kept.id}")

    return _serve(solved, kept.id, args.setting, solved.title, args)


def _serve(mystery, case_id: str, setting: str, title: str, args) -> int:
    """Everything from a finished case to a running game.

    Shared by the two ways in, a fresh generation and a case off the shelf, so
    that a saved case is played by exactly the same code that played it new.
    """
    import uvicorn

    from mystery.agent import anthropic_responder

    quality = getattr(args, "art_quality", "low")
    portraits: dict[str, str] = {}

    # The gallery decides what already exists, which on a deployment is a bucket
    # and not this machine (D-121). Asking the folder would have meant a Lambda
    # regenerating every picture on every cold start, at fifty cents a time.
    art = pick_gallery()
    have_faces = art.names(case_id, "portraits")
    have_rooms = art.names(case_id, "scenery")

    portrait_dir = ART / case_id / "portraits"
    scenery_dir = ART / case_id / "scenery"

    want_faces = (args.portraits or args.art) and not have_faces
    want_rooms = (args.scenery or args.art) and not have_rooms

    if want_faces or want_rooms:
        # Said out loud before it is spent, because "roughly five cents a case"
        # was wrong by a factor of forty five and nothing in the program was
        # ever going to notice (D-082).
        print(f"  About ${_estimate(mystery, quality, want_faces, want_rooms):.2f} "
              f"of pictures at {quality} quality.")

    if want_faces:
        from mystery.portraits import generate_portraits

        print("  Painting the cast. Another half a minute.")
        portraits = generate_portraits(mystery, ART / case_id, "portraits", quality)
        if not portraits:
            print("  No portraits came back. Using the drawn faces.")

    scenery: dict[str, str] = {}
    if want_rooms:
        from mystery.scenery import generate_scenery

        print("  Painting the house. Another minute or so.")
        scenery = generate_scenery(mystery, setting, ART / case_id, "scenery", quality)
        if not scenery:
            print("  No backdrops came back. Using the painted gradient.")

    # Generation writes to disk first and always. The image API is the expensive
    # part, the files are what is worth not losing, and a failed upload should
    # cost a retry rather than the pictures (D-121). `put` is a no-op on a
    # folder gallery, which is already looking at them.
    if portraits:
        art.put(case_id, "portraits", portrait_dir)
    if scenery:
        art.put(case_id, "scenery", scenery_dir)

    # Art that already exists is used whether or not it was asked for again: it
    # was paid for once and belongs to the case, not to the flag.
    portraits = portraits or have_faces
    scenery = scenery or have_rooms

    case = Case(
        mystery,
        id=case_id,
        portraits=portraits,
        scenery=scenery,
        setting=setting,
        seed=getattr(args, "seed", 0) or 0,
    )
    case.gallery = art

    print(f"\n  {title}")
    print(f"  You:    http://localhost:{args.port}")
    if args.share:
        print(f"  Others: http://{_lan_address()}:{args.port}")
        if args.together:
            print("\n  Everyone shares one case and one notebook. Windows will ask")
        else:
            print("\n  Everyone gets the same case and their own notebook.")
            print("  Add --together to share one between you. Windows will ask")
        print("  whether to allow Python through the firewall: say yes.\n")
    else:
        print("  Add --share to let someone else on this wifi join.\n")

    uvicorn.run(
        build_app(
            case,
            anthropic_responder(model=args.model),
            # Whatever this process is configured for: a table when one is
            # named, a folder otherwise (D-122). `--forget` still means memory
            # only, which is the flag for a demo you do not want to keep.
            sessions=None if args.forget else pick_sessions(),
            budget=args.questions,
            together=args.together,
        ),
        host="0.0.0.0" if args.share else "127.0.0.1",  # noqa: S104
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
