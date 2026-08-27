"""Tests for validator rules.

Each rule gets at least two tests: one mystery it must reject, and one it must
accept. A rule with only the rejecting test can be satisfied by a validator that
rejects everything, which passes the suite and is useless.
"""

from mystery.models import Mystery
from mystery.validator import validate


def test_rejects_event_contradicting_the_timeline(prototype_02_bug: Mystery) -> None:
    result = validate(prototype_02_bug)

    assert not result.ok
    assert "V1" in result.failed_rules


def test_names_the_character_the_timeline_disagrees_about(prototype_02_bug: Mystery) -> None:
    result = validate(prototype_02_bug)

    assert len(result.violations) == 1
    assert "tomas" in result.violations[0].message


def test_accepts_a_fragment_whose_events_match_the_timeline(coherent_fragment: Mystery) -> None:
    result = validate(coherent_fragment)

    # Passing result.violations as the assertion message means a failure prints
    # what went wrong instead of just "assert False".
    assert result.ok, result.violations
