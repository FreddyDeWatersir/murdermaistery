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


def test_the_player_gets_a_different_standing_from_a_different_seed() -> None:
    """Dealt for the same reason the manners are (D-105). Asked to invent
    somebody with a professional reason and no power, and shown one example, the
    model produced five insurance assessors in five consecutive cases."""
    from mystery.palette import STANDINGS, draw

    here = "a ferry crossing stopped in fog"
    drawn = {draw(n, here, "the_lie").standing for n in range(60)}

    assert len(drawn) > len(STANDINGS) // 2, "the deck is barely being used"
    assert drawn <= set(STANDINGS)


def test_the_standing_reaches_the_prompt() -> None:
    """A field nothing renders is the failure this project keeps having."""
    from mystery.palette import draw

    dealt = draw(7, "a lighthouse", "the_lie")

    assert dealt.standing in dealt.brief()
    assert "investigator" in dealt.brief()


def test_the_same_seed_still_deals_the_same_hand() -> None:
    from mystery.palette import draw

    here = "a lighthouse"
    assert draw(7, here, "the_lie") == draw(7, here, "the_lie")


# --- where on earth the house is (D-111) -------------------------------------


def test_the_same_setting_does_not_always_land_in_the_same_country() -> None:
    """Four settings in a row that sounded coastal and northern produced four
    Dutch casts. The setting says what the occasion is; this says where it is,
    and it is dealt from the seed alone so it varies even when the phrase does
    not (D-111)."""
    from mystery.palette import draw

    setting = "the last night of a residency at an old house"
    places = {draw(seed, setting, "the_lie").where for seed in range(12)}

    assert len(places) > 4, f"twelve seeds, one setting, only {len(places)} places"


def test_where_is_stable_for_one_seed() -> None:
    from mystery.palette import draw

    a = draw(7, "a ferry", "the_lie").where
    b = draw(7, "a ferry", "the_lie").where

    assert a == b and a


def test_the_place_reaches_the_brief_and_yields_to_a_named_setting() -> None:
    from mystery.palette import draw

    brief = draw(3, "a gallery", "the_lie").brief()

    assert "Where on earth this house is" in brief
    assert "that wins" in brief, "a setting that names a country must override it"
