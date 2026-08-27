"""Tests for the agent boundary.

None of these call a model. What is being tested is not whether an answer is any
good, it is whether the boundary holds: that a character is handed only what they
know, that the killer is handed their lie rather than the truth, and that a reply
reaching outside that set is detected.

This is the knowledge-leakage suite the project was supposed to have from the
start, and it doubles as the instrument for choosing which model can play which
role (D-004).
"""

from mystery.agent import ask, build_brief, leaks, render_system
from mystery.knowledge import derive
from mystery.models import Character, Claim, Constraint, Mystery, Place, Secret, Slot

PLACES = [Place(id=p, name=p.replace("_", " ").title()) for p in ("hall", "study", "cellar")]
SLOTS = [Slot(id=f"s{i}", label=f"2{i}:00", index=i) for i in range(3)]

CASE = Mystery(
    title="A Small Gathering",
    killer="otto",
    victim="magnus",
    characters=[
        Character(
            id="otto",
            name="Otto",
            wants="the partnership to survive the evening",
            manner="calm, competent, helpful about everything that costs him nothing",
            under_pressure="offers a smaller true thing to keep you away from the larger one",
        ),
        Character(id="magnus", name="Magnus"),
        Character(
            id="vera",
            name="Vera",
            wants="to get out of this without her name in it",
            manner="cold and precise, answers exactly the question asked",
            under_pressure="stops answering and starts asking",
        ),
        Character(id="clara", name="Clara"),
    ],
    places=PLACES,
    slots=SLOTS,
    placements={
        "otto": {"s0": "hall", "s1": "hall", "s2": "cellar"},
        "magnus": {"s0": "hall", "s1": "hall", "s2": "cellar"},
        "vera": {"s0": "hall", "s1": "study", "s2": "hall"},
        "clara": {"s0": "study", "s1": "study", "s2": "hall"},
    },
    constraints=[
        Constraint(
            id="murder",
            people=["otto", "magnus"],
            exclusive=True,
            place="cellar",
            slot="s2",
        )
    ],
    secrets=[
        Secret(
            id="affair",
            holder="vera",
            about="otto",
            summary="Vera and Otto are involved.",
            breaks_when="the questioner already knows Otto was not where he says",
        ),
        Secret(
            id="motive",
            holder="otto",
            about="magnus",
            summary="Magnus threatened to expose the affair.",
            revealed_by="affair",
            known_by=["clara"],
        ),
    ],
    false_claim=Claim(character="otto", place="hall", slot="s2"),
)

KNOW = derive(CASE)


def _responder(**payload):
    def respond(_system: str, _question: str) -> dict:
        return payload

    return respond


# What each character is handed


def test_a_character_is_only_given_what_they_saw() -> None:
    brief = build_brief(CASE, KNOW, "clara")

    assert "saw:vera@s1" in brief.licensed, "Clara was in the study with Vera at s1"
    assert "saw:otto@s2" not in brief.licensed, "Clara never saw Otto in the cellar"


def test_a_character_is_not_given_someone_elses_secret_to_conceal() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    vera = build_brief(CASE, KNOW, "vera")

    assert not clara.conceals, "Clara holds no secret of her own"
    assert any("Vera and Otto" in f.text for f in vera.conceals)


def test_knowing_a_secret_is_licensed_but_holding_one_is_not() -> None:
    """Clara knows Otto's motive without it being hers. She may say it."""
    clara = build_brief(CASE, KNOW, "clara")

    assert "heard:motive" in clara.licensed
    assert "secret:motive" not in clara.licensed


def test_the_killer_is_handed_the_lie_and_not_the_truth() -> None:
    """The most important line in the module.

    Otto's sayable fact for the murder slot is the hall. The cellar appears only
    among the things he conceals. An agent given both will hedge, and a killer who
    hedges is caught in one question.
    """
    otto = build_brief(CASE, KNOW, "otto")

    sayable = next(f for f in otto.facts if f.id == "self:s2")
    concealed = next(f for f in otto.conceals if f.id == "truth:s2")

    assert "Hall" in sayable.text
    assert "Cellar" in concealed.text
    assert not any("Cellar" in f.text for f in otto.facts)


def test_the_killer_does_not_get_facts_about_the_slot_he_lies_about() -> None:
    """Otto saw Magnus in the cellar. Citing that would place him there."""
    otto = build_brief(CASE, KNOW, "otto")

    assert "saw:magnus@s2" not in otto.licensed


def test_the_victim_never_witnessed_their_own_death() -> None:
    magnus = build_brief(CASE, KNOW, "magnus")

    assert "saw:otto@s2" not in magnus.licensed
    assert "saw:otto@s1" in magnus.licensed


# The prompt


def test_concealed_material_is_in_the_brief_but_never_as_a_citable_id() -> None:
    """A character has to know their own secret in order to deflect around it.

    That means the prompt contains what the answer must not reveal, which is a
    real risk and is precisely what the leakage detector is for.
    """
    vera = build_brief(CASE, KNOW, "vera")
    system = render_system(vera)

    assert "Vera and Otto are involved" in system
    assert "[secret:affair]" not in system, "concealed items are not offered as citations"


# Leakage


def test_citing_a_fact_the_character_does_not_have_is_a_leak() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    reply = ask(
        clara, "Where was Otto?", _responder(speech="In the cellar.", used=["saw:otto@s2"])
    )

    assert leaks(clara, reply) == ["cited something it does not know: saw:otto@s2"]


def test_citing_concealed_material_is_the_worst_kind_of_leak() -> None:
    """The character has handed over the thing they exist to hide."""
    vera = build_brief(CASE, KNOW, "vera")
    reply = ask(
        vera,
        "Anything between you and Otto?",
        _responder(speech="We are involved.", used=["secret:affair"]),
    )

    assert leaks(vera, reply) == ["cited concealed material: secret:affair"]


def test_a_clean_answer_leaks_nothing() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    reply = ask(
        clara, "Where were you at 21:00?", _responder(speech="The hall.", used=["self:s2"])
    )

    assert leaks(clara, reply) == []


def test_a_refusal_is_a_valid_answer_and_leaks_nothing() -> None:
    """Refusal is a first class behaviour, not a failure (D-013)."""
    clara = build_brief(CASE, KNOW, "clara")
    reply = ask(
        clara,
        "What happened in the cellar?",
        _responder(speech="I have no idea, I was not down there.", used=[], refused=True),
    )

    assert reply.refused
    assert leaks(clara, reply) == []


# The authored half of a character (D-044)


def test_the_person_reaches_the_prompt() -> None:
    """Facts are derived, but a person is not computable from a grid."""
    vera = build_brief(CASE, KNOW, "vera")
    system = render_system(vera)

    assert vera.manner.startswith("cold and precise")
    assert "cold and precise" in system
    assert "stops answering and starts asking" in system


def test_two_characters_with_the_same_facts_still_read_differently() -> None:
    """The whole point. Same evening, different people."""
    otto = render_system(build_brief(CASE, KNOW, "otto"))
    vera = render_system(build_brief(CASE, KNOW, "vera"))

    assert "offers a smaller true thing" in otto
    assert "offers a smaller true thing" not in vera


def test_a_character_with_no_authored_persona_still_works() -> None:
    """Magnus has no persona fields. The brief must not break, and must not
    invent one either."""
    magnus = build_brief(CASE, KNOW, "magnus")

    assert "(an ordinary guest)" in render_system(magnus)


def test_a_concealed_secret_carries_its_breaking_point() -> None:
    """Concealment that never breaks is a wall, not a mystery (D-012)."""
    vera = build_brief(CASE, KNOW, "vera")

    affair = next(f for f in vera.conceals if f.id == "secret:affair")

    assert "already knows Otto was not where he says" in affair.text


def test_a_secret_with_no_breaking_point_says_so_rather_than_going_silent() -> None:
    otto = build_brief(CASE, KNOW, "otto")

    motive = next(f for f in otto.conceals if f.id == "secret:motive")

    assert "You do not give this up." in motive.text
