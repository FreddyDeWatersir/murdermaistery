"""Who could have moved it (D-202).

An object the killer moved out of a room only the killer was ever seen in
names the killer without a word of testimony, which is what the Oath's
stylus-case did. The measure counts everybody who could have taken it.
"""

from mystery.example import OPENING_NIGHT
from mystery.models import Mystery, Thing

BASE = Mystery.model_validate(OPENING_NIGHT)  # wouter killed bram in the prop store at s3


def _with(*things: Thing) -> Mystery:
    return BASE.model_copy(update={"things": list(things)})


def test_an_object_only_the_killer_could_have_moved_counts_one() -> None:
    from mystery.measures import NORMAL, measure, mover_complaints, possible_movers

    knife = Thing(
        id="knife",
        name="the prop knife",
        where={
            "s0": "prop_store",
            "s1": "prop_store",
            "s2": "prop_store",
            "s3": "prop_store",
            "s4": "green_room",
        },
        moved_by={"s4": "wouter"},
    )
    m = _with(knife)
    assert [len(x.could) for x in possible_movers(m)] == [1]
    assert measure(m).movers == [1]
    assert not measure(m).movers_met(NORMAL)
    said = mover_complaints(m, NORMAL)
    assert len(said) == 1 and "Wouter" in said[0] and "at least 2" in said[0]


def test_somebody_else_through_the_room_makes_two() -> None:
    from mystery.measures import NORMAL, measure

    hat = Thing(
        id="hat",
        name="a hat",
        where={"s0": "stage_door", "s1": "green_room"},
        moved_by={"s1": "wouter"},
    )
    m = _with(hat)
    assert measure(m).movers == [2]  # wouter, and nadia at the door at s1
    assert measure(m).movers_met(NORMAL)
    assert not measure(m).movers_met({"movers": 3})


def test_a_witness_who_saw_it_there_closes_the_window_behind_them() -> None:
    """The window opens at the last time somebody other than its mover saw it.
    Tomas sees the cup at s2 and is still there at s3, when wouter is not: so
    wouter, in the room at s1 and s2, could not have been the one."""
    from mystery.measures import possible_movers

    cup = Thing(
        id="cup",
        name="a cup",
        where={"s1": "green_room", "s2": "green_room", "s3": "prop_store"},
        moved_by={"s3": "wouter"},
    )
    assert possible_movers(_with(cup)) == []


def test_a_move_the_killer_could_not_have_made_is_not_counted() -> None:
    from mystery.measures import possible_movers

    scarf = Thing(
        id="scarf",
        name="a scarf",
        where={"s0": "dressing_corridor", "s1": "stage_door"},
        moved_by={"s1": "nadia"},
    )
    assert possible_movers(_with(scarf)) == []


def test_an_object_that_names_the_killer_is_sent_back_then_kept(monkeypatch) -> None:
    """Soft (D-202): every draft is told, and the last one is kept rather than
    the case being thrown away."""
    from test_generator import REQUEST, _staged

    import mystery.measures
    from mystery.generator import SKELETON_ATTEMPTS, _bare, generate

    monkeypatch.setattr(mystery.measures, "GATE", {**mystery.measures.GATE, "movers": 2})
    knife = Thing(
        id="knife",
        name="the prop knife",
        where={
            "s0": "prop_store",
            "s1": "prop_store",
            "s2": "prop_store",
            "s3": "prop_store",
            "s4": "green_room",
        },
        moved_by={"s4": "wouter"},
    )
    drafter = _staged([_bare(_with(knife))])
    case = generate(REQUEST, drafter=drafter)

    calls = drafter.calls["skeleton"]
    assert len(calls) == SKELETON_ATTEMPTS
    assert any("prop knife" in c or "`knife`" in c for c in calls[1][0])
    assert [t.id for t in case.things] == ["knife"]
