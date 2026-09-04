"""Objects with paths of their own (D-131).

The second falsifiable axis. Until this existed every claim the game could check
reduced to *person, place, slot*: one grid, one kind of lie, one kind of
contradiction, and a notebook that was a spreadsheet with a story printed beside
it. A thing that moves is evidence nobody has to lie for.
"""

from mystery.agent import build_brief
from mystery.critique import not_every_journey_points_at_the_killer as a23
from mystery.critique import something_in_this_house_moved as a21
from mystery.example import OPENING_NIGHT
from mystery.knowledge import derive
from mystery.models import Mystery, Thing

CASE = Mystery.model_validate(OPENING_NIGHT)
SLOTS = [s.id for s in sorted(CASE.slots, key=lambda s: s.index)]


def _with(thing: Thing) -> Mystery:
    return CASE.model_copy(update={"things": [thing]})


def _head(**kw) -> Thing:
    """A stone head that starts in the green room and ends by the body."""
    where = dict.fromkeys(SLOTS[:3], "green_room") | dict.fromkeys(SLOTS[3:], "prop_store")
    return Thing(
        id="head",
        name="stone head of a newel post",
        where=where,
        moved_by={SLOTS[3]: "wouter"},
        matters="It was carried down the stair.",
        **kw,
    )


# --- the path ----------------------------------------------------------------


def test_a_thing_that_moves_knows_it_moved() -> None:
    assert _head().moves == 1
    assert Thing(id="x", name="a lamp", where=dict.fromkeys(SLOTS, "green_room")).moves == 0


def test_only_the_people_in_the_room_saw_it() -> None:
    """Co-location, exactly as it works for people, and for the same reason: it
    is the part that must never be invented."""
    mystery = _with(_head())
    knowledge = derive(mystery)

    seen = {
        who: {s.slot for s in knowledge[who].sightings}
        for who in ("ilse", "tomas", "wouter")
    }

    assert seen["ilse"] == set(), "she was never in a room with it"
    assert seen["tomas"], "he was in the green room while it sat there"


def test_the_person_who_carried_it_saw_it_in_both_rooms() -> None:
    """The whole mechanic. They are implicated by an object's path without ever
    lying about their own whereabouts."""
    mystery = _with(_head())
    knowledge = derive(mystery)

    places = {s.place for s in knowledge["wouter"].sightings}

    assert places == {"green_room", "prop_store"}


def test_a_sighting_becomes_a_citable_fact() -> None:
    mystery = _with(_head())
    knowledge = derive(mystery)

    brief = build_brief(mystery, knowledge, "wouter")
    facts = [f for f in brief.facts if f.id.startswith("thing:")]

    assert facts
    assert all(f.subject == "head" for f in facts)
    assert {f.place for f in facts} == {"green_room", "prop_store"}
    assert "the stone head of a newel post" in facts[0].text, "one article, not two"


def test_a_thing_nobody_shared_a_room_with_is_in_nobody_s_facts() -> None:
    """The hard line covers objects too: no fact, no knowledge, no statement."""
    lonely = Thing(id="ring", name="a signet ring", where=dict.fromkeys(SLOTS, "lighting_box"))
    mystery = _with(lonely)
    knowledge = derive(mystery)

    for character in mystery.characters:
        walked = mystery.placements.get(character.id, {})
        if any(walked.get(slot) == "lighting_box" for slot in SLOTS):
            continue
        assert not [
            f for f in build_brief(mystery, knowledge, character.id).facts
            if f.id.startswith("thing:ring")
        ]


def test_an_object_fact_reaches_the_notebook_as_a_row() -> None:
    """A thing's path is reconstructed from testimony exactly the way a person's
    is, so the grid that shows one has to show the other."""
    from mystery.agent import Reply
    from mystery.interrogation import assertions_from

    mystery = _with(_head())
    knowledge = derive(mystery)
    brief = build_brief(mystery, knowledge, "wouter")
    cited = [f.id for f in brief.facts if f.id.startswith("thing:")][:2]

    made = assertions_from(brief, Reply(speech="It was on the post.", used=cited))

    assert [a.subject for a in made] == ["head", "head"]


def test_the_notebook_names_the_thing_rather_than_its_id() -> None:
    from mystery.solver import solve
    from mystery.web import Case, Game

    game = Game(Case(solve(_with(_head()), seed=0), id="things"), lambda s, q: {})

    assert game.names["head"] == "stone head of a newel post"


# --- A21 ----------------------------------------------------------------------


def test_a_case_with_no_objects_is_flagged() -> None:
    assert [a.check for a in a21(CASE)] == ["A21"]


def test_a_thing_that_never_moves_is_furniture() -> None:
    still = Thing(id="lamp", name="a brass lamp", where=dict.fromkeys(SLOTS, "green_room"))

    said = a21(_with(still))

    assert said and "not one of them moves" in said[0].message


def test_a_journey_nobody_witnessed_convicts_nobody() -> None:
    unseen = Thing(
        id="ghost",
        name="a folded note",
        where=dict.fromkeys(SLOTS[:3], "lighting_box") | dict.fromkeys(SLOTS[3:], "stage_door"),
    )
    mystery = _with(unseen)
    # Nobody is in both of those rooms across that boundary in the example case.
    said = a21(mystery)

    assert not said or "convicts nobody" in said[0].message or "narrows nothing" in said[0].message


def test_a_good_object_passes() -> None:
    assert a21(_with(_head())) == []


# --- not every journey points at the killer (A23, D-136) ---------------------


def _letters(mover: str) -> Thing:
    """A second thing, carried by whoever the test needs."""
    where = dict.fromkeys(SLOTS[:2], "dressing_corridor") | dict.fromkeys(
        SLOTS[2:], "lighting_box"
    )
    return Thing(
        id="letters",
        name="a bundle of letters",
        where=where,
        moved_by={SLOTS[2]: mover},
        matters="They were taken out of the corridor.",
    )


def test_one_object_carried_by_the_killer_is_a_signpost() -> None:
    """The failure A23 exists for. A21 asks for a thing that moves and for its
    journey to be watched by only one or two people, which on its own describes
    an arrow pointing at the killer."""
    said = a23(_with(_head()))
    assert said
    assert "shorter road" in said[0].message


def test_a_second_journey_by_somebody_innocent_clears_it() -> None:
    case = CASE.model_copy(update={"things": [_head(), _letters("ilse")]})
    assert not a23(case)


def test_two_things_both_carried_by_the_killer_still_fails() -> None:
    case = CASE.model_copy(update={"things": [_head(), _letters("wouter")]})
    assert a23(case)


def test_nothing_moves_is_a21s_problem_not_a23s() -> None:
    """Two checks, two jobs. A house where nothing travels is already reported
    once, and reporting it twice teaches the drafter nothing new."""
    still = Thing(id="x", name="a lamp", where=dict.fromkeys(SLOTS, "green_room"))
    assert not a23(_with(still))
    assert a21(_with(still))


# --- objects are off the notebook (D-139) ------------------------------------


def test_an_object_claim_never_reaches_the_grid() -> None:
    """Things stayed in the case and in the briefs, so a suspect can still say
    where the bangle was. They are off the notebook because a player cannot ask
    about a thing they do not know exists, so the axis never started a thread:
    five citations in seventy-one questions on the case that retired it."""
    from mystery.web import Game

    case = CASE.model_copy(update={"things": [_head()]})
    ids: list[str] = []

    def responder(system, question):
        text = "".join(system) if isinstance(system, list) else system
        ids[:] = [
            line.split("]")[0].split("[")[1]
            for line in text.splitlines()
            if line.strip().startswith("[")
        ]
        return {
            "speech": "The head was on the newel post.",
            "used": [i for i in ids if i.startswith("thing:")][:2],
            "refused": False,
        }

    from mystery.knowledge import derive

    know = derive(case)
    witness = next(c.id for c in case.characters if know[c.id].sightings)
    game = Game(case, responder)
    game.ask(witness, "What was in the green room?")

    assert any(i.startswith("thing:") for i in ids), "the brief still licenses it"
    assert game.transcript.statements[0].cited, "and the answer still cites it"
    book = game.notebook()
    assert book["timeline"] == {}
    assert book["grid"] == []
    for page in book["people"]:
        assert page["told"] == []
