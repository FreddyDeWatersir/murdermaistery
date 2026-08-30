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
import sys
from dataclasses import replace
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from mystery.agent import Brief, Responder, ask, build_brief
from mystery.daily import todays_case, waiting
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
from mystery.library import ART, catalogue
from mystery.library import load as load_case
from mystery.library import save as save_case
from mystery.models import Mystery
from mystery.session import FileSessions, InMemorySessions, Session, Sessions
from mystery.solvable import analyse, report
from mystery.solver import solve
from mystery.topology import DEFAULT as DEFAULT_TOPOLOGY
from mystery.topology import LIBRARY, assess, drawn
from mystery.topology import get as get_topology
from mystery.validator import validate

log = structlog.get_logger()

CACHE = Path("var/mysteries")


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
    ) -> None:
        self.id = id or mystery.title
        self.mystery = mystery
        self.portraits = portraits or {}
        self.scenery = scenery or {}
        self.knowledge = derive(mystery)
        self.briefs = {
            c.id: build_brief(mystery, self.knowledge, c.id)
            for c in mystery.characters
            if c.id != mystery.victim
        }
        self.portrait_dir: Path | None = None
        self.scenery_dir: Path | None = None


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
        return {c.id: c.name for c in self.mystery.characters}

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

    def ask(self, who: str, question: str) -> str:
        brief = self.brief_for(who)
        reply = ask(brief, question, self.responder, history=self.history(who))
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

        claims: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for statement in self.transcript.statements:
            for a in statement.assertions:
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
            }
            for c in self.transcript.contradictions()
        ]

        leads = self.transcript.leads(self.mystery, self.knowledge)
        holes = sorted(
            {
                (
                    f"{names.get(x.claimant, x.claimant)} says "
                    f"{places.get(x.place, x.place)} at {times.get(x.slot, x.slot)}, but "
                    f"{names.get(x.silent_witness, x.silent_witness)} described that room "
                    f"then and did not mention them"
                )
                for x in leads
                if x.witness_has_spoken
            }
        )
        unasked = sorted(
            {
                (
                    f"{names.get(x.claimant, x.claimant)} says "
                    f"{places.get(x.place, x.place)} at {times.get(x.slot, x.slot)}. "
                    f"Nobody has confirmed it. Ask "
                    f"{names.get(x.silent_witness, x.silent_witness)}"
                )
                for x in leads
                if not x.witness_has_spoken
            }
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

        return {
            "grid": grid,
            "conflicts": conflicts,
            "holes": holes,
            "unasked": unasked,
            "questions": self.transcript.rounds,
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
            return Game(the_case, answer, session=shared)

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
        return Game(the_case, answer, session=found)

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
            "notebook": game.notebook(),
        }

    @app.get("/portrait/{filename}")
    def portrait(filename: str):
        from fastapi.responses import FileResponse
        from fastapi.responses import Response as Sent

        cid = filename.removesuffix(".png")
        name = the_case.portraits.get(cid)
        folder = the_case.portrait_dir
        if not name or folder is None or not (folder / name).exists():
            return Sent(status_code=404)
        return FileResponse(folder / name, media_type="image/png")

    @app.get("/scene/{filename}")
    def scene(filename: str):
        from fastapi.responses import FileResponse
        from fastapi.responses import Response as Sent

        name = the_case.scenery.get(filename.removesuffix(".png"))
        folder = the_case.scenery_dir
        if not name or folder is None or not (folder / name).exists():
            return Sent(status_code=404)
        return FileResponse(folder / name, media_type="image/png")

    @app.post("/ask")
    def ask_endpoint(question: Question, request: Request, response: Response) -> dict:
        game = player(request, response)
        speech = game.ask(question.who, question.text)
        store.save(game.session)
        return {"speech": speech, "notebook": game.notebook()}

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
.badge{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;
text-transform:uppercase;color:var(--muted)}
.badge b{color:var(--bad)}
/* The panel's width is a variable so it can be dragged (D-098). Everything that
   has to agree with it reads the same property: the panel, and the shift that
   keeps the portrait out from under it. */
#book{position:fixed;top:0;right:0;bottom:0;width:min(var(--book),92vw);
background:var(--panel);
border-left:1px solid var(--rule);padding:22px;overflow-y:auto;z-index:5;
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
background:var(--panel);padding:6px 0 10px;z-index:2}
#tabs button{flex:1;font-size:12px;padding:6px 4px}
#tabs button.on{background:var(--cool);color:#0b0d12;border-color:var(--cool);font-weight:500}
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
table.tl tr.gap th.rm{color:#4d5464}
.pin{display:inline-block;background:var(--cool);color:#0b0d12;font-size:10.5px;
font-weight:600;letter-spacing:.03em;border-radius:3px;padding:2px 4px;margin:1px;
cursor:default}
.pin.bad{background:var(--bad);color:#fff}
.pin.off{background:transparent;color:#4d5464;border:1px solid var(--rule);font-weight:400}
.pin.dead{background:var(--muted);color:#0b0d12}
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
/* A centred flex child taller than the viewport loses its top edge, and the
   overflow cannot be scrolled back to because it is above the start of the box.
   `margin:auto` on the card centres it when it fits and leaves it alone when it
   does not, which is the fix rather than `align-items:center` (D-106). */
#reveal{position:fixed;inset:0;background:rgba(5,6,9,.95);display:none;
justify-content:center;padding:24px;overflow-y:auto;z-index:9;user-select:text}
#reveal.on{display:flex}
#reveal .card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:32px;max-width:640px;width:100%;margin:auto;height:max-content}
#reveal h3{font-family:var(--display);font-size:34px;margin:0 0 4px;font-weight:400}
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
mark{background:var(--warm);color:#12151d;border-radius:2px;padding:0 2px}
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
#plan .door{stroke:var(--rule);stroke-width:1.5}
#plan .room rect{fill:var(--panel2);stroke:var(--rule);stroke-width:1.5}
#plan .room.seen rect{stroke:var(--muted)}
#plan text.rn{fill:var(--muted);font-family:var(--mono);font-size:10px;
letter-spacing:.07em;text-anchor:middle}
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
<div id="reveal"><div class="card" id="revealcard"></div></div>
<script>
const $=i=>document.getElementById(i);
let S=null,who=null,busy=false,typer=null,sound=true,lastConflicts=0;
let tab='book',NB={grid:[],conflicts:[],holes:[],unasked:[],logs:{},timeline:{},
  missing:{},tags:[],found:[],held:[],shown:{}};

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

/* ---------- typewriter ------------------------------------------------- */
function say(text,pitch,asked){
  const el=$('said');el.className='';
  if(typer)clearInterval(typer);
  let i=0;
  const mouth=document.getElementById('mouth');
  // Same shape a recall will have (see `recall`), so the box does not jump when
  // the player leaves this person and comes back to them.
  el.innerHTML=(asked?'<span class="asked">“'+esc(asked)+'”</span>':'')+
    '<span class="body"></span><span class="cursor"></span>';
  const body=el.querySelector('.body');
  typer=setInterval(()=>{
    if(i>=text.length){finish();return}
    const ch=text[i++];
    body.textContent+=ch;
    if(mouth)mouth.setAttribute('ry',(i%3===0)?'5.5':'2.6');
    if(/[a-z0-9]/i.test(ch)&&i%2===0)blip(pitch);
  },17);
  function finish(){
    clearInterval(typer);typer=null;
    body.textContent=text;
    el.querySelector('.cursor')?.remove();
    if(mouth)mouth.setAttribute('ry','2.6');
  }
  el._finish=finish;
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
  paintBook(S.notebook);
  select(S.suspects[0].id);
}

async function send(){
  const inp=$('q'),text=inp.value.trim();
  if(!text||busy||!who)return;
  busy=true;inp.value='';
  // The question lands before the answer does, so the box is already this
  // person's while they think about it.
  $('said').className='';
  $('said').innerHTML='<span class="asked">“'+esc(text)+'”</span>'+
    '<span class="body">…</span>';
  try{
    const r=await (await fetch('/ask',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({who:who,text:text})})).json();
    say(r.speech,pitchOf(who),text);
    const before=lastConflicts;
    paintBook(r.notebook);
    if(r.notebook.conflicts.length>before){
      chime();
      ['portrait','photo'].forEach(k=>{$(k).classList.add('rattled');
        setTimeout(()=>$(k).classList.remove('rattled'),520)});
    }
  }catch(e){$('said').textContent='(no answer came back)'}
  busy=false;inp.focus();
}

function paintBook(n){
  NB=n;lastConflicts=n.conflicts.length;
  $('count').innerHTML=n.questions+(n.questions===1?' question':' questions')+
    (n.conflicts.length?' \u00b7 <b>'+n.conflicts.length+' contradiction'+
      (n.conflicts.length>1?'s':'')+'</b>':'');
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
  const box=$('find');
  if(box){
    // Re-rendered on every keystroke would lose the caret, so the field keeps
    // its own state and only the rows below it are redrawn.
    box.oninput=()=>{find=box.value;const at=box.selectionStart;render();
      const again=$('find');if(again){again.focus();again.setSelectionRange(at,at)}};
  }
  const mine=$('mynotes');
  if(mine)mine.oninput=()=>save(noteKey(who),mine.value);
}

function viewBook(n){
  /* Group by person rather than by row, so the panel reads as five short
     dossiers instead of one long table nobody scans. */
  const by={};
  n.grid.forEach(r=>{(by[r.subject]=by[r.subject]||[]).push(r)});
  let h='';
  /* Who you are, kept where you can reread it (D-101). It is the answer to
     "why is anybody telling me anything", and the player is entitled to it. */
  if(S.you)h+='<h2>You</h2><div class="item soft">'+esc(S.you.role)+
    (S.you.why?'<br><span class="empty">'+esc(S.you.why)+'</span>':'')+
    (S.you.standing?'<br><span class="empty">'+esc(S.you.standing)+'</span>':'')+
    '</div>';
  if(n.conflicts.length)h+='<h2>Contradictions</h2>'+n.conflicts.map(c=>
    '<div class="item hard">'+esc(c.text)+'<br><span class="empty">'+esc(c.kind)+
    '</span></div>').join('');
  if(n.holes.length)h+='<h2>Accounts that do not line up</h2>'+n.holes.map(x=>
    '<div class="item soft">'+esc(x)+'</div>').join('');
  h+='<h2>What each of them claims</h2>';
  if(!Object.keys(by).length)h+='<div class="empty">Nothing established yet.</div>';
  Object.keys(by).sort().forEach(name=>{
    h+='<div class="item"><b>'+esc(name)+'</b><table>'+by[name].map(r=>
      '<tr class="'+(r.disputed?'disputed':'')+'"><td>'+esc(r.time)+'</td><td>'+
      esc(r.place)+'</td><td>'+esc(r.source)+'</td></tr>').join('')+'</table></div>';
  });
  if(n.unasked.length)h+='<h2>Worth asking</h2>'+n.unasked.map(x=>
    '<div class="item cold">'+esc(x)+'</div>').join('');
  return h;
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
    '<textarea id="mynotes" rows="5" placeholder="What you make of them, what to '+
    'come back to\u2026">'+esc(noteFor(who))+'</textarea>';
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

  const W=520,H=252,cx=W/2,cy=H/2,rx=W/2-70,ry=H/2-44;
  const at={};
  order.forEach((id,i)=>{
    const a=(i/order.length)*Math.PI*2-Math.PI/2;
    at[id]={x:cx+rx*Math.cos(a),y:cy+ry*Math.sin(a)};
  });

  // Each door once: adjacency is symmetric by the time it reaches the browser.
  const drawn={};let edges='';
  P.forEach(p=>(p.adjacent||[]).forEach(q=>{
    const key=[p.id,q].sort().join('|');
    if(drawn[key]||!at[q]||!at[p.id])return;
    drawn[key]=1;
    edges+='<line x1="'+at[p.id].x.toFixed(1)+'" y1="'+at[p.id].y.toFixed(1)+
      '" x2="'+at[q].x.toFixed(1)+'" y2="'+at[q].y.toFixed(1)+'" class="door"/>';
  }));

  const here=((n.timeline||{})[atSlot])||{};
  const dead=new Set((n.tags||[]).filter(k=>k.dead).map(k=>k.tag));
  const BW=104,BH=34;
  let rooms='';
  P.forEach(p=>{
    const q=at[p.id];if(!q)return;
    const inside=here[p.id]||[];
    rooms+='<g class="room'+(inside.length?' seen':'')+(p.scene?' clickable':'')+
      '" data-scene="'+esc(p.scene||'')+'" data-room="'+esc(p.name)+'">'+
      '<rect x="'+(q.x-BW/2).toFixed(1)+'" y="'+(q.y-BH/2).toFixed(1)+
      '" width="'+BW+'" height="'+BH+'" rx="6"/>'+
      '<text class="rn" x="'+q.x.toFixed(1)+'" y="'+(q.y-BH/2-7).toFixed(1)+'">'+
      esc(p.name)+'</text>'+
      inside.map((x,i)=>{
        const span=(inside.length-1)*20;
        return '<text class="who'+(x.disputed?' bad':(dead.has(x.tag)?' dead':''))+
          (x.firm?' firm':'')+'" x="'+(q.x-span/2+i*20).toFixed(1)+'" y="'+
          (q.y+4).toFixed(1)+'"><title>'+esc(x.name+', from '+x.source)+
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
    '<svg id="plan" viewBox="0 0 '+W+' '+H+'">'+edges+rooms+'</svg>'+
    (nobody.length?'<div class="empty" style="margin:2px 0 0">Nobody has placed '+
      nobody.map(x=>esc(x.name)).join(', ')+' at this hour.</div>':'')+
    '<div class="empty" style="margin:6px 0 18px">A line is a door. Red means two '+
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
    '</td>').join('')+'</tr></table></div>';
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

async function charge(id,why){
  const r=await (await fetch('/accuse',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({who:id,why:why||null})})).json();
  let h='<h3>'+(r.correct?'You named him.':'Wrong.')+'</h3>';
  h+='<p>The killer was <b>'+esc(r.killer)+'</b>. You asked '+r.questions+
    (r.questions===1?' question.':' questions.')+'</p>';
  if(r.charged)h+='<h2>What you said</h2><div class="item soft">'+esc(r.charged)+'</div>';
  if(r.motive)h+='<h2>What it was</h2><div class="item '+(r.correct?'hard':'cold')+'">'+
    esc(r.motive)+'</div>';
  if(r.charged&&r.motive)h+='<p class="empty">Nobody is marking this. Read the two '+
    'and decide whether you had it.</p>';
  if(r.lie)h+='<h2>The lie</h2><p>'+esc(r.lie)+'</p>';
  if((r.lies||[]).length>1)h+='<h2>Everyone who lied to you</h2>'+r.lies.map(l=>
    '<div class="item '+(l.killer?'hard':'soft')+'"><b>'+esc(l.name)+'</b> said the '+
    esc(l.claimed)+' at '+esc(l.time)+'. They were in the '+esc(l.truth)+'.'+
    (l.covering?'<br><span class="empty">Covering: '+esc(l.covering)+'</span>':'')+
    '</div>').join('');
  if(r.witnesses.length)h+='<h2>Who could have broken it</h2>'+r.witnesses.map(w=>
    '<div class="item '+(w.asked?'soft':'cold')+'">'+esc(w.name)+' \u2014 '+
    (w.asked?('asked '+w.asked+'x'):'you never asked them')+'</div>').join('');
  if((r.surfaced||[]).length)h+='<h2>What you got out of them</h2>'+r.surfaced.map(x=>
    '<div class="item soft">'+esc(x)+'</div>').join('');
  if(r.missed.length)h+='<h2>Secrets you never found</h2>'+r.missed.map(m=>
    '<div class="item cold">'+esc(m)+'</div>').join('');
  $('revealcard').innerHTML=h;$('reveal').classList.add('on');
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


def _existing(folder: Path) -> dict[str, str]:
    """Whatever pictures are already on disk for this case.

    Art belongs to the case rather than to the flag that made it, so a saved
    case brings its faces and rooms back without --art and without paying twice
    (D-073).
    """
    if not folder.exists():
        return {}
    return {path.stem: path.name for path in sorted(folder.glob("*.png"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play a mystery in a browser.")
    parser.add_argument("--setting", default="a private view at a small art gallery")
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
        "--together",
        action="store_true",
        help="everyone shares one notebook, which is what two people in a room "
        "solving one case actually want. Off, each visitor gets their own",
    )
    args = parser.parse_args(argv)

    # Drawn once here rather than defaulted to zero, so two runs of the same
    # command are two different evenings (D-102). Printed, because a seed you
    # cannot read is not reproducible.
    if args.seed is None:
        args.seed = fresh_seed()
        print(f"  Seed {args.seed}. Pass --seed {args.seed} for this case again.")

    # The shape comes from the seed too, so the number reproduces the whole
    # case and not most of it (D-103).
    if args.topology is None:
        args.topology = drawn(args.seed)
        print(f"  Shape: {args.topology}. {get_topology(args.topology).blurb}.")

    if args.cases:
        print(catalogue())
        return 0

    if args.daily:
        case = todays_case()
        if case is None:
            print("  There is no case for today and the buffer is empty.")
            print("  Run: uv run python -m mystery.cli --fill --setting \"...\"")
            return 1
        print(f"  Today's case: {case.id}. {len(waiting())} waiting behind it.")
        return _serve(case.mystery, case.id, case.setting, case.title, args)

    # A saved case skips everything above the solver: it was solved and checked
    # on the day it was made (D-073).
    if args.case:
        saved = load_case(args.case)
        return _serve(saved.mystery, saved.id, saved.setting, saved.title, args)

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

    solved = solve(draft, seed=args.seed)
    result = validate(solved)
    if not result.ok:
        print("That mystery came out broken. Try another seed.")
        for violation in result.violations:
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
    # there tomorrow whatever happens to the prompt in between.
    kept = save_case(solved, args.setting, args.topology, args.seed)
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
    portrait_dir = ART / case_id / "portraits"
    scenery_dir = ART / case_id / "scenery"

    want_faces = (args.portraits or args.art) and not _existing(portrait_dir)
    want_rooms = (args.scenery or args.art) and not _existing(scenery_dir)

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

    # Art already on disk is used whether or not it was asked for again: it was
    # paid for once and belongs to the case, not to the flag.
    portraits = portraits or _existing(portrait_dir)
    scenery = scenery or _existing(scenery_dir)

    case = Case(mystery, id=case_id, portraits=portraits, scenery=scenery)
    case.portrait_dir = portrait_dir
    case.scenery_dir = scenery_dir

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
            sessions=None if args.forget else FileSessions(),
            together=args.together,
        ),
        host="0.0.0.0" if args.share else "127.0.0.1",  # noqa: S104
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
