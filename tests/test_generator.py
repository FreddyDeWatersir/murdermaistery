"""Tests for the generator.

Not one of these calls a model. The whole point of keeping the model boundary as
a plain callable is that a fake can stand in its place, so the suite runs
offline, free, and in milliseconds. If testing this needed an API key, it would
stop being run.
"""

import json

import pytest

from mystery.example import OPENING_NIGHT as SHIPPED
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


def test_the_page_javascript_has_no_broken_escapes() -> None:
    """The embedded page is a Python string holding JavaScript, so a regex like
    /\\.$/ is an invalid Python escape: a warning today, an error on a later
    Python (D-110).

    Compiles **the source file**, not the built string. The first version of this
    test compiled `PAGE`, which is the value after Python has already swallowed
    the bad escape, so it could never see one. It passed while a fresh
    `SyntaxWarning` sat in the module, put there by the briefing screen a few
    days later (D-128). A test that examines the output of the step that loses
    the information cannot check that step.
    """
    import warnings
    from pathlib import Path

    import mystery.web as web

    source = Path(web.__file__).read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error", SyntaxWarning)
        compile(source, web.__file__, "exec")

    assert "/\\.$/" in web.PAGE, "the JavaScript should still contain the regex itself"


def test_the_draft_ceiling_is_above_what_a_draft_actually_writes() -> None:
    """Two drafts in one run came back at exactly the old ceiling, truncated,
    and arrived as schema errors (D-110). The estimate is measured from the same
    logs, so the two numbers have to stay in step."""
    import inspect

    import mystery.generator as gen
    from mystery.generator import TYPICAL_DRAFT

    source = inspect.getsource(gen.anthropic_drafter)
    ceiling = int(source.split("max_tokens=")[1].split(",")[0])

    assert ceiling > TYPICAL_DRAFT[1] * 1.5, (
        f"a typical draft writes {TYPICAL_DRAFT[1]} tokens and the ceiling is "
        f"{ceiling}: too little headroom, and truncation reads as a schema error"
    )


def test_the_placeholder_setting_is_refused_before_anything_is_spent() -> None:
    """The literal `"..."` from the example commands, pasted through, bought
    three Opus drafts of a murder set in nothing (D-110)."""
    from mystery.generator import complaint_about_setting

    for placeholder in ["...", "…", "", "   ", '"..."', "-"]:
        complaint = complaint_about_setting(placeholder)
        assert complaint, f"{placeholder!r} was accepted as a setting"
        assert "placeholder" in complaint or "too thin" in complaint


def test_a_real_setting_is_not_refused() -> None:
    """The guard has one job and must not develop opinions about prose."""
    from mystery.generator import complaint_about_setting

    for setting in [
        "a private view at a small art gallery",
        "the last night of a residency at an old house",
        "a robotics lab, the night before the demo",
        "a ferry, fogbound",
    ]:
        assert complaint_about_setting(setting) is None, setting


def test_the_setting_guard_stops_the_web_entry_point() -> None:
    """A unit on the function is not the thing that failed. What failed was a
    command line, so the assertion is about the command line."""
    from mystery.web import main

    assert main(["--setting", "..."]) == 2


def test_the_setting_guard_stops_the_cli_entry_point() -> None:
    from mystery.cli import main

    assert main(["--setting", "..."]) == 2


def test_the_page_javascript_parses() -> None:
    """The page is a Python string containing a program in another language, so
    Python's own syntax check says nothing about it. Two escaping bugs shipped
    to a browser this way in one afternoon: `\\'` and `\\n` written once too few
    times, which Python swallowed happily and node did not.

    Skipped rather than failed where node is absent, because the suite's promise
    is that it runs anywhere with no network and no keys.
    """
    import shutil
    import subprocess
    import tempfile

    node = shutil.which("node")
    if node is None:
        pytest.skip("no node on this machine")

    from mystery import web

    script = web.PAGE.split("<script>")[1].split("</script>")[0]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(script)
        path = f.name

    done = subprocess.run([node, "--check", path], capture_output=True, text=True)

    assert done.returncode == 0, done.stderr


def test_a_draft_that_big_has_to_be_streamed() -> None:
    """The SDK refuses a non-streaming request whose `max_tokens` implies it
    could run past ten minutes, client side, before anything is sent. Raising
    the ceiling to twenty-four thousand crossed that line and the first real run
    afterwards died on it (D-148).

    Nothing in this suite touches the SDK, so the only thing that can be checked
    is the shape of the call. Which is enough: the two numbers have to move
    together, and this says so."""
    import inspect

    import mystery.generator as gen

    source = inspect.getsource(gen.anthropic_drafter)
    ceiling = int(source.split("max_tokens=")[1].split(",")[0])

    if ceiling <= 8192:
        return  # small enough that the SDK allows a plain call

    assert "client.messages.stream(" in source
    assert "client.messages.create(" not in source, (
        f"max_tokens is {ceiling}, which the SDK will refuse without streaming"
    )


# --- the briefing is repaired, not rejected (D-149) --------------------------


def _briefed(text: str) -> Mystery:
    from mystery.models import Character, Place, Slot

    return Mystery(
        title="t",
        killer="devika",
        victim="ravi",
        characters=[
            Character(id="devika", name="Devika Menon"),
            Character(id="anna", name="Annapurna Menon"),
            Character(id="ravi", name="Ravi Nair"),
        ],
        places=[Place(id="hall", name="Hall")],
        slots=[Slot(id="s0", label="eight", index=0)],
        commission=text,
    )


def test_a_named_suspect_is_taken_out_of_the_briefing() -> None:
    """Two drafts in three came back naming somebody and each rejection cost a
    fresh Opus call. It has one right answer and no judgement in it, so it is
    repaired for nothing instead."""
    from mystery.generator import unname_the_commission

    fixed = unname_the_commission(
        _briefed("The family have settled on Devika Menon and want it written down.")
    ).commission

    assert "Devika" not in fixed
    assert fixed == "The family have settled on one of them and want it written down."


def test_the_whole_name_goes_at_once() -> None:
    """Word by word, "Devika Menon" becomes "one of them that person", which is
    worse than the name was."""
    from mystery.generator import unname_the_commission

    fixed = unname_the_commission(_briefed("Everyone blames Devika Menon.")).commission

    assert fixed.count("one of them") == 1


def test_the_same_person_twice_is_still_one_person() -> None:
    from mystery.generator import unname_the_commission

    fixed = unname_the_commission(
        _briefed("It was Devika. Devika drank and shouted.")
    ).commission

    assert fixed == "It was one of them. One of them drank and shouted."


def test_two_people_are_two_people() -> None:
    from mystery.generator import unname_the_commission

    fixed = unname_the_commission(_briefed("Devika says it was Annapurna.")).commission

    assert fixed == "One of them says it was another of them."


def test_a_possessive_reads_as_one() -> None:
    from mystery.generator import unname_the_commission

    fixed = unname_the_commission(
        _briefed("They want Devika Menon's name on the paper.")
    ).commission

    assert fixed == "They want their name on the paper."


def test_the_victim_may_still_be_named() -> None:
    """They are on every other screen already."""
    from mystery.generator import unname_the_commission

    text = "Write a plain account of how Ravi Nair came to die."

    assert unname_the_commission(_briefed(text)).commission == text


def test_a_briefing_that_names_nobody_is_left_alone() -> None:
    from mystery.generator import unname_the_commission

    text = "They have already settled on one name between them."

    assert unname_the_commission(_briefed(text)).commission == text


def test_an_unwinnable_case_is_sent_back_rather_than_paid_for_and_binned() -> None:
    """A real run died this way: three drafts, a dollar ten, and the third case
    was refused at the end because the killer's motive was known to nobody but
    the killer. The program already treated that as fatal; it just never said so
    to the one thing that could fix it (D-149)."""
    from mystery.generator import _unreachable

    sealed = Mystery.model_validate(SHIPPED)
    sealed = sealed.model_copy(
        update={
            "secrets": [
                s.model_copy(update={"known_by": [], "revealed_by": "nothing_at_all"})
                if s.is_motive
                else s
                for s in sealed.secrets
            ]
        }
    )

    said = _unreachable(sealed)

    assert said
    assert any("motive" in m.lower() for m in said)
    assert not _unreachable(Mystery.model_validate(SHIPPED))


def test_a_cached_draft_is_repaired_on_the_way_out_too() -> None:
    """A cached case is precisely the one nobody is going to pay to draft again,
    and every draft cached before the repair existed still names somebody in its
    briefing (D-149)."""
    import tempfile
    from pathlib import Path

    named = _briefed("The family have settled on Devika Menon.")
    request = GenerationRequest(setting="a house", seed=1)

    with tempfile.TemporaryDirectory() as folder:
        cache = Path(folder)
        (cache / f"{request.cache_key()}.json").write_text(
            named.model_dump_json(), encoding="utf-8"
        )

        def never_called(req, complaints):
            raise AssertionError("a cache hit must not call the model")

        got = generate(request, drafter=never_called, cache_dir=cache)

    assert "Devika" not in got.commission


# --- the shape governs (D-151) -----------------------------------------------


def test_the_shape_is_the_first_thing_the_model_reads() -> None:
    """It used to sit on the fifth line of the request, after the cast size,
    while three thousand characters of standing instruction insisted on a
    pattern of lying that several shapes forbid. A real case drew "the killer
    never lies" and wrote "the killer lies about a room"."""
    from mystery.generator import _user_prompt

    prompt = _user_prompt(GenerationRequest(setting="a house", seed=1))

    assert prompt.startswith("SHAPE OF THE SOLUTION")
    assert prompt.index("SHAPE OF THE SOLUTION") < prompt.index("Setting:")
    assert "this wins" in prompt


def test_the_standing_instructions_do_not_decide_who_lies() -> None:
    """Who lies and how many is the shape's business. The system prompt used to
    say "three people lie about where they were" and call it the most important
    instruction here, which is a direct contradiction of four of the seven
    shapes and the louder half of it."""
    from mystery.generator import SYSTEM_PROMPT

    assert "Three people lie about where they were" not in SYSTEM_PROMPT
    assert "SHAPE OF THE SOLUTION" in SYSTEM_PROMPT
    assert "the shape wins" in SYSTEM_PROMPT


def test_every_shape_says_who_appears_in_false_claims() -> None:
    """The doctrine moved out of the standing instructions, so each shape now
    has to carry its own. A shape that says nothing gets whatever the model
    remembers from the examples, which is how this went wrong."""
    from mystery.topology import LIBRARY

    for name, shape in LIBRARY.items():
        assert "false_claims" in shape.brief, f"{name} does not say who lies"


def test_the_prompt_does_not_ask_for_what_nothing_shows() -> None:
    """Objects with paths came off the notebook in D-139 and the prompt went on
    asking for them for three weeks, at about 1,260 tokens a draft (D-151)."""
    from mystery.generator import SYSTEM_PROMPT

    assert "objects with paths of their own" not in SYSTEM_PROMPT


def test_the_retired_object_checks_are_not_run() -> None:
    """Keeping them in the module is fine. Running them means complaining about
    an absence we chose."""
    from mystery.critique import (
        ADVISORIES,
        not_every_journey_points_at_the_killer,
        something_in_this_house_moved,
    )

    assert something_in_this_house_moved not in ADVISORIES
    assert not_every_journey_points_at_the_killer not in ADVISORIES


def _clashing_draft() -> dict:
    """The failure that cost $1.20 in one evening: two scenes claiming the same
    person in different rooms at the same hour (D-156).

    Built on the shipped case rather than on `GOOD_DRAFT`, because what is being
    tested is whether the *solver* can rescue a clash, and a four-person
    three-slot skeleton has nowhere to move a scene to. The real drafts this
    happens to are full cases, and that is what this has to be.
    """
    draft = json.loads(json.dumps(SHIPPED))
    bound = [c for c in draft["constraints"] if c.get("place") and c.get("slot")]
    first, second = next(
        (a, b)
        for i, a in enumerate(bound)
        for b in bound[i + 1 :]
        if set(a["people"]) & set(b["people"]) and a["place"] != b["place"]
    )
    second["slot"] = first["slot"]
    return draft


def test_a_clash_the_solver_would_fix_does_not_cost_a_redraft() -> None:
    """V6 said "no repair exists" and `_resolve_clashes` has been the repair the
    whole time. Manufacturing this clash in thirty-three corpus drafts, the
    solver fixed thirty-two (D-156).

    `attempts=1` is the assertion: there is no second draft to fall back on, so
    this passes only if the first one was accepted.
    """
    from mystery.solver import solve_until_valid

    clashing = _clashing_draft()
    proposed = validate(Mystery.model_validate(clashing), phase="proposed")
    assert "V6" in {v.rule for v in proposed.violations}, "the fixture must clash"

    drafter = _flaky_drafter(clashing)
    mystery = generate(REQUEST, drafter=drafter, attempts=1)

    assert len(drafter.calls) == 1, "a repairable clash must not spend a redraft"
    _, _, violations = solve_until_valid(mystery, seed=REQUEST.seed)
    assert not violations, "accepted on the promise that solving fixes it"


def test_a_clash_the_solver_cannot_fix_still_goes_back_to_the_model() -> None:
    """The free second opinion must not become a way of accepting anything. An
    invented character is unrepairable at every layer."""
    hopeless = _clashing_draft()
    hopeless["constraints"][0]["people"] = ["the_butler"]

    with pytest.raises(GenerationFailed) as caught:
        generate(REQUEST, drafter=_fake_drafter(hopeless), attempts=1)

    assert "the_butler" in str(caught.value)


def test_an_invented_room_is_unbound_rather_than_rejected() -> None:
    """A scene set in a conservatory the map does not have has exactly one right
    answer: it is a scene that does not know its room, and finding one is the
    solver's job (D-149, D-156)."""
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0].update({"place": "conservatory", "slot": "s1"})

    drafter = _flaky_drafter(invented)
    mystery = generate(REQUEST, drafter=drafter, attempts=1)

    assert len(drafter.calls) == 1, "an invented room must not spend a redraft"
    scene = next(c for c in mystery.constraints if c.id == "tryst")
    assert scene.place is None, "the invented room should have been dropped"
    assert scene.slot == "s1", "everything else about the scene should survive"


def test_an_invented_person_is_not_unbound_away() -> None:
    """The half of V4 that stays fatal. Dropping a name nobody can resolve would
    silently change the story rather than repair it."""
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0]["people"] = ["roos", "the_butler"]

    with pytest.raises(GenerationFailed):
        generate(REQUEST, drafter=_fake_drafter(invented), attempts=1)


def test_a_rejected_draft_is_written_down(tmp_path) -> None:
    """Every measurement of this engine is taken over the drafts that passed, so
    nothing could say what the gate rejects or how often (D-156)."""
    cache = tmp_path / "mysteries"
    invented = json.loads(json.dumps(GOOD_DRAFT))
    invented["constraints"][0]["people"] = ["roos", "the_butler"]

    with pytest.raises(GenerationFailed):
        generate(REQUEST, drafter=_fake_drafter(invented), cache_dir=cache, attempts=2)

    wreckage = sorted((tmp_path / "rejected").glob("*.json"))
    assert len(wreckage) == 2, "one file per rejected attempt"

    kept = json.loads(wreckage[0].read_text(encoding="utf-8"))
    assert any("the_butler" in c for c in kept["complaints"])
    assert kept["draft"]["title"] == "The Private View", "the draft itself must be kept"
    assert kept["setting"] == REQUEST.setting


def test_an_unparseable_draft_is_kept_too(tmp_path) -> None:
    """The one you most want back: it never became a Mystery, so nothing else in
    the pipeline could have recorded it."""
    cache = tmp_path / "mysteries"

    with pytest.raises(GenerationFailed):
        generate(REQUEST, drafter=_fake_drafter({"title": "half"}), cache_dir=cache, attempts=1)

    kept = sorted((tmp_path / "rejected").glob("*.json"))
    assert len(kept) == 1
    assert json.loads(kept[0].read_text(encoding="utf-8"))["draft"] == {"title": "half"}


def _dead_man_at_dinner() -> dict:
    """A draft that passes the proposed gate and has no valid arrangement.

    The failure that cost another 37 cents: the model sat the victim at a
    communal meal an hour after killing him. V7 is a final rule only, so the
    proposed gate waved it through, it was cached, and `web.py` then failed all
    twenty-four arrangements with two paid attempts unspent (D-157).
    """
    draft = json.loads(json.dumps(SHIPPED))
    murder = next(c for c in draft["constraints"] if c["id"] == "murder")
    order = {s["id"]: s["index"] for s in draft["slots"]}
    later = next(s["id"] for s in draft["slots"] if s["index"] > order[murder["slot"]])
    victim = draft["victim"]
    # Every hour the victim is still alive for is already an exclusive scene, so
    # the extra one below has nowhere earlier to be moved to. That is what made
    # the real draft impossible rather than merely misarranged: its victim had
    # two live slots and both were private scenes with the killer.
    for scene in draft["constraints"]:
        if victim in scene["people"]:
            scene["exclusive"] = True
    draft["constraints"].append(
        {
            "id": "the_wake",
            # Somebody who is in none of the victim's other scenes, so the wake
            # cannot be quietly folded into one of them.
            "people": [victim, "renske"],
            "place": "green_room",
            "slot": later,
            "description": "A quiet drink, with a man who has been dead for an hour.",
        }
    )
    return draft


def _too_many_private_hours() -> dict:
    """Unsolvable, and clean at the proposed gate, which is the combination that
    matters (D-157).

    One character is wanted alone with six different people, in scenes with no
    place or slot of their own, on an evening of five hours. Nothing at the
    proposed gate can object, because nothing is bound and so no clash is written
    down anywhere. The solver is the only thing that finds out, when it runs out
    of hours to give her private scenes.
    """
    draft = json.loads(json.dumps(SHIPPED))
    guests = ["gerda", "pim"]
    draft["characters"] += [{"id": g, "name": g.title()} for g in guests]
    for who in guests:
        for slot in draft["slots"]:
            draft.setdefault("placements", {}).setdefault(who, {})[slot["id"]] = draft[
                "places"
            ][0]["id"]

    alone_with = [
        c["id"]
        for c in draft["characters"]
        if c["id"] not in ("renske", draft["victim"])
    ]
    for who in alone_with:
        draft["constraints"].append(
            {
                "id": f"renske_alone_with_{who}",
                "people": ["renske", who],
                "exclusive": True,
                "description": f"Renske gets {who} on their own.",
            }
        )
    return draft


def test_a_draft_with_no_valid_arrangement_is_redrafted_not_returned() -> None:
    """The proposed gate passing is not the same as the draft being usable, and
    for one evening the program could not tell the difference (D-157)."""
    doomed = _too_many_private_hours()
    assert validate(Mystery.model_validate(doomed), phase="proposed").ok, (
        "the fixture has to pass the proposed gate, or it tests nothing"
    )

    drafter = _flaky_drafter(doomed, SHIPPED)
    mystery = generate(REQUEST, drafter=drafter)

    assert len(drafter.calls) == 2, "an unsolvable draft has to buy a redraft"
    assert drafter.calls[1], "and the model has to be told what was wrong"
    assert not any(c.id.startswith("renske_alone") for c in mystery.constraints)


def test_an_unsolvable_draft_is_not_cached(tmp_path) -> None:
    """Caching one would make that seed fail identically forever."""
    doomed = _dead_man_at_dinner()

    with pytest.raises(GenerationFailed):
        generate(REQUEST, drafter=_fake_drafter(doomed), cache_dir=tmp_path, attempts=1)

    assert not list(tmp_path.glob("*.json"))


def test_a_cached_draft_that_cannot_be_arranged_is_not_handed_back(tmp_path) -> None:
    """Drafts cached before D-157 include unplayable ones. A cache hit that
    cannot be solved is worse than a miss: it never redrafts."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    doomed = Mystery.model_validate(_dead_man_at_dinner())
    (tmp_path / f"{REQUEST.cache_key()}.json").write_text(
        doomed.model_dump_json(indent=2), encoding="utf-8"
    )

    drafter = _flaky_drafter(SHIPPED)
    mystery = generate(REQUEST, drafter=drafter, cache_dir=tmp_path)

    assert len(drafter.calls) == 1, "the broken cache entry should have been passed over"
    assert not any(c.id == "the_wake" for c in mystery.constraints)


def test_a_scene_with_the_victim_after_the_murder_is_freed_by_the_solver() -> None:
    """The sibling of D-152's rule: that one frees a scene bound into the room
    the body is in, this frees a scene bound to the body. Across the corpus,
    manufacturing this failure in twenty-seven healthy drafts, the solver
    repaired six before and twenty-seven after (D-157)."""
    from mystery.solver import solve_until_valid

    draft = json.loads(json.dumps(SHIPPED))
    murder = next(c for c in draft["constraints"] if c["id"] == "murder")
    order = {s["id"]: s["index"] for s in draft["slots"]}
    later = next(s["id"] for s in draft["slots"] if s["index"] > order[murder["slot"]])
    # An ordinary scene the victim is in, dragged to after his death. Unlike the
    # wake above, this one has somewhere earlier it can go.
    threat = next(c for c in draft["constraints"] if c["id"] == "the_threat")
    threat["slot"] = later

    solved, _, violations = solve_until_valid(Mystery.model_validate(draft), seed=0)

    assert not violations
    moved = next(c for c in solved.constraints if c.id == "the_threat")
    assert order[moved.slot] <= order[murder["slot"]], "the scene must move back before the death"


def test_the_request_tells_the_model_the_victim_s_time_budget() -> None:
    """The model does not count on its own (D-158).

    Measured over the corpus it writes 3.56 scenes with the victim regardless of
    when the murder was dealt, so at an early murder slot the draft is born
    unsatisfiable. The arithmetic is trivial and was simply never stated.
    """
    from mystery.generator import _when

    asked = _when(GenerationRequest(setting="a harvest", slot_count=5, seed=632452))

    assert "victim's whole life" in asked or "whole life" in asked
    assert "alive for slots" in asked
    assert "secrets" in asked, "it has to say where the material that does not fit goes"
    assert "later is after they are dead" in asked


def test_the_prompt_does_not_hard_code_the_announcement() -> None:
    """The line that made every case the same plot (D-161).

    "A good case usually has an earlier private scene between those same two
    people, **the one where the victim says the thing that gets them killed**"
    turned a suggestion about structure into a requirement about content, and
    twenty four of twenty six real motives came out as a deadline announced in
    private minutes before the death.
    """
    from mystery.generator import SYSTEM_PROMPT

    assert "does not have to be where the victim says" in SYSTEM_PROMPT
    assert "Do not turn every motive into an announcement" in SYSTEM_PROMPT
    assert "do not invent one" in SYSTEM_PROMPT


def test_the_prompt_does_not_assume_the_killer_arranged_to_be_alone() -> None:
    """Twenty eight cases read end to end: in twenty three the killer asked, took,
    brought or followed the victim somewhere, and in none was the victim simply
    already there (D-165).

    That makes every murder premeditated, which is why the evening keeps needing
    a deadline however the motive was dealt.
    """
    from mystery.generator import SYSTEM_PROMPT

    assert "not always the killer's doing" in SYSTEM_PROMPT
    assert "they need an" in SYSTEM_PROMPT and "opportunity" in SYSTEM_PROMPT


def test_the_prompt_does_not_require_the_victim_to_own_the_place() -> None:
    """The victim was the proprietor in 22 of 28, so the cast wrote itself as the
    people who worked for them: a manager, a foreman, a cellarman and one
    outsider, every time (D-165)."""
    from mystery.generator import SYSTEM_PROMPT

    assert "does not have to own the place" in SYSTEM_PROMPT


def test_the_victims_own_name_survives_the_briefing_repair() -> None:
    """Sixteen of fifty six cases give a suspect the victim's surname, because a
    niece, a nephew and a daughter are the commonest things in this cast (D-167).

    Replacing that surname rewrote the dead woman's own name in the first
    sentence the player reads: "Doña Amalia one of them was found at the foot of
    the river steps".
    """
    from mystery.generator import unname_the_commission

    family = Mystery.model_validate(
        {
            **json.loads(json.dumps(GOOD_DRAFT)),
            "victim": "roos",
            "killer": "gustav",
            "characters": [
                {"id": "roos", "name": "Amalia Reccioli"},
                {"id": "gustav", "name": "Ines Reccioli de Farias"},
                {"id": "lelia", "name": "Julieta Bossani"},
                {"id": "mihail", "name": "Cosme Lattanzi"},
            ],
            "commission": (
                "Amalia Reccioli was found at the foot of the steps, and Ines "
                "Reccioli de Farias will not have it."
            ),
        }
    )

    repaired = unname_the_commission(family).commission

    assert "Amalia Reccioli was found" in repaired, "the victim may be named"
    assert "Ines" not in repaired, "the suspect may not"


def test_v13_does_not_report_a_name_the_victim_shares() -> None:
    from mystery.validator import validate

    family = Mystery.model_validate(
        {
            **json.loads(json.dumps(GOOD_DRAFT)),
            "victim": "roos",
            "killer": "gustav",
            "characters": [
                {"id": "roos", "name": "Amalia Reccioli"},
                {"id": "gustav", "name": "Ines Reccioli de Farias"},
                {"id": "lelia", "name": "Julieta Bossani"},
                {"id": "mihail", "name": "Cosme Lattanzi"},
            ],
            "commission": "Amalia Reccioli was found at the foot of the steps.",
        }
    )

    assert not [v for v in validate(family, phase="proposed").violations if v.rule == "V13"]


def test_a_draft_records_the_model_as_well_as_the_prompt() -> None:
    """The prompt hash stopped being enough the moment there were two models to
    choose between (D-171). A corpus that cannot tell them apart is D-166 again
    in a different column.
    """
    def wrote_it(request, complaints):
        return SHIPPED

    wrote_it.model = "claude-opus-5-5"

    stamped = generate(REQUEST, drafter=wrote_it)

    assert stamped.built_with.endswith("/opus-5-5")
    assert "/" in stamped.built_with, "the prompt version is still the first half"


def test_a_drafter_with_no_model_still_stamps_the_prompt() -> None:
    """Every fake in this suite is a plain function, and none of them should have
    to grow an attribute to keep the pipeline working."""
    stamped = generate(REQUEST, drafter=_fake_drafter(SHIPPED))

    assert stamped.built_with and "/" not in stamped.built_with


def test_the_rates_cover_the_models_actually_used() -> None:
    """Getting a price wrong by a factor of forty five cost real money once
    (D-082), so the table has to carry whatever the defaults point at."""
    from mystery.generator import DRAFT_MODEL, RATES, VOICE_MODEL

    assert DRAFT_MODEL in RATES and VOICE_MODEL in RATES
    assert RATES["claude-opus-5-5"] == (4.0, 20.0), "Opus 5.5 is $4 in, $20 out"


def test_a_model_that_cannot_force_a_tool_call_is_refused_before_it_is_paid_for() -> None:
    """Opus 5.5 returns a 400 for `tool_choice: {"type": "tool"}`, which is how
    this pipeline guarantees a valid case (D-002, D-173).

    Found in the middle of a batch that had been announced at $2.41, so the
    useful moment to say so is before the first call rather than after it.
    """
    from mystery.generator import complaint_about_model

    assert complaint_about_model("claude-opus-5-5")
    assert "output_config" in complaint_about_model("claude-opus-5-5")


def test_a_model_nobody_has_tested_is_not_refused() -> None:
    """A deny list, not an allow list. What is known is which models refuse;
    treating everything unlisted as broken would block the next one that works
    and would be a claim nobody checked."""
    from mystery.generator import complaint_about_model

    assert complaint_about_model("claude-opus-5") is None
    assert complaint_about_model("claude-sonnet-5-5") is None
    assert complaint_about_model("some-model-from-next-year") is None


def test_the_drafting_default_is_a_model_that_can_do_it() -> None:
    from mystery.generator import DRAFT_MODEL, complaint_about_model

    assert complaint_about_model(DRAFT_MODEL) is None
