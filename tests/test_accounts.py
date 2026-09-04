"""What people say happened, and being wrong without lying (D-132).

The third falsifiable axis. Person-place-slot says who was in the room;
thing-place-slot says what was in it; neither says what *happened* there. And
the field that matters most is `honest`: until this existed every fact in the
game was true and every contradiction meant a liar.
"""

from mystery.agent import build_brief, render_system
from mystery.critique import somebody_is_wrong_without_lying as a22
from mystery.example import OPENING_NIGHT
from mystery.knowledge import derive
from mystery.models import Account, Mystery

CASE = Mystery.model_validate(OPENING_NIGHT)
SCENE = CASE.constraints[0]
PAIR = SCENE.people[:2]


def _told(*accounts: Account) -> Mystery:
    return CASE.model_copy(update={"accounts": list(accounts)})


def _version(who: str, says: str, **kw) -> Account:
    return Account(constraint=SCENE.id, character=who, says=says, **kw)


# --- what reaches the person --------------------------------------------------


def test_an_account_reaches_only_the_person_who_gave_it() -> None:
    mystery = _told(
        _version(PAIR[0], "He raised his voice first."),
        _version(PAIR[1], "Nobody raised anything.", true=False, honest=True),
    )
    knowledge = derive(mystery)

    mine = build_brief(mystery, knowledge, PAIR[0]).accounts
    theirs = build_brief(mystery, knowledge, PAIR[1]).accounts

    assert [f.text for f in mine] != [f.text for f in theirs]
    assert "He raised his voice first." in mine[0].text
    assert "Nobody raised anything." in theirs[0].text


def test_somebody_honestly_wrong_is_not_told_they_are_wrong_in_a_way_they_can_hedge() -> None:
    """The whole point of `honest`. They are certain. If the brief let them
    perform doubt, the player would read the doubt and never be misled."""
    mystery = _told(_version(PAIR[0], "The door was shut.", true=False, honest=True))
    knowledge = derive(mystery)

    said = build_brief(mystery, knowledge, PAIR[0]).accounts[0].text

    assert "You are certain of this" in said
    assert "do not perform uncertainty" in said
    assert "you think they are the one who is mistaken" in said


def test_a_liar_is_told_plainly_that_they_are_lying() -> None:
    mystery = _told(
        _version(
            PAIR[0], "I never went in.", true=False, honest=False,
            changes_when="shown the key",
        )
    )
    knowledge = derive(mystery)

    said = build_brief(mystery, knowledge, PAIR[0]).accounts[0].text

    assert "not what happened and you know it" in said
    assert "shown the key" in said


def test_a_true_account_is_just_true() -> None:
    mystery = _told(_version(PAIR[0], "We argued about the money."))
    knowledge = derive(mystery)

    said = build_brief(mystery, knowledge, PAIR[0]).accounts[0].text

    assert "no reason to doubt it" in said


def test_accounts_carry_where_and_when_the_scene_was() -> None:
    from mystery.solver import solve

    solved = solve(CASE, seed=0)
    scene = next(c for c in solved.constraints if c.place and c.slot)
    mystery = solved.model_copy(
        update={
            "accounts": [
                Account(constraint=scene.id, character=scene.people[0], says="It was brief.")
            ]
        }
    )
    knowledge = derive(mystery)

    said = build_brief(mystery, knowledge, scene.people[0]).accounts[0].text

    assert "(" in said and ")" in said, "an account with no scene is unanchored"


def test_accounts_are_given_freely_rather_than_under_the_hard_line() -> None:
    """An account is not a fact about position, so the rule that governs FACTS
    must not govern this."""
    mystery = _told(_version(PAIR[0], "We argued."))
    knowledge = derive(mystery)

    system = render_system(build_brief(mystery, knowledge, PAIR[0]), [])

    assert "WHAT YOU SAY HAPPENED" in system
    assert "the hard line above does not cover them" in system
    assert "as often as between liars" in system


def test_somebody_with_nothing_to_describe_says_so() -> None:
    knowledge = derive(CASE)
    system = render_system(build_brief(CASE, knowledge, CASE.characters[0].id), [])

    assert "nothing you were close enough to describe" in system


# --- A22 ----------------------------------------------------------------------


def test_a_case_with_no_accounts_is_flagged() -> None:
    assert [a.check for a in a22(CASE)] == ["A22"]


def test_accounts_that_all_agree_are_description_not_evidence() -> None:
    said = a22(_told(_version(PAIR[0], "It was brief."), _version(PAIR[1], "Very brief.")))

    assert any("never conflict" in a.message for a in said)


def test_every_falsehood_being_a_lie_is_flagged() -> None:
    """With nobody honestly mistaken, a contradiction still means a liar and the
    player is right to treat every collision as a verdict."""
    said = a22(
        _told(
            _version(PAIR[0], "We argued."),
            _version(PAIR[1], "We did not.", true=False, honest=False),
        )
    )

    assert any("deliberate lies" in a.message for a in said)


def test_an_honest_mistake_satisfies_it() -> None:
    said = a22(
        _told(
            _version(PAIR[0], "We argued."),
            _version(PAIR[1], "We did not.", true=False, honest=True),
        )
    )

    assert said == []


def test_an_account_from_somebody_who_was_not_there_is_hearsay() -> None:
    outsider = next(c.id for c in CASE.characters if c.id not in SCENE.people)

    said = a22(
        _told(
            _version(PAIR[0], "We argued."),
            _version(PAIR[1], "We did not.", true=False, honest=True),
            _version(outsider, "I heard the whole thing."),
        )
    )

    assert any("hearsay wearing" in a.message for a in said)
