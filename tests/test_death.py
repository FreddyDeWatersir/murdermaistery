"""The hour of death is a window, and hidden visits close it (D-206)."""

from mystery.example import OPENING_NIGHT
from mystery.models import FalseClaim, Mystery


def _case(**update) -> Mystery:
    return Mystery.model_validate(OPENING_NIGHT).model_copy(update=update)


def test_the_example_has_a_window_a_hidden_visit_and_a_lie_elsewhere() -> None:
    from mystery.measures import measure, time_of_death

    m = _case()
    death = time_of_death(m)
    assert death.hidden == {"tomas"}
    assert death.window >= 2
    assert measure(m, "the_lie").other_lies >= 1


def test_owning_up_to_the_visit_moves_last_seen_later() -> None:
    """Without Tomas's lie, the last hour anybody admits being with Bram is the
    one Tomas was hiding: the same, or later, never earlier."""
    from mystery.measures import time_of_death

    lying = time_of_death(_case())
    honest = time_of_death(
        _case(false_claims=[c for c in _case().false_claims if c.character != "tomas"])
    )
    order = [s.id for s in _case().slots]
    assert order.index(honest.last_seen) >= order.index(lying.last_seen)
    assert honest.hidden == set()


def test_the_killer_is_never_a_hidden_visit() -> None:
    from mystery.measures import time_of_death

    m = _case()
    claims = [*m.false_claims, FalseClaim(character="wouter", place="green_room", slot="s1")]
    assert "wouter" not in time_of_death(m.model_copy(update={"false_claims": claims})).hidden


def test_the_soft_numbers_are_said_and_never_fatal() -> None:
    from mystery.measures import SOFT, Measures, soft_complaints

    said = soft_complaints(
        _case(),
        Measures(other_lies=0, window=1, hidden_visits=0),
        {"other_lies": 1, "window": 2, "hidden_visits": 1},
    )
    assert len(said) == 3
    assert {"other_lies", "window", "hidden_visits"} <= set(SOFT)


def test_the_targets_ask_for_the_window() -> None:
    from mystery.generator import _targets
    from mystery.measures import NORMAL

    text = _targets("the_lie", NORMAL)
    assert "a window, not an hour" in text and "hidden visit" in text.lower()
