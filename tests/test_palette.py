"""Tests for the material each case is dealt.

What is being protected is variety across a *run* of cases, which is not a
property any single case has, so these tests look at sequences (D-075).
"""

from mystery.palette import INTRIGUES, MANNERS, MOTIVES, draw


def test_the_same_case_is_dealt_the_same_hand_twice() -> None:
    """Or a cached case and a fresh one would not match."""
    assert draw(3, "a theatre", "the_lie") == draw(3, "a theatre", "the_lie")


def test_different_seeds_are_dealt_different_hands() -> None:
    motives = {draw(s, "a theatre", "the_lie").motive for s in range(12)}

    assert len(motives) >= 8, "twelve cases should not keep killing for one reason"


def test_the_same_seed_in_a_different_house_is_a_different_hand() -> None:
    """Otherwise every seed 0 case anybody ever runs shares a motive."""
    theatre = draw(0, "a theatre", "the_lie")
    salt = draw(0, "a salt works", "the_lie")

    assert (theatre.motive, theatre.manners) != (salt.motive, salt.manners)


def test_nobody_in_a_cast_gets_the_same_manner_twice() -> None:
    hand = draw(7, "a wedding", "the_lie", cast_size=5)

    assert len(set(hand.manners)) == len(hand.manners) == 5


def test_a_large_cast_does_not_run_out() -> None:
    hand = draw(1, "a conference", "the_lie", cast_size=99)

    assert len(hand.manners) == len(MANNERS)


def test_everything_dealt_reaches_the_brief() -> None:
    hand = draw(2, "a theatre", "the_lie")
    brief = hand.brief()

    assert hand.motive in brief
    assert all(m in brief for m in hand.manners)
    assert all(i in brief for i in hand.intrigues)


def test_the_material_is_behaviour_rather_than_people() -> None:
    """A list of characters would hand over the cast. A list of behaviours can
    belong to a bishop or a bouncer, and leaves the writing to be done."""
    everything = MANNERS + MOTIVES + INTRIGUES

    assert all(len(entry) < 120 for entry in everything)
    assert len(set(everything)) == len(everything), "no duplicates to skew the draw"


def test_the_prompt_carries_this_case_and_not_the_list() -> None:
    """The model must never see the whole set, or it acquires favourites."""
    from mystery.generator import GenerationRequest, _user_prompt

    prompt = _user_prompt(GenerationRequest(setting="a theatre", seed=4))
    present = [m for m in MANNERS if m in prompt]

    assert len(present) == 5, "five manners in, twenty eight kept back"
