"""How a case plays, as numbers (D-186)."""

from test_agent import CASE

from mystery.measures import NORMAL, measure


def test_the_fixture_is_full_of_shortcuts() -> None:
    """Otto is alone with Magnus at the murder hour, is the only one there the
    hour before, and is the only liar. Every trick names him."""
    m = measure(CASE, "the_lie")
    assert {"alone", "last_with", "lies_at_hour", "only_liar"} <= set(m.shortcuts)
    assert not m.meets()


def test_a_shape_that_hides_a_shortcut_does_not_count_it() -> None:
    """Mutual alibi gives the killer a false witness for the hour, so "who was
    alone" is not a question the player can ask of it."""
    assert "alone" in measure(CASE, "the_lie").shortcuts
    assert "alone" not in measure(CASE, "mutual_alibi").shortcuts


def test_the_field_needs_a_reason_and_a_chance() -> None:
    """Both secrets marked damning: Vera and Otto have a reason, but at the
    murder hour Vera was in the hall with Clara and told the truth about it, so
    only Otto also had the chance."""
    marked = CASE.model_copy(
        update={"secrets": [s.model_copy(update={"damning": True}) for s in CASE.secrets]}
    )
    m = measure(marked, "the_lie")
    assert (m.reason, m.field, m.killer_in_field) == (2, 1, True)


def test_normal_asks_for_a_choice_and_no_tricks() -> None:
    assert NORMAL["field"] >= 3 and NORMAL["shortcuts"] == 0


# --- where the killer stands (D-188) -------------------------------------------


def _example():
    from mystery.example import OPENING_NIGHT
    from mystery.models import Mystery

    return Mystery.model_validate(OPENING_NIGHT)


def test_a_case_dealt_no_position_is_not_measured() -> None:
    from mystery.measures import position_landed

    case = _example().model_copy(update={"killer_position": ""})
    assert position_landed(case) is None
    assert position_landed(case.model_copy(update={"killer_position": "mourner"})) is None


def test_the_shipped_example_reads_as_an_outsider_and_a_small_sinner() -> None:
    """Wouter holds the theft (lesser, open from the start) and the motive, and
    is tied to one other suspect, as few as anyone and fewer than Renske."""
    from mystery.measures import position_landed

    case = _example()
    landed = {
        p: position_landed(case.model_copy(update={"killer_position": p}))
        for p in ("hub", "outsider", "clean_hands", "small_sinner")
    }
    assert landed == {"hub": False, "outsider": True, "clean_hands": False, "small_sinner": True}


def test_clean_hands_means_the_motive_is_all_they_hold() -> None:
    from mystery.measures import position_landed

    case = _example()
    killer = case.killer
    only_motive = case.model_copy(
        update={
            "killer_position": "clean_hands",
            "secrets": [s for s in case.secrets if s.holder != killer or s.is_motive],
        }
    )
    assert position_landed(only_motive) is True


# --- the room the body was found in, and objects (D-193) -------------------------


def _shipped():
    from mystery.example import OPENING_NIGHT
    from mystery.models import Mystery
    from mystery.solver import solve

    return solve(Mystery.model_validate(OPENING_NIGHT))


def test_an_honest_killer_in_the_room_the_body_was_found_is_a_shortcut() -> None:
    """Telling no lie about the hour of the killing is saying you were where it
    happened, and where the body was found is the one thing everybody is told."""
    case = _shipped()
    honest = case.model_copy(
        update={"false_claims": [c for c in case.false_claims if c.character != case.killer]}
    )
    assert "found_room" not in measure(case, "the_lie").shortcuts, "the liar names elsewhere"
    assert "found_room" in measure(honest, "the_frame").shortcuts


def test_a_body_carried_next_door_is_not_that_shortcut() -> None:
    from mystery.models import Discovery

    case = _shipped()
    honest = case.model_copy(
        update={
            "false_claims": [c for c in case.false_claims if c.character != case.killer],
            "discovery": Discovery(finder="tomas", place="stage_door"),
            "moved_body": True,
        }
    )
    assert honest.body_moved and honest.found_in == "stage_door"
    assert "found_room" not in measure(honest, "the_frame").shortcuts


def test_half_the_gates_open_with_an_object_and_the_key_roads_have_one() -> None:
    case = _shipped()
    m = measure(case, "the_lie")
    assert m.gates == 3 and m.argued == 0 and m.objects_met(NORMAL)
    bare = case.model_copy(
        update={"secrets": [s.model_copy(update={"evidence": None}) for s in case.secrets]}
    )
    stripped = measure(bare, "the_lie")
    assert not stripped.objects_met(NORMAL)
    assert not stripped.motive_object and not stripped.trail_object
    from mystery.measures import complaints

    assert any("open with an object" in c for c in complaints(stripped, NORMAL))


def test_the_deepest_complaint_says_how_deep() -> None:
    """D-205: the redraft is told the two depths, and that level is fine."""
    from mystery.measures import Measures, complaints

    m = Measures(shortcuts=["deepest"], killer_depth=5, innocent_depth=3)
    said = complaints(m, {"field": 0, "shortcuts": 0, "motive": 0, "trail": 0,
                          "liars_at_hour": 0})
    assert any("5 gates deep" in c and "innocent's is 3" in c and "level is fine" in c
               for c in said)
