"""The killer's earlier lie (D-207): a second lie, at an hour before the
murder, that can be broken and points somewhere else when it is."""

from mystery.example import OPENING_NIGHT
from mystery.models import FalseClaim, Mystery

# wouter killed bram at s3; at s1 wouter was in the green room.
EARLIER = FalseClaim(
    character="wouter",
    place="stage_door",
    slot="s1",
    covers="the_theft",
    admits_when="somebody says they saw him in the green room before the curtain",
)


def _case(*extra: FalseClaim) -> Mystery:
    m = Mystery.model_validate(OPENING_NIGHT)
    return m.model_copy(update={"false_claims": [*m.false_claims, *extra]})


def _v8(m: Mystery) -> list[str]:
    from mystery.validator import check_false_claims_are_false

    return [v.message for v in check_false_claims_are_false(m)]


def test_the_killer_may_tell_two_lies_at_two_hours() -> None:
    assert _v8(_case(EARLIER)) == []


def test_not_two_about_one_hour_and_not_three() -> None:
    same = EARLIER.model_copy(update={"slot": "s3", "place": "stage_door"})
    assert _v8(_case(same))
    third = EARLIER.model_copy(update={"slot": "s0", "place": "green_room"})
    assert _v8(_case(EARLIER, third))


def test_an_innocent_still_tells_one() -> None:
    twice = FalseClaim(character="nadia", place="green_room", slot="s3", covers="the_promise")
    assert _v8(_case(twice))


def test_the_case_still_turns_on_the_lie_about_the_murder_hour() -> None:
    assert _case(EARLIER).false_claim.slot == "s3"


def test_the_earlier_lie_can_be_broken_and_the_murder_hour_cannot() -> None:
    from mystery.agent import build_brief
    from mystery.knowledge import derive

    m = _case(EARLIER)
    brief = build_brief(m, derive(m), "wouter")
    guarded = {f.id: f.text for f in brief.guarded}
    concealed = {f.id for f in brief.conceals}
    assert "truth:s1" in guarded and "own up to being there" in guarded["truth:s1"]
    assert "truth:s3" in concealed


def test_dealt_a_third_of_the_time_never_to_an_honest_killer() -> None:
    from mystery.palette import earlier_lie

    seeds = range(500_000, 503_000)
    share = sum(earlier_lie(s, "the_lie") for s in seeds) / len(seeds)
    assert 0.28 < share < 0.38
    assert not any(earlier_lie(s, t) for s in seeds for t in ("the_frame", "the_finder"))


def test_a_dealt_earlier_lie_that_is_missing_is_sent_back(monkeypatch) -> None:
    import mystery.measures
    from mystery.generator import GenerationRequest, _earlier_complaints
    from mystery.palette import earlier_lie

    monkeypatch.setattr(mystery.measures, "GATE", {"dealt_objects": 1})
    seed = next(s for s in range(500_000, 501_000) if earlier_lie(s, "the_lie"))
    request = GenerationRequest(setting="a theatre", seed=seed, topology="the_lie")
    assert any("not there" in c for c in _earlier_complaints(_case(), request))
