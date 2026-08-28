"""Tests for the contradiction tracker.

The tracker is the difference between an interrogation and a reading exercise.
In the paper playtest the case broke open because two conflicting claims landed
in adjacent rows of a table; the same claims eleven messages apart in prose would
probably have been missed. These tests pin down what it catches and, just as
importantly, what it deliberately leaves to the player (D-019).
"""

from mystery.agent import Reply, build_brief
from mystery.interrogation import Assertion, Statement, Transcript, assertions_from
from mystery.knowledge import derive

from test_agent import CASE, KNOW


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
