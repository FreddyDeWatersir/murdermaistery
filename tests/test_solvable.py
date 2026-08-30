"""Tests for the reachability analysis.

The point of these is the cases every other check passes. A cycle, a missing
gate, a motive at the end of a chain that never starts: in all of them every
secret has a holder, a summary and a breaking point, every advisory is quiet,
and nobody can solve the case (D-068).
"""

from mystery.models import Character, Constraint, FalseClaim, Mystery, Place, Secret, Slot
from mystery.solvable import analyse, report, why_not

PLACES = [Place(id=p, name=p.title()) for p in ("hall", "study", "cellar")]
SLOTS = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)]
GRID = {
    "k": {"s0": "hall", "s1": "cellar", "s2": "hall"},
    "v": {"s0": "hall", "s1": "cellar", "s2": "cellar"},
    "a": {"s0": "hall", "s1": "hall", "s2": "hall"},
    "b": {"s0": "hall", "s1": "hall", "s2": "hall"},
}


PLAIN_LIE = FalseClaim(character="k", place="hall", slot="s1")


def _case(secrets, claims=None) -> Mystery:
    claims = (PLAIN_LIE,) if claims is None else claims
    return Mystery(
        title="Test",
        killer="k",
        victim="v",
        characters=[Character(id=c, name=c.upper()) for c in ("k", "v", "a", "b")],
        places=PLACES,
        slots=SLOTS,
        placements=GRID,
        constraints=[
            Constraint(id="murder", people=["k", "v"], exclusive=True, place="cellar", slot="s1")
        ],
        secrets=secrets,
        false_claims=list(claims),
    )


GATE = Secret(id="gate", holder="a", about="v", summary="a was being blackmailed")
MOTIVE = Secret(
    id="motive", holder="k", about="v", summary="v had him", is_motive=True, revealed_by="gate"
)


def test_a_working_case_is_winnable() -> None:
    """The motive is sealed to its holder, so somebody else has to half know it."""
    case = _case([GATE, MOTIVE.model_copy(update={"known_by": ["b"]})])

    result = analyse(case)

    assert result.way_in == ["gate"]
    assert result.motive_is_reachable
    assert result.killer_is_assailable
    assert result.winnable


def test_a_cycle_seals_both_secrets() -> None:
    """The failure no other check catches. A gates B, B gates A, every
    advisory passes, nobody can solve it."""
    case = _case(
        [
            GATE.model_copy(update={"revealed_by": "motive"}),
            MOTIVE.model_copy(update={"known_by": ["b"]}),
        ]
    )

    result = analyse(case)

    assert result.way_in == []
    assert set(result.sealed) == {"gate", "motive"}
    assert not result.winnable
    assert {a.check for a in why_not(case)} >= {"S1", "S2", "S3"}


def test_a_gate_that_does_not_exist_seals_what_is_behind_it() -> None:
    case = _case([GATE, MOTIVE.model_copy(update={"revealed_by": "the_letter"})])

    result = analyse(case)

    assert result.sealed == ["motive"]
    assert "S3" in {a.check for a in why_not(case)}


def test_the_killer_cannot_be_the_only_route_to_their_own_motive() -> None:
    """They never give it up (D-066), so with an empty `known_by` the reason
    for the murder exists nowhere a player can reach."""
    case = _case([GATE, MOTIVE])

    assert not analyse(case).motive_is_reachable
    assert "S3" in {a.check for a in why_not(case)}


def test_a_lie_covering_an_unreachable_secret_is_reported() -> None:
    """A11 checks the exit exists. This checks the exit can be got to."""
    case = _case(
        [
            GATE.model_copy(update={"revealed_by": "nowhere"}),
            MOTIVE.model_copy(update={"known_by": ["b"], "revealed_by": None}),
        ],
        claims=(
            FalseClaim(character="k", place="hall", slot="s1"),
            FalseClaim(character="a", place="study", slot="s0", covers="gate"),
        ),
    )

    assert "S4" in {a.check for a in why_not(case)}


def test_an_unbreakable_alibi_is_not_winnable_however_open_the_secrets_are() -> None:
    """Nobody else is in the hall at s1 in this grid, so nobody can contradict
    a claim to have been there."""
    empty_room = _case(
        [GATE, MOTIVE.model_copy(update={"known_by": ["b"]})],
        claims=(FalseClaim(character="k", place="study", slot="s1"),),
    )

    result = analyse(empty_room)

    assert result.motive_is_reachable
    assert not result.killer_is_assailable
    assert not result.winnable


def test_a_case_with_no_secrets_says_nothing_rather_than_passing() -> None:
    assert why_not(_case([])) == []


def test_the_report_is_readable() -> None:
    text = report(_case([GATE, MOTIVE.model_copy(update={"known_by": ["b"]})]))

    assert "Winnable:    yes" in text


def test_a_killer_who_never_lied_is_still_reachable() -> None:
    """Two shapes are built on the killer telling the truth (D-104).

    In a frame they have no need to lie; in the wrong hour their alibi for the
    hour everybody believes in is real. Requiring a breakable lie made both
    impossible to generate: every draft came back valid, was discarded as
    unwinnable, and the money was spent.
    """
    honest = _case(
        [GATE, MOTIVE.model_copy(update={"known_by": ["b"]})], claims=()
    )

    report = analyse(honest)

    assert report.killer_is_assailable
    assert report.winnable


def test_a_killer_seen_at_the_scene_by_somebody_is_not_the_shape_either() -> None:
    """The honest branch still refuses a killer nothing can touch. If somebody
    was standing there, the case is not about working out who did it."""
    case = _case([GATE, MOTIVE.model_copy(update={"known_by": ["b"]})], claims=())
    scene = case.murder_scene
    watched = case.model_copy(
        update={
            "placements": {
                **case.placements,
                "a": {**case.placements.get("a", {}), scene.slot: scene.place},
            }
        }
    )

    assert not analyse(watched).killer_is_assailable
