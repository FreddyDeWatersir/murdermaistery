"""Tests for the agent boundary.

None of these call a model. What is being tested is not whether an answer is any
good, it is whether the boundary holds: that a character is handed only what they
know, that the killer is handed their lie rather than the truth, and that a reply
reaching outside that set is detected.

This is the knowledge-leakage suite the project was supposed to have from the
start, and it doubles as the instrument for choosing which model can play which
role (D-004).
"""

from mystery.agent import ask, build_brief, leaks, render_system, strip_citations
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
            evidence="the letters",
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


def test_a_gated_secret_is_not_in_the_witness_brief_at_all() -> None:
    """Clara knows Otto's motive, and until the gate is met she does not have it.

    Withheld by omission rather than by instruction (D-087). Before this, a
    secret gated behind another sat in Clara's plain facts from question one:
    `revealed_by` was read by the solvability check and by nothing that ran
    during play, so the gate the whole case was built around did not exist.
    """
    clara = build_brief(CASE, KNOW, "clara")

    assert "heard:motive" not in clara.licensed
    assert not any("threatened to expose" in f.text for f in clara.facts)
    assert "secret:motive" not in clara.licensed


def test_producing_the_object_opens_the_gate_for_that_person_only() -> None:
    """Otto's motive is gated behind the affair, whose object is the letters."""
    opened = build_brief(CASE, KNOW, "clara", shown={"affair"})

    assert "heard:motive" in opened.licensed
    assert any(f.id == "heard:motive" for f in opened.yielding), (
        "shown the thing itself, it is coming out, not merely permitted"
    )
    assert "the letters" in next(f.text for f in opened.yielding)

    # And nobody else moved. Showing Clara something tells Vera nothing.
    assert "heard:motive" not in build_brief(CASE, KNOW, "vera").licensed


def test_the_killer_keeps_their_motive_even_when_shown_everything() -> None:
    """D-066 outranks the object. Otto never says why he did it, full stop."""
    otto = build_brief(CASE, KNOW, "otto", shown={"affair", "motive"})

    assert "secret:motive" not in otto.licensed
    assert any(f.id == "secret:motive" for f in otto.conceals)


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


def test_everybody_is_told_who_everybody_else_is() -> None:
    """Five models inventing the same relationship five ways is not a style issue.

    In a real playtest the same woman was called the victim's niece, his
    daughter and his wife by three different suspects, because no brief said
    who anyone was. `role` is public by construction, so it goes to all of them.
    """
    brief = build_brief(CASE, derive(CASE), "otto")
    rendered = render_system(brief)

    listed = {line.split(":")[0].strip() for line in brief.roster}
    assert listed == {c.name for c in CASE.characters if c.id != "otto"}
    assert "WHO THE OTHERS ARE" in rendered
    for line in brief.roster:
        assert line in rendered


def test_the_roster_says_which_one_is_dead() -> None:
    """A suspect who talks about the victim in the present tense should be doing
    it as a character choice, not because nobody told them."""
    brief = build_brief(CASE, derive(CASE), "otto")
    victim = next(c for c in CASE.characters if c.id == CASE.victim)

    said = next(line for line in brief.roster if line.startswith(victim.name))
    assert "dead" in said.lower()


def test_nobody_is_on_their_own_roster() -> None:
    for character in CASE.characters:
        if character.id == CASE.victim:
            continue
        brief = build_brief(CASE, derive(CASE), character.id)
        assert not any(line.startswith(character.name) for line in brief.roster)


def test_somebody_elses_secret_is_not_filed_under_where_people_were() -> None:
    """Two witnesses sat on a forgery for a hundred questions (D-088).

    Not because they were told to protect it. Because it was in `facts`, which
    the prompt introduces as the whitelist of things you may state about where
    anyone was, so a model reads the heading and treats the block as whereabouts.
    """
    clara = build_brief(CASE, KNOW, "clara", shown={"affair"})

    assert not any(f.id.startswith("heard:") for f in clara.facts)
    assert all(f.id.startswith(("self:", "saw:")) for f in clara.facts)


def test_an_ungated_secret_you_merely_know_is_yours_to_say() -> None:
    vera = build_brief(CASE, KNOW, "vera")
    heard = [f.id for f in vera.hearsay]

    assert "heard:the_debt" in heard or heard == [], heard
    for fact in vera.hearsay:
        assert fact.id in vera.licensed
        assert fact.text.startswith("About "), "the prompt has to say who it is about"


def test_a_gate_with_nothing_to_produce_stays_held_back() -> None:
    """Cases made before objects existed keep the difficulty they had.

    The alternative was putting a gated secret into the block that says say this
    freely, which would make every old case solvable in one question.
    """
    soft = CASE.model_copy(
        update={
            "secrets": [
                s.model_copy(update={"evidence": ""}) if s.id == "affair" else s
                for s in CASE.secrets
            ]
        }
    )
    clara = build_brief(soft, derive(soft), "clara")

    assert not any(f.id == "heard:motive" for f in clara.hearsay)
    assert any(f.id == "heard:motive" for f in clara.guarded)


def test_a_first_question_carries_no_pressure() -> None:
    brief = build_brief(CASE, KNOW, "vera")
    opening = render_system(brief, [])

    assert "just come to you" in opening
    assert "being worked on" not in opening


def test_pressure_rises_with_the_number_of_questions() -> None:
    """`under_pressure` has been authored per character since D-044 and nothing
    ever told the character that pressure was high (D-089)."""
    brief = build_brief(CASE, KNOW, "vera")

    early = render_system(brief, [("q", "a")] * 2)
    late = render_system(brief, [("q", "a")] * 9)

    assert "question 3" in early
    assert "being worked on" not in early
    assert "question 10" in late
    assert "being worked on" in late


def test_pressure_never_obliges_anybody_to_talk() -> None:
    """A temperature, not a threshold. Nothing here opens anything, which is the
    whole point: the floor is objects (D-087), this is only the weather."""
    late = render_system(build_brief(CASE, KNOW, "vera"), [("q", "a")] * 30)

    assert "obliges you to give anything up" in late
    assert "Which one you are" in late


def test_a_held_back_condition_is_the_fastest_way_in_not_the_only_one() -> None:
    """The old wording made one sentence the sole key and told the character to
    stay put regardless, which is how a player asked about a forged reference a
    dozen times and never got it."""
    rendered = render_system(build_brief(CASE, KNOW, "vera"), [])

    assert "easiest way in, not the only one" in rendered
    assert "you stay with the story you told" not in rendered


def test_a_citation_spoken_aloud_is_taken_back_out() -> None:
    """Citations belong in `used`, which is the entire leakage design (D-038).

    A model asked for them there will sometimes write them into the speech as
    well, and the player gets 'I was in the workshop [self:s4]' said out loud
    (D-091).
    """
    said = strip_citations("I was in the workshop all evening [self:s4]. Ask Marijke.")

    assert said == "I was in the workshop all evening. Ask Marijke."


def test_every_shape_of_citation_is_recognised() -> None:
    messy = (
        "Fine. [secret:s_ledger] I took the pages. [truth:s4] I was in the office, "
        "and [saw:priya@s2] I saw her by the door. [heard:the_books] She told me."
    )

    assert "[" not in strip_citations(messy)


def test_a_character_may_still_use_square_brackets() -> None:
    """The pattern is a prefix, a colon and an id. Anything else is dialogue."""
    line = 'He wrote "[see attached]" and nothing else.'

    assert strip_citations(line) == line


def test_the_reply_the_player_sees_is_the_stripped_one() -> None:
    def cites_aloud(system, question):
        return {"speech": "The workshop [self:s1], all night.", "used": ["self:s1"]}

    reply = ask(build_brief(CASE, KNOW, "vera"), "Where were you?", cites_aloud)

    assert reply.speech == "The workshop, all night."
    assert reply.used == ["self:s1"], "the citation still counts, it just stops showing"


# --- the questioner is not one of them (D-111) -------------------------------


def _house_with_investigator():
    from mystery.example import OPENING_NIGHT
    from mystery.models import Investigator

    mystery = Mystery.model_validate(OPENING_NIGHT)
    return mystery.model_copy(
        update={
            "investigator": Investigator(
                role="A structural surveyor, engaged by the fund's insurers",
                why_here=(
                    "You were to hand your report to Eefje at breakfast; instead "
                    "the police are ninety minutes away on the dijk road."
                ),
                standing="What you have is the insurers' authority over this building.",
            )
        }
    )


def test_the_questioners_own_briefing_never_reaches_a_suspect() -> None:
    """From a played case: four of five suspects claimed to be the surveyor, and
    one had to reconcile it aloud with being a resident since January. `why_here`
    and `standing` are written to the player in the second person, and a prompt
    that already says "you" to the character cannot hold both (D-111)."""
    mystery = _house_with_investigator()
    knowledge = derive(mystery)

    for character in mystery.characters:
        if character.id == mystery.victim:
            continue
        brief = build_brief(mystery, knowledge, character.id)
        block = "\n".join(brief.investigator)

        assert "your report" not in block.lower(), character.id
        assert "what you have" not in block.lower(), character.id
        assert "surveyor" in block, "they should still know what the visitor is"


def test_a_suspect_is_told_the_visitor_is_not_them() -> None:
    mystery = _house_with_investigator()
    knowledge = derive(mystery)
    system = render_system(build_brief(mystery, knowledge, mystery.characters[0].id), [])

    assert "It is not you" in system


def test_the_shared_arithmetic_of_the_house_reaches_every_brief() -> None:
    """Six names to one suspect and nine to another, about the same list, because
    the only shared block was the death itself (D-111)."""
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT).model_copy(
        update={"common_ground": ["There are nine residents, so nine names on the list."]}
    )
    knowledge = derive(mystery)

    for character in mystery.characters:
        if character.id == mystery.victim:
            continue
        brief = build_brief(mystery, knowledge, character.id)
        assert any("nine names" in line for line in brief.common), character.id


def test_nobody_is_allowed_to_invent_a_number_about_the_house() -> None:
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT)
    knowledge = derive(mystery)
    system = render_system(build_brief(mystery, knowledge, mystery.characters[0].id), [])

    assert "Do not invent a number" in system


# --- what is actually on the table (D-112) -----------------------------------


def _case_with_an_object():
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT)
    secret = mystery.secrets[0]
    return mystery.model_copy(
        update={
            "secrets": [
                secret.model_copy(update={"evidence": "A bundle of letters in a ribbon"}),
                *mystery.secrets[1:],
            ]
        }
    ), secret


def test_showing_a_thing_reaches_the_prompt_even_when_it_unlocks_nothing() -> None:
    """Two of three shows in a played session changed the prompt by not one
    character, because the only trace of an object was the gate it happened to
    open. The player put something on the table and was answered by somebody
    behaving as though the table were empty (D-112)."""
    mystery, secret = _case_with_an_object()
    knowledge = derive(mystery)
    stranger = next(
        c.id
        for c in mystery.characters
        if c.id not in (secret.holder, mystery.victim) and c.id not in secret.known_by
    )

    empty = render_system(build_brief(mystery, knowledge, stranger), [])
    holding = render_system(build_brief(mystery, knowledge, stranger, shown={secret.id}), [])

    assert empty != holding
    assert "A bundle of letters in a ribbon" in holding
    assert "A bundle of letters in a ribbon" not in empty


def test_the_owner_of_a_thing_is_told_it_came_from_them() -> None:
    """Handing somebody their own letters back is not the same scene as showing
    them to the person who has been steaming them open."""
    mystery, secret = _case_with_an_object()
    knowledge = derive(mystery)

    brief = build_brief(mystery, knowledge, secret.holder, shown={secret.id})

    assert any("came from you" in line for line in brief.on_the_table)


def test_somebody_who_already_knew_is_not_told_it_is_new_to_them() -> None:
    mystery, secret = _case_with_an_object()
    if not secret.known_by:
        return
    knowledge = derive(mystery)
    who = secret.known_by[0]

    brief = build_brief(mystery, knowledge, who, shown={secret.id})

    assert any("already knew" in line for line in brief.on_the_table)
    assert not any("not seen this before" in line for line in brief.on_the_table)


def test_an_empty_table_says_so_rather_than_going_missing() -> None:
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT)
    knowledge = derive(mystery)
    system = render_system(build_brief(mystery, knowledge, mystery.characters[0].id), [])

    assert "not holding anything out to you" in system


def test_a_secret_with_no_object_cannot_be_put_on_the_table() -> None:
    """The hand is derived from secrets that have `evidence`. Anything else must
    not become a nameless thing in front of somebody."""
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT)
    bare = next(s for s in mystery.secrets if not s.evidence)
    knowledge = derive(mystery)

    brief = build_brief(mystery, knowledge, mystery.characters[0].id, shown={bare.id})

    assert brief.on_the_table == []


def test_an_object_is_weighed_against_what_they_are_holding_back() -> None:
    """Showing a thing does more than open the gates the generator happened to
    write. A person reacts to paper that makes their position untenable, and the
    only thing that can judge that is the model reading both at once, so the
    prompt has to join them (D-112)."""
    mystery, secret = _case_with_an_object()
    knowledge = derive(mystery)
    stranger = next(
        c.id
        for c in mystery.characters
        if c.id not in (secret.holder, mystery.victim) and c.id not in secret.known_by
    )

    system = render_system(build_brief(mystery, knowledge, stranger, shown={secret.id}), [])

    assert "against your own conditions" in system
    assert "does not work against paper" in system


def test_an_object_never_buys_a_fact_or_the_thing_they_never_give_up() -> None:
    """The fence. Reacting realistically must not become a way to move somebody
    off the hard line about who was where, or off a secret written as theirs
    forever."""
    mystery, secret = _case_with_an_object()
    knowledge = derive(mystery)

    system = render_system(
        build_brief(mystery, knowledge, mystery.killer, shown={secret.id}), []
    )

    assert "who was where and when that is not in FACTS" in system
    assert "stays yours forever, however much paper" in system


def test_a_thing_on_the_table_is_a_different_pressure_from_a_question() -> None:
    from mystery.agent import render_pressure

    mystery, secret = _case_with_an_object()
    knowledge = derive(mystery)
    who = mystery.characters[0].id

    asked_only = render_pressure(5, build_brief(mystery, knowledge, who))
    with_thing = render_pressure(5, build_brief(mystery, knowledge, who, shown={secret.id}))

    assert "not the same as being asked" in with_thing
    assert "not the same as being asked" not in asked_only


def test_the_hand_does_not_tell_the_player_what_to_do_with_it() -> None:
    """Provenance is a clue. "SHOW MARGIT" on every card was a walkthrough."""
    from mystery.web import PAGE

    assert "'show '+to" not in PAGE
    assert "give it back to" not in PAGE
    assert "from '+src" in PAGE, "where a thing came from is the part worth keeping"


def test_a_breaking_point_is_not_worded_as_a_password() -> None:
    """The block header said the condition is not a lock and the line under it
    said "you will say it only if". The specific one won, and conditions written
    as stage directions got played as trigger phrases (D-113)."""
    from mystery.example import OPENING_NIGHT

    mystery = Mystery.model_validate(OPENING_NIGHT)
    knowledge = derive(mystery)
    who = next(
        c.id
        for c in mystery.characters
        if c.id != mystery.victim
        and any(s.breaks_when for s in mystery.secrets if s.holder == c.id)
    )

    system = render_system(build_brief(mystery, knowledge, who), [])

    assert "only if:" not in system
    assert "rather than a password" in system
    assert "by another road has still arrived" in system
