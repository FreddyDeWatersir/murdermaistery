"""Tests for the generator.

Not one of these calls a model. The whole point of keeping the model boundary as
a plain callable is that a fake can stand in its place, so the suite runs
offline, free, and in milliseconds. If testing this needed an API key, it would
stop being run.
"""

import json

import pytest
from mystery.generator import GenerationFailed, GenerationRequest, generate
from mystery.models import Mystery
from mystery.validator import validate

GOOD_DRAFT = {
    "title": "The Private View",
    "characters": [
        {"id": "roos", "name": "Roos"},
        {"id": "gustav", "name": "Gustav"},
        {"id": "lelia", "name": "Lelia"},
        {"id": "mihail", "name": "Mihail"},
    ],
    "places": [
        {"id": "main_hall", "name": "Main Hall"},
        {"id": "storeroom", "name": "Storeroom"},
        {"id": "courtyard", "name": "Courtyard"},
    ],
    "slots": [
        {"id": "s1", "label": "20:00", "index": 0},
        {"id": "s2", "label": "20:30", "index": 1},
        {"id": "s3", "label": "21:00", "index": 2},
    ],
    "constraints": [
        {
            "id": "tryst",
            "people": ["roos", "gustav"],
            "exclusive": True,
            "description": "Roos and Gustav slip away.",
        },
        {
            "id": "murder",
            "people": ["lelia", "mihail"],
            "exclusive": True,
            "description": "Lelia kills Mihail.",
        },
    ],
}


def _fake_drafter(payload: dict):
    """A stand-in for the model that returns whatever you hand it."""

    def draft(_request: GenerationRequest, _complaints: list[str]) -> dict:
        return payload

    return draft


def _flaky_drafter(*payloads: dict):
    """Returns each payload in turn, so a retry can be observed.

    Also records the complaints it was handed on each call, which is what the
    retry tests actually assert on: not that it retried, but that it was told
    what was wrong.
    """
    calls: list[list[str]] = []
    queue = list(payloads)

    def draft(_request: GenerationRequest, complaints: list[str]) -> dict:
        calls.append(list(complaints))
        return queue.pop(0) if queue else payloads[-1]

    draft.calls = calls
    return draft


REQUEST = GenerationRequest(setting="a gallery private view", cast_size=3, slot_count=3)


def test_a_draft_is_parsed_into_typed_objects() -> None:
    mystery = generate(REQUEST, drafter=_fake_drafter(GOOD_DRAFT))

    assert isinstance(mystery, Mystery)
    assert {c.id for c in mystery.characters} == {"roos", "gustav", "lelia", "mihail"}


def test_a_good_proposal_passes_proposal_validation() -> None:
    mystery = generate(REQUEST, drafter=_fake_drafter(GOOD_DRAFT))

    assert validate(mystery, phase="proposed").ok


def test_a_model_that_never_fixes_itself_eventually_fails_loudly() -> None:
    """The failure a model actually makes.

    Asked for a cast and then for constraints about them, a model will refer to
    a character by a name it did not define. Only the model can fix that, so it
    is retried, and if it still cannot, the error names the problem.
    """
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0]["people"] = ["roos", "the_butler"]

    with pytest.raises(GenerationFailed) as caught:
        generate(REQUEST, drafter=_fake_drafter(invented), attempts=2)

    assert "the_butler" in str(caught.value)


def test_a_rejected_draft_is_retried_with_the_reason_attached() -> None:
    """The point of the loop. The model is told what was wrong, in the same
    words a person would have read."""
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0]["people"] = ["roos", "the_butler"]

    drafter = _flaky_drafter(invented, GOOD_DRAFT)
    mystery = generate(REQUEST, drafter=drafter)

    assert isinstance(mystery, Mystery)
    assert drafter.calls[0] == [], "the first attempt should carry no complaints"
    assert any("the_butler" in c for c in drafter.calls[1])


def test_an_unparseable_payload_is_retried_with_the_pydantic_errors() -> None:
    """Observed in the wild: a response missing half its required fields."""
    drafter = _flaky_drafter({"title": "half a mystery"}, GOOD_DRAFT)

    generate(REQUEST, drafter=drafter)

    assert any("characters" in c for c in drafter.calls[1])


def test_a_degenerate_wrapper_is_unwrapped_rather_than_retried() -> None:
    """Also observed: the whole mystery returned under a stray key.

    Cheaper to unwrap than to pay for another call.
    """
    drafter = _flaky_drafter({"$PARAMETER_NAME": GOOD_DRAFT})

    mystery = generate(REQUEST, drafter=drafter)

    assert mystery.title == "The Private View"
    assert len(drafter.calls) == 1, "unwrapping should not have cost a retry"


def test_a_failed_draft_is_not_cached(tmp_path) -> None:
    """Caching a broken draft would make the failure permanent for that seed."""
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0]["people"] = ["roos", "the_butler"]

    with pytest.raises(GenerationFailed):
        generate(REQUEST, drafter=_fake_drafter(invented), cache_dir=tmp_path, attempts=1)

    assert not list(tmp_path.iterdir())


def test_a_proposal_with_a_broken_exclusive_room_is_repaired() -> None:
    """The failure a model actually makes when it writes the grid.

    Everything is coherent except that a third person is standing in the murder
    room. The repairer moves that one person and leaves the rest of the story
    where the model put it.
    """
    from mystery.solver import solve

    proposal = json.loads(json.dumps(GOOD_DRAFT))
    # Both constraints are bound, so nothing needs rescheduling and any movement
    # in the result is the repairer's doing rather than a side effect.
    proposal["constraints"][0].update({"place": "courtyard", "slot": "s3"})
    proposal["constraints"][1].update({"place": "storeroom", "slot": "s2"})
    proposal["placements"] = {
        "roos": {"s1": "main_hall", "s2": "main_hall", "s3": "courtyard"},
        "gustav": {"s1": "main_hall", "s2": "main_hall", "s3": "courtyard"},
        "lelia": {"s1": "main_hall", "s2": "storeroom", "s3": "main_hall"},
        "mihail": {"s1": "courtyard", "s2": "storeroom", "s3": "main_hall"},
        # Roos should not be in the murder room. She is the only thing wrong.
    }
    proposal["placements"]["roos"]["s2"] = "storeroom"

    fixed = solve(generate(REQUEST, drafter=_fake_drafter(proposal)), seed=1)

    assert validate(fixed).ok, validate(fixed).violations
    assert fixed.who_is_in("storeroom", "s2") == {"lelia", "mihail"}
    # Everything the model chose that did not break a rule is untouched.
    assert fixed.placements["gustav"]["s1"] == "main_hall"
    assert fixed.placements["mihail"]["s3"] == "main_hall"


def test_a_proposed_grid_is_kept_when_it_is_already_correct() -> None:
    """The whole point of the repair path. A clean proposal survives intact."""
    from mystery.solver import solve

    proposal = json.loads(json.dumps(GOOD_DRAFT))
    proposal["constraints"][0].update({"place": "courtyard", "slot": "s1"})
    proposal["constraints"][1].update({"place": "storeroom", "slot": "s3"})
    proposal["placements"] = {
        "roos": {"s1": "courtyard", "s2": "main_hall", "s3": "main_hall"},
        "gustav": {"s1": "courtyard", "s2": "main_hall", "s3": "main_hall"},
        "lelia": {"s1": "main_hall", "s2": "main_hall", "s3": "storeroom"},
        "mihail": {"s1": "main_hall", "s2": "main_hall", "s3": "storeroom"},
    }

    before = generate(REQUEST, drafter=_fake_drafter(proposal))
    after = solve(before, seed=1)

    assert validate(after).ok, validate(after).violations
    assert after.placements == before.placements, "a correct proposal was altered"


def test_the_cache_is_written_and_then_read_instead_of_the_model(tmp_path) -> None:
    """The corpus costs money once.

    `tmp_path` is a pytest fixture: a fresh empty directory per test, cleaned up
    afterwards. It is how you test anything touching the filesystem without
    leaving debris or having tests interfere with each other.
    """
    calls = []

    def counting_drafter(request: GenerationRequest, _complaints: list[str]) -> dict:
        calls.append(request)
        return GOOD_DRAFT

    first = generate(REQUEST, drafter=counting_drafter, cache_dir=tmp_path)
    second = generate(REQUEST, drafter=counting_drafter, cache_dir=tmp_path)

    assert len(calls) == 1, "the second call should have come from disk"
    assert first.model_dump() == second.model_dump()


def test_a_different_request_is_a_different_cache_entry(tmp_path) -> None:
    calls = []

    def counting_drafter(request: GenerationRequest, _complaints: list[str]) -> dict:
        calls.append(request)
        return GOOD_DRAFT

    generate(REQUEST, drafter=counting_drafter, cache_dir=tmp_path)
    generate(
        REQUEST.model_copy(update={"seed": 99}), drafter=counting_drafter, cache_dir=tmp_path
    )

    assert len(calls) == 2


def test_a_generated_mystery_survives_the_whole_pipeline() -> None:
    """Draft, solve, validate. The spine, end to end, with a fake model."""
    from mystery.solver import solve

    draft = generate(REQUEST, drafter=_fake_drafter(GOOD_DRAFT))
    assert validate(draft, phase="proposed").ok

    solved = solve(draft, seed=1)
    result = validate(solved)

    assert result.ok, result.violations


def test_who_kills_whom_is_decided_here_not_by_the_model() -> None:
    """Every case came out with a man killing a man (D-074). Two independent
    bits off the seed, so all four combinations happen across a run of seeds."""
    from mystery.generator import _casting

    seen = {(("woman" in _casting(s).split("victim")[0]),
             ("woman" in _casting(s).split("victim")[1])) for s in range(4)}

    assert len(seen) == 4, "all four castings must appear in the first four seeds"


def test_the_casting_note_reaches_the_prompt() -> None:
    from mystery.generator import GenerationRequest, _user_prompt

    assert "the killer is a woman" in _user_prompt(GenerationRequest(setting="x", seed=1))
    assert "the killer is a man" in _user_prompt(GenerationRequest(setting="x", seed=0))
