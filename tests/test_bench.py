"""Scoring a corpus without a model (D-152).

The sweep exists so that a change to a check or to the solver can be measured
against every case already paid for, rather than against the two hand-built
cases in this suite. These tests are about the sweep itself holding up; what it
reports is the corpus's business.
"""

import json

from test_agent import CASE

from mystery.bench import Score, report, score, sweep
from mystery.example import OPENING_NIGHT
from mystery.models import Mystery


def test_a_case_that_holds_scores_as_valid_and_winnable() -> None:
    got = score(Mystery.model_validate(OPENING_NIGHT), name="shipped")

    assert got.valid
    assert got.winnable
    assert got.cast == len(Mystery.model_validate(OPENING_NIGHT).characters)
    assert not got.broke


def test_what_broke_is_named_rather_than_counted() -> None:
    """A sweep that says "3 failed" is a sweep nobody acts on."""
    holed = CASE.model_copy(update={"constraints": []})
    got = score(holed, name="holed")

    assert got.broke == sorted(set(got.broke)), "each rule once, not once per violation"


def test_a_file_that_will_not_parse_is_reported_not_skipped(tmp_path) -> None:
    """A corpus accumulates by accident and collects empty and half-written
    files. Dropping them silently is how a sweep stops covering anything."""
    (tmp_path / "good.json").write_text(json.dumps(OPENING_NIGHT), encoding="utf-8")
    (tmp_path / "empty.json").write_text("", encoding="utf-8")
    (tmp_path / "half.json").write_text('{"title": "cut off', encoding="utf-8")

    got = sweep(tmp_path)

    assert len(got) == 3
    assert sum(1 for s in got if s.unreadable) == 2
    assert "would not parse" in report(got)


def test_the_report_calls_out_a_check_that_fires_on_everything() -> None:
    """An advisory that fires on 96% of cases is not a check, it is a complaint.
    The first real sweep found two of those, and the point of the column is that
    it tells you about the check rather than about the case."""
    everywhere = [
        Score(name=f"c{i}", cast=6, secrets=6, valid=True, winnable=True, fired=["A1"])
        for i in range(10)
    ]
    text = report(everywhere)

    assert "fires on nearly everything" in text
    assert "A1" in text


def test_an_empty_folder_says_so_rather_than_dividing_by_zero(tmp_path) -> None:
    assert report(sweep(tmp_path)) == "Nothing to score."


def test_scoring_calls_no_model(monkeypatch) -> None:
    """The whole promise of the sweep. If this ever needs a key, it has stopped
    being the cheap way to test the engine."""
    import mystery.generator as gen

    def explode(*args, **kwargs):
        raise AssertionError("a sweep must not call a model")

    monkeypatch.setattr(gen, "anthropic_drafter", explode)
    assert score(Mystery.model_validate(OPENING_NIGHT)).valid


def test_a_sweep_does_not_narrate_every_relocation(capsys) -> None:
    """The solver says what it moved, which is right for one case and noise for
    forty. The first real report arrived under six hundred lines of
    `solver.relocated_lie` and could not be read."""
    # Wouter claiming the green room, where only Tomas could contradict him, so
    # the solver has a lie to move (the shipped case no longer needs one, D-189).
    moved = {
        **OPENING_NIGHT,
        "false_claims": [
            {**c, "place": "green_room"} if c["character"] == "wouter" else c
            for c in OPENING_NIGHT["false_claims"]
        ],
    }
    score(Mystery.model_validate(moved))
    loud = capsys.readouterr().out

    import tempfile
    from pathlib import Path as P

    with tempfile.TemporaryDirectory() as folder:
        (P(folder) / "a.json").write_text(json.dumps(moved), encoding="utf-8")
        sweep(P(folder))
    quiet = capsys.readouterr().out

    assert "solver." in loud, "a single solve still explains itself"
    assert "solver." not in quiet, "a sweep does not"


def test_logging_comes_back_after_a_sweep(tmp_path) -> None:
    """A context manager that leaks its silence would turn off the logs for the
    rest of the process, which is the sort of thing found three days later."""
    import structlog

    before = structlog.get_config()["wrapper_class"]
    sweep(tmp_path)

    assert structlog.get_config()["wrapper_class"] is before


def test_drafts_from_before_secrets_are_left_out_of_the_base_rates() -> None:
    """A draft with no secrets predates the layer half these checks measure, and
    counting it drags every rate towards "everything is broken"."""
    mixed = [
        Score(name="old", cast=6, secrets=0, valid=True, winnable=False, fired=["A3"]),
        Score(name="new", cast=6, secrets=7, valid=True, winnable=True, fired=["A1"]),
    ]
    text = report(mixed)

    rates = text.split("how often")[1]
    assert "1 older draft has no secrets" in text
    assert "A1" in rates
    assert "A3" not in rates, "a check that only the pre-secrets draft fired"


def test_a_mixed_corpus_gets_a_column_per_cohort(tmp_path) -> None:
    """Saying the rates belong to no version and then printing them anyway was
    half a report (D-175).

    The stamp exists so a change can be seen to have landed, and a pooled rate
    over two prompt versions cannot show that however loudly the header warns.
    """
    from mystery.bench import report, sweep
    from mystery.models import Mystery

    case = Mystery.model_validate(OPENING_NIGHT)
    for name, version in (("a", ""), ("b", ""), ("c", "7884377a/opus-5")):
        stamped = case.model_copy(update={"built_with": version})
        (tmp_path / f"{name}.json").write_text(stamped.model_dump_json(), encoding="utf-8")

    page = report(sweep(tmp_path))

    assert "by the instructions that made the draft" in page
    assert "pre-stamp" in page and "7884377a" in page
    assert "n=2" in page and "n=1" in page


def test_one_cohort_keeps_the_plain_list(tmp_path) -> None:
    """A column per cohort is worth the width only when there is something to
    compare. One set of instructions gets the single column it always had."""
    from mystery.bench import report, sweep
    from mystery.models import Mystery

    case = Mystery.model_validate(OPENING_NIGHT).model_copy(
        update={"built_with": "7884377a/opus-5"}
    )
    for name in ("a", "b"):
        (tmp_path / f"{name}.json").write_text(case.model_dump_json(), encoding="utf-8")

    page = report(sweep(tmp_path))

    assert "by the instructions that made the draft" not in page
    assert "how often each advisory fires" in page
