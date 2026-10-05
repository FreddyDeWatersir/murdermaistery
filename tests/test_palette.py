"""Tests for the material each case is dealt.

What is being protected is variety across a *run* of cases, which is not a
property any single case has, so these tests look at sequences (D-075).
"""

from mystery.models import Mystery
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


def test_the_murder_is_never_earlier_than_the_third_slot() -> None:
    """The victim can only appear at or before the murder, so the murder slot is
    also the size of his life (D-158).

    Dealing from slot 2 gave him two hours on a five hour evening, while the
    request asks for a private scene with the killer, usually an earlier one with
    the same pair, and a victim who was working on all of them tonight. Measured
    over the corpus the model writes 3.56 scenes with him and does not reduce that
    when the murder is early, so a quarter of all draws were unsatisfiable before
    the model had written a word.
    """
    from mystery.palette import murder_slot

    dealt = {murder_slot(seed, 5) for seed in range(4000)}
    assert dealt == {3, 4, 5}, "slot 2 leaves the victim two hours and no case"


def test_the_murder_is_still_not_always_near_the_end() -> None:
    """The thing D-125 bought, which this must not give back: a murder that is
    always in the last hour or two is answerable by asking who lies about the
    last hour or two."""
    from mystery.palette import murder_slot

    dealt = [murder_slot(seed, 5) for seed in range(4000)]
    assert 0.25 < dealt.count(3) / len(dealt) < 0.42, (
        "the earliest allowed slot should still come up about a third of the time"
    )


def test_a_short_evening_still_gets_a_legal_slot() -> None:
    """The floor is min(3, slot_count), so a three slot evening returns 3 rather
    than an empty range."""
    from mystery.palette import murder_slot

    for slots in (2, 3, 4, 6):
        for seed in range(50):
            assert 1 <= murder_slot(seed, slots) <= slots


def test_the_motives_are_not_all_the_same_sentence() -> None:
    """Twenty six real cases were read back and twenty four were one plot: the
    victim announces a deadline and the killer removes it (D-161).

    The deck was half the cause. Nineteen of its twenty entries were some form of
    "the victim was about to take something away or say something out loud", so
    whatever the model was dealt, it wrote the same evening.
    """
    from mystery.palette import MOTIVES

    deadline = ("about to", "was going to", "in the morning", "next week", "on Monday")
    prospective = [m for m in MOTIVES if any(word in m for word in deadline)]

    assert len(prospective) / len(MOTIVES) < 0.5, (
        "more than half the motives are still a thing that has not happened yet"
    )


def test_the_motives_cover_more_than_money_and_exposure() -> None:
    """The registers the engine had never once produced in forty drafts."""
    from mystery.palette import MOTIVES

    deck = " ".join(MOTIVES)
    for feeling in ("love", "grief", "cruel", "conviction", "affair", "die"):
        assert feeling in deck, f"nothing in the deck is about {feeling}"


def test_the_old_business_is_not_all_somebody_s_guilt() -> None:
    """Twelve entries and eleven were a thing somebody concealed, so every cast
    came out as colleagues managing an exposure (D-168).

    The prompt asks this deck for what gives them reasons to know about each
    other rather than only about the victim, and knowing each other has never
    required having covered something up together.
    """
    from mystery.palette import OLD_BUSINESS

    guilt = (
        "recorded as an accident", "went missing", "who was blamed",
        "read by more people", "never named", "signed by the wrong person",
        "withdrawn under pressure", "who was told what", "only half of them have kept",
        "whose name is not used",
    )
    concealed = [o for o in OLD_BUSINESS if any(word in o for word in guilt)]

    assert len(concealed) / len(OLD_BUSINESS) <= 0.6, (
        "the deck can only produce a group that covered something up"
    )


def test_a_commission_does_not_say_who_engaged_the_player() -> None:
    """Two decks were independently answering "why are you here" (D-169).

    Six of the eight commissions asserted who sent for the player or what
    brought them to the building, which is what STANDINGS is for, and the two are
    dealt from separate streams. So a case could be told it was hired by a
    frightened letter-writer and also that it was halfway through an unrelated
    survey.
    """
    import re

    from mystery.palette import COMMISSIONS

    hiring = re.compile(
        r"wrote to you|sent for you|paid for you|engaged|brought you|"
        r"you came|you did not come|you were already here",
        re.I,
    )
    trespassing = [brief for brief, _ in COMMISSIONS if hiring.search(brief)]

    assert not trespassing, f"the commission is writing the standing: {trespassing}"


def test_the_prompt_keeps_the_two_apart() -> None:
    from mystery.generator import GenerationRequest, _commission

    asked = _commission(GenerationRequest(setting="a harvest", seed=657043))

    assert "who engaged the player" in asked


def test_every_hand_carries_one_intrigue_that_could_end_somebody() -> None:
    """Weighed by what it would cost the holder, the old deck was 3 heavy, 7
    damaging and 14 merely awkward, so three sampled flat were usually three
    embarrassments (D-170).

    A red herring has to be something a reader would write a name down about, so
    a deck that cannot supply one leaves the model inventing motive-grade
    material for the innocents from nothing.
    """
    from mystery.palette import WEIGHTY, draw

    for seed in range(60):
        hand = draw(seed, "a vigil that has run long", "the_lie", 5)
        assert len(hand.intrigues) == 3
        assert sum(1 for i in hand.intrigues if i in WEIGHTY) >= 1


def test_a_hand_is_not_three_heavy_ones() -> None:
    """Five people whose lives are all ending tonight is melodrama, and flat in
    a new way: the texture comes from obstructions of different sizes."""
    from mystery.palette import WEIGHTY, draw

    hands = [draw(seed, "a dig packing up early", "the_frame", 5) for seed in range(60)]

    assert max(sum(1 for i in h.intrigues if i in WEIGHTY) for h in hands) <= 2


def test_every_intrigue_is_something_its_holder_could_conceal() -> None:
    """Two entries could not be secrets at all: one whose holder does not know it
    ("about to be replaced and is the only person who does not know") and one
    nobody hides ("a job was given to the wrong person and everybody knows
    which"). The prompt asks for each to become a secret with a holder."""
    from mystery.palette import INTRIGUES

    assert not [i for i in INTRIGUES if "the only person who does not know" in i]
    assert not [i for i in INTRIGUES if "a job was given to the wrong person" in i]


def test_the_brief_says_the_first_one_is_the_heavy_one() -> None:
    from mystery.palette import draw

    brief = draw(3, "a memorial swim", "the_lie", 5).brief()

    assert "first of the three is heavier" in brief


def test_a_batch_makes_n_drafts_whatever_the_buffer_holds(monkeypatch, tmp_path) -> None:
    """`--fill 8` with seventeen cases waiting correctly did nothing at all: it
    tops *up to* a target, which is right for a buffer and wrong for statistics
    (D-172). A corpus is not full because the queue is.
    """
    import mystery.cli as cli
    from mystery.example import OPENING_NIGHT

    asked: list[int] = []

    def spy(request, drafter, cache_dir=None, attempts=3):
        asked.append(request.seed)
        return Mystery.model_validate(OPENING_NIGHT)

    monkeypatch.setattr(cli, "generate", spy)
    monkeypatch.setattr(cli, "anthropic_drafter", lambda *a, **kw: (lambda r, c: {}))
    monkeypatch.setattr(cli, "CACHE", tmp_path)

    assert cli.main(["--drafts", "4", "--seed", "500"]) == 0
    assert asked == [500, 501, 502, 503]


def test_a_batch_varies_the_occasion_and_the_shape(monkeypatch, tmp_path) -> None:
    """The reason to buy a batch is mostly to see what the decks do, so a batch
    at one occasion measures nothing (D-163, D-166)."""
    import mystery.cli as cli
    from mystery.example import OPENING_NIGHT

    seen: list[tuple[str, str]] = []

    def spy(request, drafter, cache_dir=None, attempts=3):
        seen.append((request.setting, request.topology))
        return Mystery.model_validate(OPENING_NIGHT)

    monkeypatch.setattr(cli, "generate", spy)
    monkeypatch.setattr(cli, "anthropic_drafter", lambda *a, **kw: (lambda r, c: {}))
    monkeypatch.setattr(cli, "CACHE", tmp_path)

    cli.main(["--drafts", "10", "--seed", "900"])

    assert len({s for s, _ in seen}) > 3, "ten drafts at one occasion measure nothing"
    assert len({t for _, t in seen}) > 2, "and one shape is one puzzle"


def test_a_batch_waits_out_an_overloaded_api(monkeypatch, tmp_path) -> None:
    """Six of eight drafts made, then "Overloaded" on the seventh ended the run
    and threw away the eighth, three dollars in (D-174).

    Nothing was charged for the failure, because the call did not happen. The
    only cost of giving up was the drafts that never got made.
    """
    import mystery.cli as cli
    from mystery.example import OPENING_NIGHT

    tries: list[int] = []

    def flaky(request, drafter, cache_dir=None, attempts=3):
        tries.append(request.seed)
        if tries.count(request.seed) == 1:
            raise RuntimeError("Error code: 529 - {'type': 'overloaded_error'}")
        return Mystery.model_validate(OPENING_NIGHT)

    monkeypatch.setattr(cli, "generate", flaky)
    monkeypatch.setattr(cli, "anthropic_drafter", lambda *a, **kw: (lambda r, c: {}))
    monkeypatch.setattr(cli, "CACHE", tmp_path)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    assert cli.main(["--drafts", "3", "--seed", "10"]) == 0
    assert sorted(set(tries)) == [10, 11, 12], "every seed should still get drafted"


def test_a_batch_does_not_wait_out_a_missing_key(monkeypatch, tmp_path) -> None:
    """No key and no such model will not be different in twenty seconds, and
    retrying them costs money the second time."""
    import mystery.cli as cli

    calls: list[int] = []

    def refused(request, drafter, cache_dir=None, attempts=3):
        calls.append(request.seed)
        raise RuntimeError("No ANTHROPIC_API_KEY found")

    monkeypatch.setattr(cli, "generate", refused)
    monkeypatch.setattr(cli, "anthropic_drafter", lambda *a, **kw: (lambda r, c: {}))
    monkeypatch.setattr(cli, "CACHE", tmp_path)
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)

    assert cli.main(["--drafts", "4", "--seed", "20"]) == 1
    assert calls == [20], "it should stop on the first one, not try all four"


# --- Other worlds (D-182) ---------------------------------------------------


def test_about_three_cases_in_ten_are_in_another_world() -> None:
    from mystery.palette import world

    share = sum(world(seed) is not None for seed in range(3000)) / 3000
    assert 0.25 < share < 0.35, share


def test_every_world_is_dealt_somewhere() -> None:
    from mystery.palette import WORLDS, world

    dealt = {w.key for seed in range(5000) if (w := world(seed)) is not None}
    assert dealt == {w.key for w in WORLDS}


def test_a_world_seed_is_dealt_one_of_that_worlds_own_occasions() -> None:
    from mystery.palette import occasion, world

    seed = next(s for s in range(1000) if world(s) is not None)
    assert occasion(seed) in world(seed).occasions


def test_every_world_occasion_survives_the_setting_guard() -> None:
    from mystery.generator import complaint_about_setting
    from mystery.palette import WORLDS

    for w in WORLDS:
        for line in w.occasions:
            assert complaint_about_setting(line) is None, line


def test_a_setting_somebody_typed_is_never_moved_into_another_world() -> None:
    from mystery.palette import world, world_for

    seed = next(s for s in range(1000) if world(s) is not None)
    assert world_for(seed, "a board stranded overnight by weather") is None
    assert world_for(seed, world(seed).occasions[0]) == world(seed)


def test_a_world_replaces_the_region_in_the_brief_and_says_who_is_coming() -> None:
    from mystery.palette import draw, world

    seed = next(s for s in range(1000) if world(s) is not None)
    w = world(seed)
    brief = draw(seed, w.occasions[0], "the_lie").brief()

    assert "not in the present day" in brief
    assert w.place in brief and w.authority in brief and w.silence in brief
    assert "Where on earth this house is" not in brief


def test_the_present_day_brief_is_unchanged_by_worlds() -> None:
    from mystery.palette import draw, world

    seed = next(s for s in range(1000) if world(s) is None)
    brief = draw(seed, "a wake, on the night before the will is read", "the_lie").brief()
    assert "Where on earth this house is" in brief
    assert "not in the present day" not in brief


def test_whoever_is_coming_reads_as_a_plural_after_the_page_says_the() -> None:
    """The page writes "{authority} are on their way", capitalised at the
    start of a sentence, so every entry is "the something", plural."""
    from mystery.palette import WORLDS

    for w in WORLDS:
        assert w.authority.startswith("the "), w.key
        assert w.silence.strip(), w.key


def test_a_world_case_keeps_its_own_colours_and_an_old_case_keeps_its_region() -> None:
    from mystery.palette import WORLDS, hues

    w = WORLDS[0]
    assert hues(12, w.key) == dict(zip(("warm", "cool", "bad"), w.hues, strict=True))
    # No key is how every case made before worlds arrives, and it must not
    # change colour because its seed would deal a world today.
    assert hues(12) == hues(12, "")
    assert hues(12, "no-such-world") == hues(12)


def test_world_keys_are_unique_and_colours_are_colours() -> None:
    import re

    from mystery.palette import WORLDS

    assert len({w.key for w in WORLDS}) == len(WORLDS)
    for w in WORLDS:
        assert all(re.fullmatch(r"#[0-9a-f]{6}", c) for c in w.hues), w.key


# --- what used to be left to the model (D-188) ---------------------------------


def test_the_age_and_the_title_form_are_dealt_and_in_the_brief() -> None:
    from mystery.palette import AGES, TITLE_FORMS, draw

    hand = draw(7, "a house", "the_lie")
    assert hand.old_business_age in AGES
    assert hand.title_form in TITLE_FORMS
    brief = hand.brief()
    assert f"It happened {hand.old_business_age}" in brief
    assert hand.title_form in brief


def test_every_age_and_title_form_turns_up_across_seeds() -> None:
    from mystery.palette import AGES, TITLE_FORMS, draw

    hands = [draw(s, "a house", "the_lie") for s in range(400)]
    assert {h.old_business_age for h in hands} == set(AGES)
    assert {h.title_form for h in hands} == set(TITLE_FORMS)


def test_every_position_is_dealt_across_seeds() -> None:
    from mystery.palette import POSITIONS, killer_position

    assert {killer_position(s) for s in range(200)} == set(POSITIONS)
    assert killer_position(41) == killer_position(41)
