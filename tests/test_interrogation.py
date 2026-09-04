"""Tests for the contradiction tracker.

The tracker is the difference between an interrogation and a reading exercise.
In the paper playtest the case broke open because two conflicting claims landed
in adjacent rows of a table; the same claims eleven messages apart in prose would
probably have been missed. These tests pin down what it catches and, just as
importantly, what it deliberately leaves to the player (D-019).
"""

from test_agent import CASE, KNOW

from mystery.agent import Reply, build_brief
from mystery.interrogation import Assertion, Statement, Transcript, assertions_from
from mystery.knowledge import derive


def _said(round_: int, speaker: str, *assertions, refused: bool = False) -> Statement:
    return Statement(
        round=round_,
        speaker=speaker,
        question="?",
        speech="...",
        assertions=[Assertion(*a) for a in assertions],
        refused=refused,
    )


def test_a_reply_is_reduced_to_what_it_committed_the_speaker_to() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    reply = Reply(speech="The study, with Vera.", used=["self:s1", "saw:vera@s1"])

    assert set(assertions_from(clara, reply)) == {
        Assertion("clara", "s1", "study"),
        Assertion("vera", "s1", "study"),
    }


def test_uncited_prose_is_invisible_to_the_tracker() -> None:
    """A stated limitation, not an oversight. Same boundary as the leak detector."""
    clara = build_brief(CASE, KNOW, "clara")
    reply = Reply(speech="Otto was in the cellar, I am certain of it.", used=[])

    assert assertions_from(clara, reply) == []


def test_a_concealed_fact_cannot_become_an_assertion() -> None:
    """Otto's real location is not among his citable facts, so even if he cited
    it the tracker would not record him placing himself in the cellar."""
    otto = build_brief(CASE, KNOW, "otto")

    assert assertions_from(otto, Reply(speech="", used=["truth:s2"])) == []


def test_two_people_disagreeing_about_one_person_is_a_contradiction() -> None:
    """The killer's lie, caught. Otto says the hall; Clara puts him elsewhere."""
    transcript = Transcript()
    transcript.record(_said(1, "otto", ("otto", "s2", "hall")))
    transcript.record(_said(2, "clara", ("otto", "s2", "cellar")))

    found = transcript.contradictions()

    assert len(found) == 1
    assert found[0].subject == "otto"
    assert found[0].first == ("otto", "hall")
    assert found[0].second == ("clara", "cellar")
    assert not found[0].is_self_contradiction


def test_changing_your_own_story_is_caught_as_a_self_contradiction() -> None:
    transcript = Transcript()
    transcript.record(_said(1, "vera", ("vera", "s1", "study")))
    transcript.record(_said(4, "vera", ("vera", "s1", "hall")))

    found = transcript.contradictions()

    assert len(found) == 1
    assert found[0].is_self_contradiction


def test_agreement_is_not_a_contradiction() -> None:
    transcript = Transcript()
    transcript.record(_said(1, "clara", ("vera", "s1", "study")))
    transcript.record(_said(2, "vera", ("vera", "s1", "study")))

    assert transcript.contradictions() == []


def test_a_claim_nobody_has_confirmed_is_a_lead_not_a_contradiction() -> None:
    """The heart of D-019.

    Otto claims the hall at s2. Clara and Vera were both in the hall and neither
    has mentioned him. That is suggestive and it is not evidence, because they
    may simply never have been asked. Deciding whether to press them is the game.
    """
    transcript = Transcript()
    transcript.record(_said(1, "otto", ("otto", "s2", "hall")))

    assert transcript.contradictions() == []

    leads = transcript.leads(CASE, derive(CASE))
    silent = {lead.silent_witness for lead in leads}

    assert silent == {"clara", "vera"}


def test_a_confirmed_claim_stops_being_a_lead() -> None:
    """Once somebody corroborates, there is nothing left to chase."""
    transcript = Transcript()
    transcript.record(_said(1, "vera", ("vera", "s1", "study")))
    transcript.record(_said(2, "clara", ("vera", "s1", "study")))

    assert transcript.leads(CASE, derive(CASE)) == []


def test_the_transcript_counts_what_the_player_has_spent() -> None:
    """Questions asked is the score, so the transcript has to be able to say."""
    transcript = Transcript()
    transcript.record(_said(1, "otto"))
    transcript.record(_said(2, "otto"))
    transcript.record(_said(3, "vera", refused=True))

    assert transcript.rounds == 3
    assert transcript.asked("otto") == 2
    assert transcript.asked("clara") == 0


def test_a_witness_who_described_the_room_without_you_is_a_stronger_lead() -> None:
    """The mechanism that broke the hand-built case.

    Otto claims the hall. Clara then describes the hall at that moment, names
    Vera, and does not mention Otto. Her silence has stopped meaning "nobody
    asked" and started meaning "her account and his cannot both be complete".
    """
    transcript = Transcript()
    transcript.record(_said(1, "otto", ("otto", "s2", "hall")))
    transcript.record(_said(2, "clara", ("clara", "s2", "hall"), ("vera", "s2", "hall")))

    against_otto = [
        lead
        for lead in transcript.leads(CASE, derive(CASE))
        if lead.claimant == "otto" and lead.silent_witness == "clara"
    ]

    assert len(against_otto) == 1
    assert against_otto[0].witness_has_spoken


def test_a_witness_who_has_said_nothing_is_only_worth_asking() -> None:
    """Vera has not been questioned at all, so her silence is not evidence."""
    transcript = Transcript()
    transcript.record(_said(1, "otto", ("otto", "s2", "hall")))

    against_otto = [
        lead
        for lead in transcript.leads(CASE, derive(CASE))
        if lead.silent_witness == "vera"
    ]

    assert len(against_otto) == 1
    assert not against_otto[0].witness_has_spoken


def test_a_retraction_reaches_the_notebook() -> None:
    """D-064. A liar who comes clean has to move the timeline, or the admission
    is a nice sentence the game never heard."""
    from mystery.agent import Brief, Fact

    brief = Brief(
        character="vera",
        name="Vera",
        facts=[Fact(id="self:s1", text="the hall", subject="vera", slot="s1", place="hall")],
        guarded=[Fact(id="truth:s1", text="the study", subject="vera", slot="s1", place="study")],
    )

    assertions = assertions_from(brief, Reply(speech="All right. The study.", used=["truth:s1"]))

    assert assertions == [Assertion(subject="vera", slot="s1", place="study")]


# What the house has been saying (D-099)


def _house():
    from mystery.models import Character, Mystery, Place, Secret, Slot

    return Mystery(
        title="the house",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "a", "b")],
        places=[Place(id="hall", name="Hall")],
        slots=[Slot(id="s0", label="20:00", index=0)],
        secrets=[
            Secret(id="hers", holder="a", summary="A owes money.", known_by=["b"]),
            Secret(id="his", holder="b", summary="B was dismissed.", known_by=[]),
        ],
    )


def _cited(speaker: str, cited: list[str]) -> Statement:
    return Statement(round=1, speaker=speaker, question="?", speech="", cited=cited)


def test_everyone_hears_who_has_been_questioned() -> None:
    """Visible from a corridor, and it gives nothing away."""
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    log.record(_cited("a", []))

    heard = word_got_back(log, case, derive(case), "b")

    assert any("questioning A" in line for line in heard)
    assert not any("questioning B" in line for line in heard), "not your own questioning"


def test_you_are_told_when_your_own_secret_is_already_out() -> None:
    """The line half of every generated break condition is waiting for."""
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    log.record(_cited("b", ["heard:hers"]))

    heard = word_got_back(log, case, derive(case), "a")

    assert any("did not come from you" in line and "A owes money" in line for line in heard)


def test_a_secret_you_do_not_know_never_reaches_you() -> None:
    """The safety argument. Gossip can only carry what its listener already
    holds, so nothing here can put a secret into a brief that did not have it,
    and the closure that decides winnability is untouched."""
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    log.record(_cited("b", ["secret:his"]))

    heard = word_got_back(log, case, derive(case), "a")

    assert not any("dismissed" in line for line in heard), "A has never heard of it"


def test_you_are_not_told_about_what_you_said_yourself() -> None:
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    log.record(_cited("a", ["secret:hers"]))

    heard = word_got_back(log, case, derive(case), "a")

    assert not any("owes money" in line for line in heard)


def test_a_long_evening_does_not_arrive_as_a_wall_of_recap() -> None:
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    for _ in range(12):
        log.record(_cited("b", ["heard:hers"]))

    heard = word_got_back(log, case, derive(case), "a")

    assert len(heard) <= 8, heard


def test_the_house_notices_somebody_being_taken_apart() -> None:
    """The player has no authority, so the only thing they spend is how they are
    seen, and until now nobody saw them at all (D-100)."""
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    for _ in range(7):
        log.record(_cited("a", []))

    heard = word_got_back(log, case, derive(case), "b")

    assert any("taken A apart" in line for line in heard)
    assert any("not asked you anything" in line for line in heard)


def test_a_short_evening_gets_no_character_reading() -> None:
    """Two questions in, nobody has formed a view of anything."""
    from mystery.interrogation import word_got_back
    from mystery.knowledge import derive

    case = _house()
    log = Transcript()
    log.record(_cited("a", []))

    heard = word_got_back(log, case, derive(case), "b")

    assert not any("apart" in line or "oversight" in line for line in heard)


# --- a contradiction is a property, not an event (D-133) ---------------------


def _claim(round_, speaker, subject, slot, place):
    return Statement(
        round=round_,
        speaker=speaker,
        question="where were you",
        speech="...",
        assertions=[Assertion(subject=subject, slot=slot, place=place)],
    )


def test_repeating_a_contradiction_does_not_add_a_new_one() -> None:
    """From play: the count climbed every time somebody restated a position they
    had already taken. Asking twice cannot make the house more inconsistent."""
    t = Transcript()
    t.record(_claim(1, "gerald", "maud", "s4", "gallery"))
    for n in range(2, 12):
        t.record(_claim(n, "maud", "maud", "s4", "library"))

    assert len(t.contradictions()) == 1


def test_the_same_disagreement_from_either_side_is_one_disagreement() -> None:
    t = Transcript()
    t.record(_claim(1, "gerald", "maud", "s4", "gallery"))
    t.record(_claim(2, "maud", "maud", "s4", "library"))
    t.record(_claim(3, "gerald", "maud", "s4", "gallery"))

    assert len(t.contradictions()) == 1


def test_a_third_person_with_a_third_answer_is_a_new_disagreement() -> None:
    t = Transcript()
    t.record(_claim(1, "gerald", "maud", "s4", "gallery"))
    t.record(_claim(2, "maud", "maud", "s4", "library"))
    t.record(_claim(3, "sidney", "maud", "s4", "chapel"))

    assert len(t.contradictions()) == 3, "each pair genuinely disagrees"


def test_a_third_person_agreeing_adds_nothing() -> None:
    t = Transcript()
    t.record(_claim(1, "gerald", "maud", "s4", "gallery"))
    t.record(_claim(2, "maud", "maud", "s4", "library"))
    t.record(_claim(3, "sidney", "maud", "s4", "library"))

    assert len(t.contradictions()) == 2, "sidney disagrees with gerald and nobody else"


def test_changing_your_own_story_still_counts() -> None:
    """The loudest kind, and the one that must survive the deduplication."""
    t = Transcript()
    t.record(_claim(1, "maud", "maud", "s4", "library"))
    t.record(_claim(2, "maud", "maud", "s4", "gallery"))

    found = t.contradictions()

    assert len(found) == 1
    assert found[0].is_self_contradiction


def test_changing_back_is_not_a_third_contradiction() -> None:
    t = Transcript()
    t.record(_claim(1, "maud", "maud", "s4", "library"))
    t.record(_claim(2, "maud", "maud", "s4", "gallery"))
    t.record(_claim(3, "maud", "maud", "s4", "library"))

    assert len(t.contradictions()) == 1


def test_agreeing_with_yourself_is_never_a_contradiction() -> None:
    t = Transcript()
    for n in range(1, 8):
        t.record(_claim(n, "maud", "maud", "s4", "library"))

    assert t.contradictions() == []


# --- the ledger (D-140) ------------------------------------------------------


def _spoke(who: str, question: str, speech: str, claims=(), cited=(), refused=False):
    return Statement(
        round=0,
        speaker=who,
        question=question,
        speech=speech,
        assertions=[Assertion(subject=s, slot=t, place=p) for s, t, p in claims],
        cited=list(cited),
        refused=refused,
    )


def test_a_held_story_is_one_line_not_ten() -> None:
    """The point of the ledger. A suspect who says the same thing ten times has
    committed to one thing, and the prompt used to carry all ten answers."""
    t = Transcript()
    for _ in range(10):
        t.record(_spoke("vera", "Where were you?", "The study.", [("vera", "s1", "study")]))

    lines = t.ledger(CASE, "vera")

    assert len([x for x in lines if "study" in x.lower()]) == 1


def test_the_version_they_are_standing_on_is_the_one_that_binds() -> None:
    """Latest wins. That they moved is the notebook's business; what they are
    committed to now is theirs."""
    t = Transcript()
    t.record(_spoke("vera", "Where?", "The study.", [("vera", "s1", "study")]))
    t.record(_spoke("vera", "Really?", "The hall.", [("vera", "s1", "hall")]))

    lines = t.ledger(CASE, "vera")

    assert any("Hall" in x for x in lines)
    assert not any("Study" in x for x in lines)


def test_what_they_said_about_other_people_is_in_it_too() -> None:
    t = Transcript()
    t.record(_spoke("vera", "Who else?", "Otto was there.", [("otto", "s1", "hall")]))

    assert any(x.startswith("You have said Otto was") for x in t.ledger(CASE, "vera"))


def test_a_secret_is_named_rather_than_repeated_in_full() -> None:
    """It is already in their brief. Printing the whole summary again is paying
    twice for the same sentence."""
    t = Transcript()
    t.record(_spoke("vera", "And?", "Yes, alright.", cited=["secret:affair"]))

    told = [x for x in t.ledger(CASE, "vera") if x.startswith("You have already told them")]

    assert len(told) == 1
    assert len(told[0]) < 200


def test_refusals_are_counted_and_answers_are_not() -> None:
    """The live block already says which question this is, and says it better."""
    t = Transcript()
    t.record(_spoke("vera", "Well?", "No.", refused=True))
    t.record(_spoke("vera", "Well?", "Still no.", refused=True))

    lines = t.ledger(CASE, "vera")

    assert any("refused to answer 2 times" in x for x in lines)
    assert not any("answered" in x for x in lines)


def test_somebody_who_has_not_spoken_has_no_ledger() -> None:
    assert Transcript().ledger(CASE, "vera") == []
