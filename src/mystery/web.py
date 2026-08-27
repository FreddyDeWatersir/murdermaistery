"""Play in a browser instead of a terminal.

    uv run python -m mystery.web --setting "a private view at a small art gallery"

Then open http://localhost:8000.

One game, held in memory, one process. No database, no sessions, no auth: this
exists so that two people can sit in front of one laptop and find out whether the
game is any good, which is the only question that matters right now. Everything
it does not do is deliberate.
"""

import argparse
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from mystery.agent import Responder, ask, build_brief
from mystery.generator import (
    GenerationFailed,
    GenerationRequest,
    anthropic_drafter,
    generate,
)
from mystery.interrogation import Statement, Transcript, assertions_from
from mystery.knowledge import analyse_alibi, derive
from mystery.models import Mystery
from mystery.solver import solve
from mystery.validator import validate
from pydantic import BaseModel

CACHE = Path("var/mysteries")


class Game:
    """One case, one transcript, one process."""

    def __init__(self, mystery: Mystery, responder: Responder) -> None:
        self.mystery = mystery
        self.responder = responder
        self.knowledge = derive(mystery)
        self.briefs = {
            c.id: build_brief(mystery, self.knowledge, c.id)
            for c in mystery.characters
            if c.id != mystery.victim
        }
        self.transcript = Transcript()
        self.solved = False

    @property
    def names(self) -> dict[str, str]:
        return {c.id: c.name for c in self.mystery.characters}

    @property
    def times(self) -> dict[str, str]:
        return {s.id: s.label for s in self.mystery.slots}

    @property
    def places(self) -> dict[str, str]:
        return {p.id: p.name for p in self.mystery.places}

    def ask(self, who: str, question: str) -> str:
        brief = self.briefs[who]
        reply = ask(brief, question, self.responder)
        self.transcript.record(
            Statement(
                round=self.transcript.rounds + 1,
                speaker=who,
                question=question,
                speech=reply.speech,
                assertions=assertions_from(brief, reply),
                refused=reply.refused,
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

        return {
            "grid": grid,
            "conflicts": conflicts,
            "holes": holes,
            "unasked": unasked,
            "questions": self.transcript.rounds,
        }

    def accuse(self, who: str) -> dict:
        self.solved = True
        m, names, places, times = self.mystery, self.names, self.places, self.times

        motive = next(
            (s for s in m.secrets if s.holder == m.killer and s.is_motive),
            next((s for s in m.secrets if s.holder == m.killer), None),
        )
        analysis = analyse_alibi(m, self.knowledge)
        surfaced = {a.subject for s in self.transcript.statements for a in s.assertions}

        lie = None
        if m.false_claim:
            truth = m.placements.get(m.false_claim.character, {}).get(m.false_claim.slot)
            lie = (
                f"{names.get(m.false_claim.character, m.false_claim.character)} claimed the "
                f"{places.get(m.false_claim.place, m.false_claim.place)} at "
                f"{times.get(m.false_claim.slot, m.false_claim.slot)}. They were in the "
                f"{places.get(truth, truth)}."
            )

        return {
            "correct": who == m.killer,
            "accused": names.get(who, who),
            "killer": names.get(m.killer, m.killer),
            "questions": self.transcript.rounds,
            "motive": motive.summary if motive else None,
            "lie": lie,
            "witnesses": [
                {
                    "name": names.get(p, p),
                    "asked": self.transcript.asked(p),
                }
                for p in analysis.contradictors
            ],
            "missed": [
                f"{names.get(s.holder, s.holder)}: {s.summary}"
                for s in m.secrets
                if s.holder not in surfaced
            ],
        }


class Question(BaseModel):
    who: str
    text: str


class Accusation(BaseModel):
    who: str


def build_app(game: Game) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return PAGE

    @app.get("/state")
    def state() -> dict:
        return {
            "title": game.mystery.title,
            "victim": game.names.get(game.mystery.victim, ""),
            "suspects": [
                {"id": c.id, "name": c.name, "wants": c.wants, "manner": c.manner}
                for c in game.mystery.characters
                if c.id != game.mystery.victim
            ],
            "times": [s.label for s in sorted(game.mystery.slots, key=lambda s: s.index)],
            "places": [p.name for p in game.mystery.places],
            "notebook": game.notebook(),
        }

    @app.post("/ask")
    def ask_endpoint(question: Question) -> dict:
        speech = game.ask(question.who, question.text)
        return {"speech": speech, "notebook": game.notebook()}

    @app.post("/accuse")
    def accuse_endpoint(accusation: Accusation) -> dict:
        return game.accuse(accusation.who)

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
#scene.shifted{right:min(430px,92vw)}
@media(max-width:760px){#scene.shifted{right:0}}
#top{padding:14px 20px;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;
z-index:3}
#top h1{font-family:var(--display);font-weight:400;font-size:22px;margin:0}
#top .sub{color:var(--muted);font-size:12.5px}
#top .right{margin-left:auto;display:flex;gap:8px;align-items:center}
#stage{flex:1;position:relative;display:flex;align-items:flex-end;
justify-content:center;min-height:0}
#portrait{width:min(46vh,340px);transition:transform .5s cubic-bezier(.2,.8,.2,1),
opacity .35s;transform-origin:bottom center;filter:drop-shadow(0 24px 60px rgba(0,0,0,.75))}
#portrait.enter{opacity:0;transform:translateY(22px) scale(.97)}
#portrait.rattled{animation:shake .5s}
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
#book{position:fixed;top:0;right:0;bottom:0;width:min(430px,92vw);background:var(--panel);
border-left:1px solid var(--rule);padding:22px;overflow-y:auto;z-index:5;
transform:translateX(100%);transition:transform .32s cubic-bezier(.2,.8,.2,1);
user-select:text}
#book.open{transform:none}
#book h2{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;
text-transform:uppercase;color:var(--muted);margin:22px 0 8px;font-weight:500}
#book h2:first-of-type{margin-top:0}
table{width:100%;border-collapse:collapse;font-size:12px;font-family:var(--mono)}
td{padding:4px 5px;border-bottom:1px solid var(--rule);vertical-align:top}
tr.disputed td{color:var(--bad)}
.item{background:var(--panel2);border-left:2px solid var(--rule);padding:8px 11px;
margin-bottom:7px;font-size:12.5px;line-height:1.5;border-radius:0 4px 4px 0}
.item.hard{border-left-color:var(--bad)}
.item.soft{border-left-color:var(--warm)}
.item.cold{border-left-color:var(--rule);color:var(--muted)}
.empty{color:var(--muted);font-size:12.5px}
#reveal{position:fixed;inset:0;background:rgba(5,6,9,.95);display:none;
align-items:center;justify-content:center;padding:24px;overflow-y:auto;z-index:9;
user-select:text}
#reveal .card{background:var(--panel);border:1px solid var(--rule);border-radius:10px;
padding:32px;max-width:640px;width:100%}
#reveal h3{font-family:var(--display);font-size:34px;margin:0 0 4px;font-weight:400}
</style></head><body>
<div id="scene">
  <div id="top">
    <h1 id="title">…</h1><span class="sub" id="sub"></span>
    <div class="right">
      <span class="badge" id="count">0 questions</span>
      <button id="mute">Sound on</button>
      <button id="booktoggle">Notebook</button>
    </div>
  </div>
  <div id="stage"><svg id="portrait" viewBox="0 0 200 250"></svg></div>
  <div id="box">
    <div id="nameplate">—</div>
    <div id="said" class="empty">Pick someone below and ask them something.</div>
  </div>
  <div id="bar">
    <div id="cast"></div>
    <input id="q" placeholder="Ask a question" autocomplete="off">
    <button class="accuse" id="accusebtn">Accuse</button>
  </div>
</div>
<aside id="book"></aside>
<div id="reveal"><div class="card" id="revealcard"></div></div>
<script>
const $=i=>document.getElementById(i);
let S=null,who=null,busy=false,typer=null,sound=true,lastConflicts=0;

/* ---------- procedural portraits -------------------------------------- */
function hash(s){let h=2166136261;for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);
h=Math.imul(h,16777619)}return Math.abs(h)}
const SKIN=['#f0cdb0','#e3b492','#c99070','#a9714f','#8a5638','#f5d9c4','#d9a684','#6f4630'];
const HAIR=['#241c18','#4a3527','#7a5638','#b08046','#2b2b33','#5d5049','#8f8f97','#3a2230'];
const CLOTH=['#2c3550','#3a2f3f','#204040','#463526','#332f45','#1f3a34','#4a2c2c','#2a3b4a'];
const ACCENT=['#7fa9ee','#d9a24e','#9d8ce0','#6fbfa8','#e08b7a','#c0a06a','#7fc0d9','#c98fb0'];

function portraitSVG(id,opts){
  const h=hash(id),o=opts||{};
  const skin=SKIN[h%8],hair=HAIR[(h>>3)%8],cloth=CLOTH[(h>>6)%8],accent=ACCENT[(h>>9)%8];
  const style=(h>>12)%6, glasses=((h>>15)%4)===0, collar=((h>>17)%3)===0;
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
function say(text,pitch){
  const el=$('said');el.className='';
  if(typer)clearInterval(typer);
  let i=0;
  const mouth=document.getElementById('mouth');
  el.innerHTML='<span class="body"></span><span class="cursor"></span>';
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

/* ---------- app -------------------------------------------------------- */
function pitchOf(id){return 300+(hash(id)%9)*46}
function nameOf(id){const s=S.suspects.find(x=>x.id===id);return s?s.name:id}

function showPortrait(id){
  const p=$('portrait');
  p.classList.add('enter');
  setTimeout(()=>{p.innerHTML=portraitSVG(id);p.classList.remove('enter')},60);
}

function select(id){
  who=id;
  document.querySelectorAll('.chip').forEach(c=>c.classList.toggle('on',c.dataset.id===id));
  showPortrait(id);
  const s=S.suspects.find(x=>x.id===id);
  $('nameplate').innerHTML=esc(s.name)+(s.manner?'<small>'+esc(s.manner)+'</small>':'');
  $('q').focus();
}

async function boot(){
  S=await (await fetch('/state')).json();
  $('title').textContent=S.title;
  $('sub').textContent=S.victim+' is dead. One of them did it.';
  const cast=$('cast');
  S.suspects.forEach(s=>{
    const b=document.createElement('button');
    b.className='chip';b.dataset.id=s.id;b.title=s.wants||'';
    b.innerHTML='<svg viewBox="0 0 200 250">'+portraitSVG(s.id)+'</svg><span>'+
      esc(s.name.split(' ')[0])+'</span>';
    b.onclick=()=>select(s.id);
    cast.appendChild(b);
  });
  $('q').onkeydown=e=>{if(e.key==='Enter')send()};
  $('mute').onclick=()=>{sound=!sound;$('mute').textContent=sound?'Sound on':'Sound off'};
  $('booktoggle').onclick=()=>{
    const open=$('book').classList.toggle('open');
    $('scene').classList.toggle('shifted',open);
  };
  $('accusebtn').onclick=()=>who&&accuse(who);
  paintBook(S.notebook);
  select(S.suspects[0].id);
}

async function send(){
  const inp=$('q'),text=inp.value.trim();
  if(!text||busy||!who)return;
  busy=true;inp.value='';
  $('said').className='empty';$('said').textContent='…';
  try{
    const r=await (await fetch('/ask',{method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({who:who,text:text})})).json();
    say(r.speech,pitchOf(who));
    const before=lastConflicts;
    paintBook(r.notebook);
    if(r.notebook.conflicts.length>before){
      chime();
      $('portrait').classList.add('rattled');
      setTimeout(()=>$('portrait').classList.remove('rattled'),520);
    }
  }catch(e){$('said').textContent='(no answer came back)'}
  busy=false;inp.focus();
}

function paintBook(n){
  lastConflicts=n.conflicts.length;
  $('count').innerHTML=n.questions+(n.questions===1?' question':' questions')+
    (n.conflicts.length?' · <b>'+n.conflicts.length+' contradiction'+
      (n.conflicts.length>1?'s':'')+'</b>':'');
  let h='<h2>Who was where</h2>';
  h+=n.grid.length?'<table>'+n.grid.map(r=>'<tr class="'+(r.disputed?'disputed':'')+
    '"><td>'+esc(r.subject)+'</td><td>'+esc(r.time)+'</td><td>'+esc(r.place)+
    '</td><td>'+esc(r.source)+'</td></tr>').join('')+'</table>'
    :'<div class="empty">Nothing established yet.</div>';
  if(n.conflicts.length)h+='<h2>Contradictions</h2>'+n.conflicts.map(c=>
    '<div class="item hard">'+esc(c.text)+'<br><span class="empty">'+esc(c.kind)+
    '</span></div>').join('');
  if(n.holes.length)h+='<h2>Accounts that do not line up</h2>'+n.holes.map(t=>
    '<div class="item soft">'+esc(t)+'</div>').join('');
  if(n.unasked.length)h+='<h2>Worth asking</h2>'+n.unasked.map(t=>
    '<div class="item cold">'+esc(t)+'</div>').join('');
  $('book').innerHTML=h;
}

async function accuse(id){
  if(!confirm('Accuse '+nameOf(id)+'? This ends the game.'))return;
  const r=await (await fetch('/accuse',{method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({who:id})})).json();
  let h='<h3>'+(r.correct?'Correct.':'Wrong.')+'</h3>';
  h+='<p>The killer was <b>'+esc(r.killer)+'</b>. You asked '+r.questions+' questions.</p>';
  if(r.motive)h+='<h2>Why</h2><p>'+esc(r.motive)+'</p>';
  if(r.lie)h+='<h2>The lie</h2><p>'+esc(r.lie)+'</p>';
  if(r.witnesses.length)h+='<h2>Who could have broken it</h2>'+r.witnesses.map(w=>
    '<div class="item '+(w.asked?'soft':'cold')+'">'+esc(w.name)+' — '+
    (w.asked?('asked '+w.asked+'x'):'you never asked them')+'</div>').join('');
  if(r.missed.length)h+='<h2>Secrets you never found</h2>'+r.missed.map(m=>
    '<div class="item cold">'+esc(m)+'</div>').join('');
  $('revealcard').innerHTML=h;$('reveal').style.display='flex';
}

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}
boot();
</script></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    import uvicorn
    from mystery.agent import anthropic_responder

    parser = argparse.ArgumentParser(description="Play a mystery in a browser.")
    parser.add_argument("--setting", default="a private view at a small art gallery")
    parser.add_argument("--cast", type=int, default=5)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--places", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5",
        help="model for the suspects. A stronger one lies better and costs more",
    )
    parser.add_argument("--generator-model", default="claude-sonnet-4-5")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    request = GenerationRequest(
        setting=args.setting,
        cast_size=args.cast,
        slot_count=args.slots,
        place_count=args.places,
        seed=args.seed,
    )

    print("Building a mystery. This takes about half a minute.")
    try:
        draft = generate(
            request, drafter=anthropic_drafter(model=args.generator_model), cache_dir=CACHE
        )
    except GenerationFailed as failure:
        print(failure)
        return 1

    solved = solve(draft, seed=args.seed)
    result = validate(solved)
    if not result.ok:
        print("That mystery came out broken. Try another seed.")
        for violation in result.violations:
            print(f"  [{violation.rule}] {violation.message}")
        return 1

    print(f"\n  {solved.title}")
    print(f"  Open http://localhost:{args.port}\n")

    uvicorn.run(
        build_app(Game(solved, anthropic_responder(model=args.model))),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
