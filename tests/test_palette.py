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


# --- the occasion is dealt too (D-115) ---------------------------------------


def test_omitting_the_setting_does_not_give_the_same_evening_forever() -> None:
    """`--setting` defaulted to a fixed string, so every case nobody named a
    setting for was a private view at the same small art gallery. It was the one
    input to a case that was never dealt, and the largest one (D-115)."""
    from mystery.palette import occasion

    drawn = {occasion(seed) for seed in range(20)}

    assert len(drawn) > 8, f"twenty seeds, only {len(drawn)} occasions"


def test_an_occasion_reproduces_from_its_seed() -> None:
    from mystery.palette import occasion

    assert occasion(11) == occasion(11)


def test_every_occasion_survives_the_setting_guard() -> None:
    """A drawn occasion goes straight into the generator, so it must pass the
    check that refuses a placeholder (D-110)."""
    from mystery.generator import complaint_about_setting
    from mystery.palette import OCCASIONS

    for line in OCCASIONS:
        assert complaint_about_setting(line) is None, line


def test_the_entry_points_no_longer_default_to_a_gallery() -> None:
    import mystery.cli as cli
    import mystery.web as web

    for module in (cli, web):
        source = __import__("inspect").getsource(module)
        assert "default=\"a private view at a small art gallery\"" not in source


# --- how they sound (D-127) --------------------------------------------------


def test_the_cast_is_dealt_voices_as_well_as_manners() -> None:
    """Two played cases, different casts, different countries, different
    centuries: 531 and 612 characters an answer, 21.0 and 20.6 words a sentence,
    two em-dashes an answer in both. One person in twelve costumes."""
    from mystery.palette import draw

    hand = draw(11, "a residency", "the_lie", cast_size=5)

    assert len(hand.voices) == 5
    assert len(set(hand.voices)) == 5, "two suspects were dealt the same voice"


def test_voice_and_manner_are_independent() -> None:
    """A blunt three-word answerer can still be the one who answers for
    everybody else. They vary on different axes and must not be one deck."""
    from mystery.palette import MANNERS, VOICES

    assert not set(MANNERS) & set(VOICES)
    assert len(VOICES) >= 12, "a deck this short repeats within a week"


def test_the_voices_reach_the_prompt_as_an_assignment() -> None:
    from mystery.palette import draw

    brief = draw(3, "a gallery", "the_lie").brief()

    assert "how they each sound" in brief
    assert "same careful literate register" in brief


def test_a_voice_is_a_shape_of_sentence_not_a_character() -> None:
    """The D-075 rule the whole module exists for: hand over behaviours, never
    characters, or every case is the same five people in different coats."""
    from mystery.palette import VOICES

    for voice in VOICES:
        assert not any(
            word in voice.lower() for word in ("young", "old man", "woman who", "nervous assistant")
        ), voice


# --- what they asked you for (D-129) -----------------------------------------


def test_the_commission_is_sometimes_wrong() -> None:
    """A commission that is always accurate is a briefing you can trust flatly,
    which makes it furniture. Two in five wrong is often enough to matter and
    rare enough that trusting it is not stupid."""
    from mystery.palette import commission

    wrong = sum(0 if commission(s)[1] else 1 for s in range(400))

    assert 0.25 < wrong / 400 < 0.55


def test_every_commission_knows_how_it_can_be_wrong() -> None:
    from mystery.palette import COMMISSIONS

    for brief, wrong in COMMISSIONS:
        assert brief.strip() and wrong.strip()
        assert len(wrong.split()) > 4, f"{brief[:40]}: no usable failure mode"


def test_a_commission_reproduces_from_its_seed() -> None:
    from mystery.palette import commission

    assert commission(17) == commission(17)


def test_the_clock_varies_per_case_and_stays_playable() -> None:
    """A cap nobody reaches creates no scarcity; a cap that always bites is just
    a shorter game. Two real evenings ran to 132 and 106 (D-129)."""
    from mystery.palette import questions

    drawn = {questions(s) for s in range(200)}

    assert len(drawn) >= 6, "one number is a setting, not a property of a case"
    assert min(drawn) >= 40, "an evening nobody can finish is not tense, it is broken"
    assert max(drawn) >= 130, "most nights should have more time than anybody needs"
