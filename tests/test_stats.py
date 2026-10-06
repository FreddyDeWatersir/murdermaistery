"""The report that is read before playing (D-185): it measures, and it spoils nothing."""

import json

from test_agent import CASE

from mystery.stats import collect, report, trail_depths


def _shelve(var, case, case_id="a-small-gathering-0001", topology="the_lie", seed=7):
    folder = var / "cases"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"20261005T000000.000__{case_id}.json").write_text(
        json.dumps(
            {
                "id": case_id,
                "title": case.title,
                "setting": "a small gathering",
                "topology": topology,
                "seed": seed,
                "saved": "2026-10-05T00:00:00+00:00",
                "mystery": case.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )


def _reject(var, case, why, n=1, built_with="abcd1234/opus-5"):
    folder = var / "rejected"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"key{n}-1.json").write_text(
        json.dumps(
            {
                "key": f"key{n}",
                "attempt": 1,
                "seed": 7,
                "setting": "a small gathering",
                "topology": "the_lie",
                "complaints": [why],
                "built_with": built_with,
                "draft": case.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )


def test_depth_is_counted_in_gates() -> None:
    motive, trail = trail_depths(CASE)
    assert motive == 1, "the fixture's motive sits behind the affair"
    assert trail == 0


def test_yield_and_rejections_are_counted_per_prompt_version(tmp_path) -> None:
    stamped = CASE.model_copy(update={"built_with": "abcd1234/opus-5"})
    _shelve(tmp_path, stamped)
    _reject(tmp_path, CASE, "the deepest thing pointing at anybody else is 0", n=1)
    _reject(tmp_path, CASE, "'x' is required in two places at 's2'", n=2)

    text = report(collect(tmp_path))
    assert "PROMPT abcd1234/opus-5" in text
    assert "shelved 1   rejected calls 2" in text
    assert "about $1.23 per shelved case" in text, "unpriced drafts at the flat estimate"
    assert "A24 1" in text and "structure 1" in text


def test_recorded_prices_replace_the_estimate(tmp_path) -> None:
    """Two stages cost different amounts, so each call carries its own (D-191)."""
    _shelve(tmp_path, CASE.model_copy(update={"built_with": "v2", "spent_usd": 0.5}))
    folder = tmp_path / "rejected"
    folder.mkdir(exist_ok=True)
    (folder / "k-skeleton-1.json").write_text(
        json.dumps(
            {
                "stage": "skeleton",
                "usd": 0.15,
                "built_with": "v2",
                "complaints": ["x"],
                "draft": {k: v for k, v in CASE.model_dump(mode="json").items() if k != "title"},
            }
        ),
        encoding="utf-8",
    )
    records = collect(tmp_path)
    text = report(records)
    assert "$0.65 per shelved case" in text
    assert "skeleton 1" in text
    skeleton = next(r for r in records if r.stage == "skeleton")
    assert not skeleton.fired & {"A11", "A22"}, "the prose stage writes those"


def test_a_played_case_is_marked_and_counted_once(tmp_path) -> None:
    _shelve(tmp_path, CASE)
    session = {"id": "s1", "case_id": "a-small-gathering-0001", "statements": [{}, {}, {}]}
    for folder in ("sessions", "transcripts"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "s1.json").write_text(json.dumps(session), encoding="utf-8")

    assert "played (3 q)" in report(collect(tmp_path))


def test_nothing_in_it_spoils_a_case(tmp_path) -> None:
    """Read before playing: no suspect, no secret, and no shape unless asked."""
    _shelve(tmp_path, CASE, topology="the_finder")
    text = report(collect(tmp_path))

    for person in CASE.characters:
        assert person.name not in text
    for secret in CASE.secrets:
        # Not the id: the fixture's motive is literally called "motive".
        assert secret.summary not in text
    assert "the_finder" not in text
    assert "the_finder" in report(collect(tmp_path), spoilers=True)


def test_a_draft_sent_back_by_the_measures_is_filed_under_normal() -> None:
    from mystery.measures import NORMAL, Measures, complaints
    from mystery.stats import _why

    assert _why(complaints(Measures(shortcuts=["alone"]), NORMAL)) == "Normal"
