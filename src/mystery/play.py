"""A playable interrogation in the terminal.

The first version of this game that a person can actually sit down with. Ugly on
purpose: the point is to find out whether it is fun before anyone spends a week
on a frontend, which is the same order of operations that produced everything
else here.

The notebook is not a convenience feature. It is the mechanic (D-019). It shows
proven contradictions, because remembering who said what is bookkeeping, and it
shows unconfirmed claims as leads, because deciding who to press is the game.
"""

from mystery.agent import Brief, Reply, Responder, ask, build_brief, leaks
from mystery.interrogation import Statement, Transcript, assertions_from
from mystery.knowledge import Knowledge, analyse_alibi, derive
from mystery.models import CharacterId, Mystery

HELP = """
  <name> <question>   ask a suspect something
  notebook            what you have established so far
  cast                who is here
  accuse <name>       name the killer and end the game
  quit                give up
"""


def _match(mystery: Mystery, text: str) -> CharacterId | None:
    """Find a suspect by any unambiguous prefix of their name or id."""
    text = text.lower()
    hits = [
        c.id
        for c in mystery.characters
        if c.id != mystery.victim
        and (c.id.startswith(text) or c.name.lower().split()[0].startswith(text))
    ]
    return hits[0] if len(hits) == 1 else None


def _notebook(
    mystery: Mystery, transcript: Transcript, knowledge: dict[CharacterId, Knowledge]
) -> str:
    names = {c.id: c.name for c in mystery.characters}
    times = {s.id: s.label for s in mystery.slots}
    places = {p.id: p.name for p in mystery.places}
    lines = []

    claims: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for statement in transcript.statements:
        for assertion in statement.assertions:
            claims.setdefault((assertion.subject, assertion.slot), []).append(
                (statement.speaker, assertion.place)
            )

    if claims:
        lines.append("  WHO WAS WHERE, according to whom")
        for (subject, slot), said in sorted(claims.items()):
            for speaker, place in said:
                source = "themselves" if speaker == subject else names.get(speaker, speaker)
                lines.append(
                    f"    {names.get(subject, subject):18} {times.get(slot, slot):8} "
                    f"{places.get(place, place):18} ({source})"
                )

    found = transcript.contradictions()
    if found:
        lines.append("")
        lines.append("  CONTRADICTIONS")
        for c in found:
            kind = "changed their story" if c.is_self_contradiction else "disagree"
            lines.append(
                f"    {names.get(c.subject, c.subject)} at {times.get(c.slot, c.slot)}: "
                f"{names.get(c.first[0], c.first[0])} says "
                f"{places.get(c.first[1], c.first[1])}, "
                f"{names.get(c.second[0], c.second[0])} says "
                f"{places.get(c.second[1], c.second[1])}  [{kind}]"
            )

    leads = transcript.leads(mystery, knowledge)

    holes = {
        (x.claimant, x.slot, x.place, x.silent_witness) for x in leads if x.witness_has_spoken
    }
    if holes:
        lines.append("")
        lines.append("  ACCOUNTS THAT DO NOT LINE UP")
        for claimant, slot, place, witness in sorted(holes):
            lines.append(
                f"    {names.get(claimant, claimant)} says {places.get(place, place)} at "
                f"{times.get(slot, slot)}, but {names.get(witness, witness)} described "
                f"that room then and did not mention them"
            )

    unasked = {
        (x.claimant, x.slot, x.place, x.silent_witness)
        for x in leads
        if not x.witness_has_spoken
    }
    if unasked:
        lines.append("")
        lines.append("  NOBODY HAS CONFIRMED  (worth asking)")
        for claimant, slot, place, witness in sorted(unasked):
            lines.append(
                f"    {names.get(claimant, claimant)} says "
                f"{places.get(place, place)} at {times.get(slot, slot)}. "
                f"Ask {names.get(witness, witness)}"
            )

    return "\n".join(lines) or "  (nothing yet)"


def _reveal(mystery: Mystery, transcript: Transcript, accused: CharacterId) -> None:
    names = {c.id: c.name for c in mystery.characters}
    places = {p.id: p.name for p in mystery.places}
    times = {s.id: s.label for s in mystery.slots}
    right = accused == mystery.killer

    print("\n" + ("CORRECT." if right else "WRONG."))
    print(f"The killer was {names.get(mystery.killer, mystery.killer)}.")
    print(f"Questions asked: {transcript.rounds}\n")

    motive = next(
        (s for s in mystery.secrets if s.holder == mystery.killer and s.is_motive),
        next((s for s in mystery.secrets if s.holder == mystery.killer), None),
    )
    if motive:
        print(f"  Why: {motive.summary}")

    if mystery.false_claim:
        claim = mystery.false_claim
        truth = mystery.placements.get(claim.character, {}).get(claim.slot)
        print(
            f"  The lie: {names.get(claim.character, claim.character)} claimed the "
            f"{places.get(claim.place, claim.place)} at {times.get(claim.slot, claim.slot)}. "
            f"They were in the {places.get(truth, truth)}."
        )

    analysis = analyse_alibi(mystery, derive(mystery))
    if analysis.contradictors:
        print("\n  Who could have broken it, and whether you asked them:")
        for person in analysis.contradictors:
            asked = transcript.asked(person)
            mark = f"asked {asked}x" if asked else "never asked"
            print(f"    {names.get(person, person):20} {mark}")

    print("\n  Secrets you never found:")
    surfaced = {a.subject for s in transcript.statements for a in s.assertions}
    for secret in mystery.secrets:
        if secret.holder not in surfaced:
            print(f"    {names.get(secret.holder, secret.holder)}: {secret.summary}")


def run(mystery: Mystery, responder: Responder, show_leaks: bool = False) -> None:
    knowledge = derive(mystery)
    briefs: dict[CharacterId, Brief] = {
        c.id: build_brief(mystery, knowledge, c.id)
        for c in mystery.characters
        if c.id != mystery.victim
    }
    names = {c.id: c.name for c in mystery.characters}
    transcript = Transcript()

    print(f"\n{mystery.title}\n")
    print(f"  {names.get(mystery.victim, mystery.victim)} is dead.")
    print("  Everyone below was present. One of them did it.\n")
    for character in mystery.characters:
        if character.id != mystery.victim:
            print(f"    {character.name:22} {character.wants}")
    print(HELP)

    round_number = 0
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not line:
            continue
        if line in ("quit", "q"):
            return
        if line in ("help", "?"):
            print(HELP)
            continue
        if line == "cast":
            for character in mystery.characters:
                if character.id != mystery.victim:
                    print(f"  {character.name:22} {character.manner}")
            continue
        if line == "notebook":
            print(_notebook(mystery, transcript, knowledge))
            continue
        if line.startswith("accuse"):
            who = _match(mystery, line[6:].strip())
            if who is None:
                print("  Who?")
                continue
            _reveal(mystery, transcript, who)
            return

        who, _, question = line.partition(" ")
        target = _match(mystery, who)
        if target is None or not question.strip():
            print("  Say a suspect's name, then your question.")
            continue

        round_number += 1
        brief = briefs[target]
        reply: Reply = ask(brief, question.strip(), responder)

        print(f"\n  {names[target]}: {reply.speech}\n")

        if show_leaks and (found := leaks(brief, reply)):
            for problem in found:
                print(f"  [leak] {problem}")

        transcript.record(
            Statement(
                round=round_number,
                speaker=target,
                question=question.strip(),
                speech=reply.speech,
                assertions=assertions_from(brief, reply),
                refused=reply.refused,
                cited=list(reply.used),
            )
        )
