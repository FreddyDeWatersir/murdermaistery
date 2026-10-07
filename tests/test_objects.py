"""The object deck (D-203): what objects are for, dealt per case."""

from mystery.example import OPENING_NIGHT
from mystery.models import Mystery, Thing
from mystery.palette import NOT_YET_DEALT, SCENE_ROLES, object_hand, scene_object

SEEDS = range(500_009, 502_009)


def test_residue_always_three_or_four_and_nothing_undealable() -> None:
    for seed in SEEDS:
        held = object_hand(seed)
        assert held[0] == "residue"
        assert 3 <= len(held) <= 4
        assert len(set(held)) == len(held)
        assert not set(held) & NOT_YET_DEALT


def test_the_killers_trace_and_the_red_herring_come_about_half_the_time() -> None:
    hands = [object_hand(s) for s in SEEDS]
    for role in ("killer_trace", "misleading"):
        share = sum(role in h for h in hands) / len(hands)
        assert 0.4 < share < 0.6, (role, share)


def test_what_lies_with_the_body_is_from_the_hand_or_nothing() -> None:
    scenes = set()
    for seed in SEEDS:
        scene = scene_object(seed)
        scenes.add(scene)
        assert scene == "nothing" or (scene in object_hand(seed) and scene in SCENE_ROLES)
    assert "nothing" in scenes and "misleading" in scenes


def test_the_request_deals_the_objects() -> None:
    from mystery.generator import GenerationRequest, _user_prompt

    request = GenerationRequest(setting="a monastery in the snow", seed=500_010)
    text = _user_prompt(request)
    assert "THE OBJECTS, dealt" in text
    for role in object_hand(500_010):
        assert f"`{role}`" in text


def _case_for(seed: int, things: list[Thing]) -> Mystery:
    return Mystery.model_validate(OPENING_NIGHT).model_copy(update={"things": things})


def test_objects_that_do_not_play_their_roles_are_sent_back(monkeypatch) -> None:
    import mystery.measures
    from mystery.generator import GenerationRequest, _object_complaints

    monkeypatch.setattr(mystery.measures, "GATE", {"dealt_objects": 1})
    seed = next(s for s in SEEDS if scene_object(s) == "nothing")
    request = GenerationRequest(setting="a theatre", seed=seed)

    wrong = _case_for(
        seed,
        [
            Thing(
                id="ash",
                name="ash",
                role="residue",
                where={"s0": "green_room", "s1": "prop_store"},
                moved_by={"s1": "tomas"},
            )
        ],
    )
    said = " ".join(_object_complaints(wrong, request))
    assert "they were dealt" in said
    assert "residue does not move" in said


def test_a_third_of_the_gates_now() -> None:
    from mystery.measures import NORMAL

    assert NORMAL["objects"] == 33
