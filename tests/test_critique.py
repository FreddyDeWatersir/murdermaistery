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

from mystery.models import FalseClaim, Secret  # noqa: E402

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
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
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
        false_claims=[FalseClaim(character="a", place="study", slot="s2")],
    )

    messages = [a.message for a in critique(case) if a.check == "A6"]

    assert len(messages) == 1
    assert "not a lie" in messages[0]


def test_a7_fires_when_a_single_credible_witness_settles_it() -> None:
    """The rule the project was specified around, finally checkable."""
    from mystery.models import FalseClaim as _Claim  # noqa: F401
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
        false_claims=[_Claim(character="a", place="hall", slot="s2")],
    )

    messages = [x.message for x in critique(case) if x.check == "A7"]

    # B and C can both contradict, but C has no secret, so one question ends it.
    assert any("settles the case" in m for m in messages)


def test_a9_fires_on_a_character_the_case_would_not_miss() -> None:
    """The complaint after the second playtest: some suspects were useless.

    A3 and A8 both passed C: she holds a secret and she had a moment alone. She
    is still decoration, because nothing in the case runs through her. She cannot
    contradict the killer, she gates nothing, and nobody's secret reaches her.
    """
    from mystery.models import FalseClaim as _Claim  # noqa: F401
    from mystery.models import Secret as _S

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
            "c": {s.id: "garden" for s in SLOTS},
        },
        constraints=[MURDER],
        secrets=[
            _S(id="motive", holder="a", about="v", summary="x", revealed_by="gate",
               is_motive=True),
            _S(id="gate", holder="b", about="v", summary="y"),
            _S(id="spare", holder="c", about="v", summary="hers alone, reaching nobody"),
        ],
        false_claims=[_Claim(character="a", place="hall", slot="s2")],
    )

    flagged = {m.split()[0] for m in [x.message for x in critique(case) if x.check == "A9"]}

    assert flagged == {"C"}, "B gates the motive; C is decoration"


# --- A10 to A12: the case must not fall to the timeline alone (D-063) -------


def test_a10_fires_when_the_killer_is_the_only_liar() -> None:
    """The flaw the second playtest found, now measured.

    One liar means "who lied" and "who did it" are the same question, and every
    secret in the case is decoration.
    """
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
    )

    assert "A10" in {x.check for x in critique(case)}


def test_a10_is_quiet_with_two_innocent_liars() -> None:
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1", covers="gate"),
            FalseClaim(character="c", place="study", slot="s0", covers="gate"),
        ],
    )

    assert "A10" not in {x.check for x in critique(case)}


def test_a11_fires_on_a_lie_with_nothing_underneath() -> None:
    """A lie the player can catch and can never resolve is a dead end wearing
    the costume of a red herring."""
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1"),
        ],
    )

    assert "A11" in {x.check for x in critique(case)}


def test_a11_fires_when_a_secret_is_sealed() -> None:
    """Covered by a real secret, but nobody else knows it and its holder has no
    condition for giving it up."""
    sealed = Secret(id="gate", holder="b", about="v", summary="b was being blackmailed")
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), sealed],
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1", covers="gate"),
        ],
    )

    assert "A11" in {x.check for x in critique(case)}


def test_a11_accepts_a_lie_somebody_else_can_explain() -> None:
    case = _structured(
        [
            MOTIVE.model_copy(update={"revealed_by": "gate"}),
            GATE.model_copy(update={"known_by": ["c"]}),
        ],
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1", covers="gate"),
        ],
    )

    assert "A11" not in {x.check for x in critique(case)}


def test_a12_fires_when_the_killer_is_the_only_liar_nobody_can_place() -> None:
    """The subtle way this collapses back into one move.

    Innocent lies break by presence, the killer's by absence. If every innocent
    liar has a witness, "which liar can nobody vouch for" is a mechanical
    shortcut straight to the answer.
    """
    together = {
        "a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        "v": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        "b": {"s0": "hall", "s1": "hall", "s2": "hall", "s3": "hall"},
        "c": {"s0": "hall", "s1": "hall", "s2": "hall", "s3": "hall"},
    }
    case = _structured(
        [
            MOTIVE.model_copy(update={"revealed_by": "gate"}),
            GATE.model_copy(update={"known_by": ["c"]}),
        ],
        placements=together,
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1", covers="gate"),
        ],
    )

    assert "A12" in {x.check for x in critique(case)}


def test_a12_is_quiet_when_an_innocent_was_also_alone() -> None:
    alone = {
        "a": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        "v": {"s0": "hall", "s1": "hall", "s2": "study", "s3": "study"},
        "b": {"s0": "hall", "s1": "garden", "s2": "hall", "s3": "hall"},
        "c": {"s0": "hall", "s1": "hall", "s2": "hall", "s3": "hall"},
    }
    case = _structured(
        [
            MOTIVE.model_copy(update={"revealed_by": "gate"}),
            GATE.model_copy(update={"known_by": ["c"]}),
        ],
        placements=alone,
        false_claims=[
            FalseClaim(character="a", place="hall", slot="s2"),
            FalseClaim(character="b", place="study", slot="s1", covers="gate"),
        ],
    )

    assert "A12" not in {x.check for x in critique(case)}


def test_a13_fires_when_only_the_killer_knows_why_they_did_it() -> None:
    """The killer never gives up their motive (D-066), so if nobody else knows
    it the player cannot name it and the best ending is unreachable."""
    case = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate", "is_motive": True}), GATE],
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
    )

    assert "A13" in {x.check for x in critique(case)}


def test_a13_is_quiet_when_somebody_half_knows() -> None:
    case = _structured(
        [
            MOTIVE.model_copy(
                update={"revealed_by": "gate", "is_motive": True, "known_by": ["b"]}
            ),
            GATE,
        ],
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
    )

    assert "A13" not in {x.check for x in critique(case)}


def test_a14_notices_a_cast_that_is_all_one_thing() -> None:
    """Not a judgement about one case. Left alone the generator cast men as the
    killer and the victim every time, and the room around them followed."""
    same = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
    ).model_copy(
        update={
            "characters": [
                c.model_copy(update={"gender": "man"})
                for c in _structured([MOTIVE, GATE]).characters
            ]
        }
    )

    assert "A14" in {x.check for x in critique(same)}


def test_a14_is_quiet_when_the_room_has_a_mix() -> None:
    mixed = _structured(
        [MOTIVE.model_copy(update={"revealed_by": "gate"}), GATE],
        false_claims=[FalseClaim(character="a", place="hall", slot="s2")],
    ).model_copy(
        update={
            "characters": [
                c.model_copy(update={"gender": "woman" if c.id in ("a", "v") else "man"})
                for c in _structured([MOTIVE, GATE]).characters
            ]
        }
    )

    assert "A14" not in {x.check for x in critique(mixed)}


def test_a14_says_so_when_nobody_states_a_gender() -> None:
    """Because then the drawn portrait is guessing from a prose sentence."""
    silent = _structured([MOTIVE, GATE])

    assert "A14" in {x.check for x in critique(silent)}
