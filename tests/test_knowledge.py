"""Tests for knowledge derivation and the alibi analysis.

The alibi tests are the important ones. They check the property the whole
project was specified around and could not be written until now.
"""

from mystery.knowledge import analyse_alibi, derive
from mystery.models import Character, Claim, Constraint, Mystery, Place, Secret, Slot

PLACES = [Place(id=p, name=p.title()) for p in ("hall", "study", "cellar")]
SLOTS = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)]
CAST = ["killer", "victim", "quiet", "shifty", "other"]

MURDER = Constraint(
    id="murder", people=["killer", "victim"], exclusive=True, place="cellar", slot="s2"
)


def _case(placements, secrets=(), claim=None) -> Mystery:
    return Mystery(
        title="Test",
        killer="killer",
        victim="victim",
        characters=[Character(id=c, name=c.title()) for c in CAST],
        places=PLACES,
        slots=SLOTS,
        placements=placements,
        constraints=[MURDER],
        secrets=list(secrets),
        false_claim=claim,
    )


GRID = {
    "killer": {"s0": "hall", "s1": "hall", "s2": "cellar"},
    "victim": {"s0": "hall", "s1": "hall", "s2": "cellar"},
    "quiet": {"s0": "hall", "s1": "study", "s2": "hall"},
    "shifty": {"s0": "hall", "s1": "study", "s2": "hall"},
    "other": {"s0": "study", "s1": "study", "s2": "study"},
}


def test_co_location_is_mutual() -> None:
    know = derive(_case(GRID))

    assert know["quiet"].saw("shifty", "s1")
    assert know["shifty"].saw("quiet", "s1")
    assert not know["quiet"].saw("other", "s2")


def test_a_character_does_not_observe_themselves() -> None:
    know = derive(_case(GRID))

    assert all(o.subject != "quiet" for o in know["quiet"].observations)


def test_the_victim_stops_seeing_things_when_they_die() -> None:
    """The body is in the room. It testifies to nothing."""
    know = derive(_case(GRID))

    assert know["victim"].saw("killer", "s1")
    assert not know["victim"].saw("killer", "s2")


def test_a_secret_makes_its_holder_an_unreliable_witness() -> None:
    know = derive(
        _case(GRID, secrets=[Secret(id="debt", holder="shifty", summary="owes money")])
    )

    assert know["quiet"].is_credible
    assert not know["shifty"].is_credible
    assert know["shifty"].conceals == ["debt"]


def test_knowing_someone_elses_secret_is_not_the_same_as_holding_it() -> None:
    know = derive(
        _case(
            GRID,
            secrets=[
                Secret(id="debt", holder="shifty", summary="owes money", known_by=["quiet"])
            ],
        )
    )

    assert know["quiet"].aware_of == ["debt"]
    assert know["quiet"].conceals == []
    assert know["quiet"].is_credible, "knowing a secret does not compromise you"


# The alibi analysis, which is the point of all of the above


CLAIM = Claim(character="killer", place="hall", slot="s2")


def test_people_in_the_room_the_killer_claims_can_contradict_it() -> None:
    """Quiet and Shifty were in the hall at s2. The killer says he was too, and
    they did not see him."""
    analysis = analyse_alibi(_case(GRID, claim=CLAIM), derive(_case(GRID, claim=CLAIM)))

    assert not analysis.claim_holds
    assert analysis.contradictors == ["quiet", "shifty"]
    assert analysis.breakable


def test_a_claim_that_matches_the_timeline_is_not_a_lie() -> None:
    honest = Claim(character="killer", place="cellar", slot="s2")
    case = _case(GRID, claim=honest)

    assert analyse_alibi(case, derive(case)).claim_holds


def test_an_alibi_only_one_person_can_touch_is_flagged_as_unbreakable() -> None:
    """The killer was alone with the victim, so nobody saw him anywhere.

    The only person who can say anything is whoever was in the room he named,
    and there is one of those. One testimony is not combined testimony, and a
    player who does not think to ask that exact person cannot solve the case.
    """
    lonely_room = Claim(character="killer", place="study", slot="s2")
    case = _case(GRID, claim=lonely_room)

    analysis = analyse_alibi(case, derive(case))

    assert analysis.contradictors == ["other"]
    assert not analysis.breakable


def test_being_seen_elsewhere_also_contradicts_a_claim() -> None:
    """The other way to break a lie, and the one that almost never fires.

    At s0 the killer was in the hall with three people. A claim to have been in
    the study then is refuted by everyone who saw him. This is why a killer who
    was alone at the murder is much harder to catch: the only witness to where he
    really was is the person who died.
    """
    seen = Claim(character="killer", place="study", slot="s0")
    case = _case(GRID, claim=seen)

    analysis = analyse_alibi(case, derive(case))

    assert set(analysis.contradictors) == {"other", "quiet", "shifty"}


def test_a_witness_with_nothing_to_hide_settles_the_case_alone() -> None:
    """The failure mode that makes a case trivial.

    Both witnesses can contradict the killer, but Quiet has no secret, so one
    question to Quiet ends it. In both hand-built prototypes every witness
    against the killer was compromised, and that is what made them suggestive
    rather than conclusive.
    """
    case = _case(
        GRID,
        secrets=[Secret(id="debt", holder="shifty", summary="owes money")],
        claim=CLAIM,
    )

    analysis = analyse_alibi(case, derive(case))

    assert analysis.breakable
    assert analysis.settled_by_one
    assert analysis.credible == ["quiet"]


def test_two_compromised_witnesses_is_the_shape_we_want() -> None:
    """Breakable by combining testimony, settled by neither alone."""
    case = _case(
        GRID,
        secrets=[
            Secret(id="debt", holder="shifty", summary="owes money"),
            Secret(id="affair", holder="quiet", summary="seeing someone"),
        ],
        claim=CLAIM,
    )

    analysis = analyse_alibi(case, derive(case))

    assert analysis.breakable
    assert not analysis.settled_by_one
