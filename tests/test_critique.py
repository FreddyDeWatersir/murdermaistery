"""Tests for the quality advisories.

These assert that an advisory fires, not that a threshold is right. The
thresholds are judgement calls and no test can settle them; what the tests
protect is that the measurement itself works, so the judgement stays arguable
instead of invisible.
"""

from mystery.critique import count_moves, critique
from mystery.models import Character, Constraint, Mystery, Place, Slot

PLACES = [Place(id=p, name=p.title()) for p in ("hall", "study", "garden")]
SLOTS = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(4)]


def _case(placements, constraints, **kw) -> Mystery:
    people = sorted(placements)
    return Mystery(
        title="Test",
        killer=kw.pop("killer", "a"),
        victim=kw.pop("victim", "v"),
        characters=[Character(id=p, name=p.upper()) for p in people],
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        constraints=constraints,
        **kw,
    )


MURDER = Constraint(
    id="murder", people=["a", "v"], exclusive=True, place="study", slot="s2"
)


def test_count_moves_counts_changes_not_slots() -> None:
    case = _case({"a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"}}, [])

    assert count_moves(case, "a") == 1


def test_a1_fires_on_a_character_who_wanders() -> None:
    case = _case(
        {
            "a": {"s0": "hall", "s1": "study", "s2": "garden", "s3": "hall"},
            "v": {"s0": "hall", "s1": "hall", "s2": "hall", "s3": "hall"},
        },
        [],
    )

    assert "A1" in {a.check for a in critique(case)}


def test_a1_stays_quiet_when_people_stand_still() -> None:
    case = _case(
        {
            "a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
            "v": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        },
        [MURDER],
    )

    assert "A1" not in {a.check for a in critique(case)}


def test_a2_fires_when_the_killer_is_the_only_one_without_an_alibi() -> None:
    """Everyone else is together in the hall, so one question solves the case."""
    case = _case(
        {
            "a": {s.id: "study" for s in SLOTS},
            "v": {s.id: "study" for s in SLOTS},
            "b": {s.id: "hall" for s in SLOTS},
            "c": {s.id: "hall" for s in SLOTS},
        },
        [MURDER],
    )

    assert "A2" in {a.check for a in critique(case)}


def test_a3_fires_on_a_suspect_with_nothing_to_hide() -> None:
    """The most important property from playtesting, now measured against the
    secrets layer rather than against exclusive constraints.

    The old version inferred "has something to hide" from being alone in a room,
    which reported characters as blameless while they were holding a documented
    secret. Two real cases were flagged wrongly before anyone noticed.
    """
    from mystery.models import Secret as _S

    case = _case(
        {
            "a": {s.id: "study" for s in SLOTS},
            "v": {s.id: "study" for s in SLOTS},
            "b": {s.id: "garden" for s in SLOTS},
            "c": {s.id: "hall" for s in SLOTS},
        },
        [MURDER],
    ).model_copy(
        update={
            "secrets": [
                _S(id="motive", holder="a", about="v", summary="x", is_motive=True),
                _S(id="debt", holder="b", about="v", summary="y"),
            ]
        }
    )

    messages = [a.message for a in critique(case) if a.check == "A3"]

    assert len(messages) == 1, "only C holds nothing"
    assert "C" in messages[0]


def test_a8_fires_on_a_suspect_who_was_never_alone() -> None:
    """Holding a secret is not enough. A character visibly in a crowded room all
    evening had no opportunity, so pressing them cannot go anywhere."""
    from mystery.models import Secret as _S

    case = _case(
        {
            "a": {s.id: "study" for s in SLOTS},
            "v": {s.id: "study" for s in SLOTS},
            "b": {s.id: "hall" for s in SLOTS},
            "c": {s.id: "hall" for s in SLOTS},
        },
        [MURDER],
    ).model_copy(
        update={"secrets": [_S(id="debt", holder="b", about="v", summary="y")]}
    )

    flagged = {m.split()[0] for m in [a.message for a in critique(case) if a.check == "A8"]}

    assert flagged == {"B", "C"}, "B and C are together for the whole evening"


def test_the_victim_is_not_expected_to_have_a_secret() -> None:
    case = _case(
        {
            "a": {s.id: "study" for s in SLOTS},
            "v": {s.id: "study" for s in SLOTS},
        },
        [MURDER],
    )

    assert not [a for a in critique(case) if a.check == "A3" and "V" in a.message]


# The structural advisories, A4 to A6. These are the ones that separate a
# generated case from a written one.

from mystery.models import Claim, Secret  # noqa: E402

CAST = ["a", "b", "c", "v"]
STILL = {p: dict.fromkeys([s.id for s in SLOTS], "hall") for p in CAST}


def _structured(secrets, **kw) -> Mystery:
    placements = kw.pop("placements", None) or {
        **STILL,
        "a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        "v": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
    }
    return Mystery(
        title="Test",
        killer="a",
        victim="v",
        characters=[Character(id=p, name=p.upper()) for p in CAST],
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        constraints=[MURDER],
        secrets=secrets,
        **kw,
    )


MOTIVE = Secret(id="motive", holder="a", about="v", summary="v was ruining a")
GATE = Secret(id="gate", holder="b", about="v", summary="b was being blackmailed")


def test_a4_fires_when_only_the_killer_cares_about_the_victim() -> None:
    """Five suspects, five unrelated subplots, one murder bolted on."""
    case = _structured(
        [
            MOTIVE.model_copy(update={"revealed_by": "gate"}),
            Secret(id="s2", holder="b", about="c", summary="unrelated affair"),
            Secret(id="s3", holder="c", about="b", summary="unrelated debt"),
        ]
    )

    assert "A4" in {a.check for a in critique(case)}


def test_a4_is_quiet_when_the_victim_had_a_hold_over_the_room() -> None:
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claim=Claim(character="a", place="hall", slot="s2"),
    )

    assert "A4" not in {a.check for a in critique(case)}


def test_a5_fires_when_the_killers_motive_is_visible_immediately() -> None:
    case = _structured([MOTIVE, GATE])

    messages = [a.message for a in critique(case) if a.check == "A5"]

    assert len(messages) == 1
    assert "not gated" in messages[0]


def test_a6_fires_when_nobody_lies_about_where_they_were() -> None:
    case = _structured([MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE])

    assert "A6" in {a.check for a in critique(case)}


def test_a6_fires_when_the_claimed_place_is_the_true_place() -> None:
    """A lie that matches the timeline is not a lie."""
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claim=Claim(character="a", place="study", slot="s2"),
    )

    messages = [a.message for a in critique(case) if a.check == "A6"]

    assert len(messages) == 1
    assert "not a lie" in messages[0]


def test_a7_fires_when_a_single_credible_witness_settles_it() -> None:
    """The rule the project was specified around, finally checkable."""
    from mystery.models import Claim as _Claim
    from mystery.models import Secret as _Secret

    case = Mystery(
        title="Test",
        killer="a",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("a", "v", "b", "c")],
        places=PLACES,
        slots=SLOTS,
        placements={
            "a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
            "v": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
            "b": {s.id: "hall" for s in SLOTS},
            "c": {s.id: "hall" for s in SLOTS},
        },
        constraints=[MURDER],
        secrets=[
            _Secret(id="motive", holder="a", about="v", summary="x", revealed_by="gate"),
            _Secret(id="gate", holder="b", about="v", summary="y"),
        ],
        false_claim=_Claim(character="a", place="hall", slot="s2"),
    )

    messages = [x.message for x in critique(case) if x.check == "A7"]

    # B and C can both contradict, but C has no secret, so one question ends it.
    assert any("settles the case" in m for m in messages)
