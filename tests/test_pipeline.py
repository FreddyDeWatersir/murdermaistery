"""One test that runs the whole chain, from a raw model response to a verdict.

Every other test file checks one component against a hand-built fixture. That is
the right shape for finding out *why* something is broken and it is the wrong
shape for finding out *whether* the thing works, which is a different question
and the one nobody was asking. The browser game went a week without ever calling
the advisories, and not one of a hundred and fifty passing tests noticed,
because each of them was holding its own piece up to the light (D-070).

So this file holds the piece nobody else does: the seams. Raw dict to parsed
mystery, mystery to solved grid, grid to briefs, briefs to answers, answers to a
notebook, notebook to an accusation. No model and no network: the drafter is the
case shipped in `example.py` and the responder is a function that cites facts.
"""

from mystery.agent import build_brief, leaks
from mystery.example import OPENING_NIGHT
from mystery.generator import GenerationRequest, generate
from mystery.knowledge import derive
from mystery.solvable import analyse, why_not
from mystery.solver import solve
from mystery.topology import assess
from mystery.validator import validate
from mystery.web import Game

REQUEST = GenerationRequest(
    setting="an Amsterdam theatre on opening night", cast_size=5, slot_count=5, place_count=5
)


def _drafter(request, complaints):
    return OPENING_NIGHT


def _case():
    return solve(generate(REQUEST, drafter=_drafter), seed=0)


# --- generation to a playable case ------------------------------------------


def test_the_shipped_case_survives_the_whole_pipeline() -> None:
    case = _case()

    assert validate(case).ok, validate(case).violations
    assert analyse(case).winnable
    assert not why_not(case), "the case shipped with the code must be solvable"


def test_every_suspect_gets_a_brief_with_something_in_it() -> None:
    case = _case()
    knowledge = derive(case)

    for character in case.characters:
        if character.id == case.victim:
            continue
        brief = build_brief(case, knowledge, character.id)
        assert brief.facts, f"{character.id} has nothing to say"
        assert brief.name


def test_the_solver_moved_the_killers_lie_somewhere_it_can_be_caught() -> None:
    """The model put Wouter's alibi in a room with one person in it. Two are
    needed, so the solver moved it (D-063), and the case is playable because of
    a repair rather than because the draft was right."""
    case = _case()
    lie = case.false_claim

    witnesses = case.who_is_in(lie.place, lie.slot) - {lie.character, case.victim}
    assert len(witnesses) >= 2
    assert case.placements[lie.character][lie.slot] != lie.place


# --- playing it -------------------------------------------------------------


def _cites_everything(system, question):
    """Answer with every fact id the brief offered, which is the worst case for
    the leak detector and the best case for filling a notebook."""
    ids = [
        line.strip()[1:].split("]")[0]
        for line in system.splitlines()
        if line.strip().startswith("[")
    ]
    return {"speech": "Here is everything.", "used": ids, "refused": False}


def test_a_full_round_of_questions_leaks_nothing_and_fills_the_notebook() -> None:
    case = _case()
    game = Game(case, _cites_everything)

    for character in case.characters:
        if character.id != case.victim:
            game.ask(character.id, "Tell me about the evening.")
            assert leaks(game.briefs[character.id], _reply_of(game, character.id)) == []

    book = game.notebook()
    assert book["timeline"], "nobody ended up anywhere"
    assert book["found"], "no secret came out of five people saying everything they had"


def _reply_of(game, who):
    from mystery.agent import Reply

    statement = next(s for s in reversed(game.transcript.statements) if s.speaker == who)
    return Reply(speech=statement.speech, used=statement.cited)


def test_the_case_can_be_won_and_can_be_lost() -> None:
    case = _case()
    game = Game(case, _cites_everything)

    # Renske knows why he did it. Nobody else can tell you, because he never will.
    game.ask("renske", "Why would anybody want him dead?")
    won = game.accuse("wouter", "the_reckoning")

    assert won["correct"] and won["right_reason"]

    lost = Game(case, _cites_everything).accuse("tomas", None)
    assert not lost["correct"]


# --- the checks actually run ------------------------------------------------


def test_a_sabotaged_case_is_caught_rather_than_served() -> None:
    """What the browser game now refuses to start (D-068). Cut the one route to
    the motive and the case becomes unwinnable without a single rule failing."""
    case = _case()
    sealed = case.model_copy(
        update={
            "secrets": [
                s.model_copy(update={"known_by": []}) if s.is_motive else s
                for s in case.secrets
            ]
        }
    )

    assert validate(sealed).ok, "still perfectly valid, which is the point"
    assert not analyse(sealed).winnable
    assert "S3" in {a.check for a in assess(sealed)}
