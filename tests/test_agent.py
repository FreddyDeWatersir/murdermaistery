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
from mystery.models import Character, Constraint, FalseClaim, Mystery, Place, Secret, Slot

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
            is_motive=True,
            known_by=["clara"],
        ),
    ],
    false_claims=[FalseClaim(character="otto", place="hall", slot="s2")],
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


def test_a_character_is_not_given_someone_elses_secret_to_keep() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    vera = build_brief(CASE, KNOW, "vera")

    assert not clara.conceals and not clara.guarded, "Clara holds no secret of her own"
    assert any("Vera and Otto" in f.text for f in vera.guarded)


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


def test_the_killers_motive_is_in_the_brief_and_never_citable() -> None:
    """A character has to know their own secret in order to deflect around it.

    That means the prompt contains what the answer must not reveal, which is a
    real risk and is precisely what the leakage detector is for. For one secret
    in the case it is absolute: the reason the killer did it never comes out of
    their own mouth (D-066).
    """
    otto = build_brief(CASE, KNOW, "otto")
    system = render_system(otto)

    assert "Magnus threatened to expose the affair" in system
    assert "secret:motive" not in otto.licensed
    assert "[secret:motive]" not in system, "the motive is not offered as a citation"


def test_a_suspects_own_secret_can_be_got_out_of_them() -> None:
    """Everything except the murder itself is winnable (D-066). Otherwise
    interrogation is a formality and the secrets layer never surfaces."""
    vera = build_brief(CASE, KNOW, "vera")

    assert "secret:affair" in vera.licensed
    assert "[secret:affair]" in render_system(vera)


# Leakage


def test_citing_a_fact_the_character_does_not_have_is_a_leak() -> None:
    clara = build_brief(CASE, KNOW, "clara")
    reply = ask(
        clara, "Where was Otto?", _responder(speech="In the cellar.", used=["saw:otto@s2"])
    )

    assert leaks(clara, reply) == ["cited something it does not know: saw:otto@s2"]


def test_citing_concealed_material_is_the_worst_kind_of_leak() -> None:
    """The character has handed over the thing they exist to hide."""
    otto = build_brief(CASE, KNOW, "otto")
    reply = ask(
        otto,
        "Why did you do it?",
        _responder(speech="He was going to tell her.", used=["secret:motive"]),
    )

    assert leaks(otto, reply) == ["cited concealed material: secret:motive"]


def test_giving_up_your_own_secret_is_a_fold_and_not_a_leak() -> None:
    """The distinction the third state exists for. Coming clean is legitimate
    play; saying something you were never told is not."""
    vera = build_brief(CASE, KNOW, "vera")
    reply = ask(
        vera,
        "Otto has already told me about the two of you.",
        _responder(speech="Then you know.", used=["secret:affair"]),
    )

    assert leaks(vera, reply) == []


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


def test_a_guarded_secret_carries_its_breaking_point() -> None:
    """Concealment that never breaks is a wall, not a mystery (D-012)."""
    vera = build_brief(CASE, KNOW, "vera")

    affair = next(f for f in vera.guarded if f.id == "secret:affair")

    assert "already knows Otto was not where he says" in affair.text


def test_a_secret_with_no_breaking_point_says_so_rather_than_going_silent() -> None:
    stubborn = CASE.model_copy(
        update={
            "secrets": [
                s.model_copy(update={"breaks_when": ""}) if s.id == "affair" else s
                for s in CASE.secrets
            ]
        }
    )

    vera = build_brief(stubborn, derive(stubborn), "vera")
    affair = next(f for f in vera.guarded if f.id == "secret:affair")

    assert "no way around it" in affair.text


# What the first playtest broke on (D-053, D-054, D-055)


def test_a_character_remembers_what_they_already_said() -> None:
    """The loudest bug from the first playtest.

    Every question was answered as though it were the first, because nothing
    carried the conversation forward. Consistency is not something a model can
    invent: it has to be shown what it committed to.
    """
    vera = build_brief(CASE, KNOW, "vera")
    system = render_system(
        vera, [("Where were you at nine?", "The study, with Clara.")]
    )

    assert "The study, with Clara." in system
    assert "Where were you at nine?" in system


def test_a_first_question_says_so_rather_than_showing_an_empty_list() -> None:
    system = render_system(build_brief(CASE, KNOW, "vera"))

    assert "this is the first thing you have been asked" in system


def test_opinions_reach_the_prompt_and_are_not_facts() -> None:
    """The second playtest complaint: they gave nothing back.

    Their whole brief was where they stood, so any question about a person
    rather than a place had no licensed answer and got a refusal. Impressions
    are stated freely and are deliberately not citable facts.
    """
    case = CASE.model_copy(
        update={
            "characters": [
                c.model_copy(update={"impressions": {"magnus": "He collected debts."}})
                if c.id == "vera"
                else c
                for c in CASE.characters
            ]
        }
    )
    vera = build_brief(case, derive(case), "vera")

    assert "Magnus: He collected debts." in vera.impressions
    assert "He collected debts." in render_system(vera)
    assert not any("collected debts" in f.text for f in vera.facts)


def test_the_body_being_found_is_common_knowledge() -> None:
    """Nothing said the body had been found, so nobody could discuss the death
    they were being questioned about."""
    from mystery.models import Discovery

    case = CASE.model_copy(
        update={
            "discovery": Discovery(
                finder="clara", place="cellar", summary="She went down for a bottle."
            )
        }
    )

    for character in ("otto", "vera", "clara"):
        brief = build_brief(case, derive(case), character)
        joined = " ".join(brief.common)
        assert "Clara found the body" in joined
        assert "Cellar" in joined


# --- innocent liars, and the third knowledge state (D-063, D-064) -----------


LIARS = CASE.model_copy(
    update={
        "false_claims": [
            FalseClaim(character="otto", place="hall", slot="s2"),
            FalseClaim(
                character="vera",
                place="hall",
                slot="s1",
                covers="affair",
                admits_when="she is told somebody saw her in the study",
            ),
        ]
    }
)
LIARS_KNOW = derive(LIARS)


def test_an_innocent_liar_is_handed_the_lie_as_their_own_account() -> None:
    """Same treatment as the killer: they say the lie, not the truth."""
    vera = build_brief(LIARS, LIARS_KNOW, "vera")

    self_s1 = next(f for f in vera.facts if f.id == "self:s1")
    assert self_s1.place == "hall", "she claims the hall"
    assert LIARS.placements["vera"]["s1"] == "study", "she was in the study"


def test_an_innocent_can_be_brought_to_the_truth_and_the_killer_cannot() -> None:
    """The asymmetry the whole design now rests on.

    An innocent's retraction has to reach the notebook, so it is citable. The
    killer's would end the game, so it never becomes sayable at all: under
    pressure they have the shield instead.
    """
    vera = build_brief(LIARS, LIARS_KNOW, "vera")
    otto = build_brief(LIARS, LIARS_KNOW, "otto")

    assert "truth:s1" in {f.id for f in vera.guarded}
    assert "truth:s1" in vera.licensed, "a retraction nobody can cite is a retraction nobody hears"

    assert "truth:s2" in {f.id for f in otto.conceals}
    assert "truth:s2" not in otto.licensed


def test_the_guarded_truth_carries_the_room_it_happened_in() -> None:
    """Structure travels with the prose (D-050), or the timeline cannot update."""
    vera = build_brief(LIARS, LIARS_KNOW, "vera")

    truth = next(f for f in vera.guarded if f.id == "truth:s1")
    assert (truth.subject, truth.slot, truth.place) == ("vera", "s1", "study")


def test_the_condition_for_admitting_it_reaches_the_prompt() -> None:
    vera = build_brief(LIARS, LIARS_KNOW, "vera")

    assert "somebody saw her in the study" in render_system(vera)


def test_admitting_it_is_not_a_leak() -> None:
    vera = build_brief(LIARS, LIARS_KNOW, "vera")

    answer = _responder(speech="Yes. I was.", used=["truth:s1"])
    reply = ask(vera, "Somebody saw you in the study.", answer)

    assert leaks(vera, reply) == []


def test_the_killer_confessing_is_a_leak() -> None:
    otto = build_brief(LIARS, LIARS_KNOW, "otto")

    reply = ask(otto, "You were in the cellar.", _responder(speech="I was.", used=["truth:s2"]))

    assert leaks(otto, reply) == ["cited concealed material: truth:s2"]


def test_a_liar_reports_nothing_from_the_moment_they_are_lying_about() -> None:
    """D-042, now for everybody. Vera cannot say who was in the study at s1
    while claiming she was in the hall."""
    vera = build_brief(LIARS, LIARS_KNOW, "vera")

    assert not [f for f in vera.facts if f.id.startswith("saw:") and f.slot == "s1"]
    assert [f for f in vera.facts if f.id.startswith("saw:") and f.slot == "s2"]
