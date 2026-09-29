"""Score every case you already own, without calling a model (D-152).

The question this exists to answer: how do you test the engine without playing a
case. Most of the answer is that **you do not need the model to test the thing
the model is judged by.** A draft is a file. Validation, solving, solvability and
all twenty-one advisories are arithmetic over that file, so every draft ever
cached is a test case that costs nothing to run again.

What a sweep is good for, in order of how much it has actually paid off:

**Finding bugs the suite cannot.** The tests use two hand-built cases and the
shipped example. Twenty-five real drafts are twenty-five shapes nobody designed,
and the first sweep found a V10 failure on two of them: a scene the model had
bound into the murder room after the murder, which the solver dutifully obeyed.
The seal from D-147 covers the three places the solver *chooses* a room. It did
not cover the one place it does not choose.

**Setting thresholds from the distribution instead of from taste.** An advisory
that fires on 96% of cases is not a check, it is a complaint. The first sweep
found two of those. Difficulty bands in particular have to come from base rates,
or "hard" is just "impossible" and every draft costs 38 cents to find out.

**Seeing a change land.** Edit a check, sweep, and read what moved. A rule that
changes nothing across twenty-five cases did not do what you thought.

What it cannot see is whether a case is any *fun*, and nothing here pretends
otherwise. This measures the properties; a person measures the evening.
"""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from mystery.critique import critique
from mystery.models import Mystery
from mystery.solvable import analyse
from mystery.solver import quietly, solve_until_valid


@dataclass
class Score:
    """One case, measured."""

    name: str
    built_with: str = ""
    cast: int = 0
    secrets: int = 0
    valid: bool = False
    winnable: bool = False
    broke: list[str] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)
    unreadable: str = ""


def score(mystery: Mystery, name: str = "", seed: int = 0) -> Score:
    """Solve a draft and measure it. No model, no network, no spend."""
    solved, _, broke = solve_until_valid(mystery, seed=seed)
    reachable = analyse(solved)
    return Score(
        name=name,
        built_with=mystery.built_with,
        cast=len(solved.characters),
        secrets=len(solved.secrets),
        valid=not broke,
        winnable=reachable.winnable,
        broke=sorted({v.rule for v in broke}),
        fired=sorted({a.check for a in critique(solved)}),
    )


# Thirty-seven drafts times up to twenty-four arrangements buried the first real
# report under six hundred lines of `solver.relocated_lie`. The silence now lives
# next to the thing making the noise (D-157); this name is kept because the tests
# and the docstring above both talk about it.
_quiet = quietly


def sweep(folder: Path, seed: int = 0) -> list[Score]:
    """Every draft in a folder, scored, in name order.

    A file that will not parse is reported rather than skipped. The corpus
    accumulates by accident, so it collects empty files and half-written ones,
    and silently dropping them is how a sweep quietly stops covering anything.
    """
    found: list[Score] = []
    for path in sorted(folder.glob("*.json")):
        try:
            mystery = Mystery.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as problem:  # noqa: BLE001 - a corpus is untidy by nature
            found.append(Score(name=path.stem[:8], unreadable=str(problem).split("\n")[0]))
            continue
        with _quiet():
            found.append(score(mystery, name=path.stem[:8], seed=seed))
    return found


def _footnote(skipped: int) -> str:
    if not skipped:
        return ""
    return (
        f", over the drafts with secrets ({skipped} older "
        f"{'draft has' if skipped == 1 else 'drafts have'} no secrets and "
        f"{'is' if skipped == 1 else 'are'} left out)"
    )


def _by_cohort(modern, counted, cohorts) -> list[str]:
    """One column per set of instructions, unstamped first and newest last.

    The stamp exists so that a change can be seen to have landed, and a pooled
    rate over two prompt versions cannot show that however loudly the header
    warns about it (D-175).
    """
    # "before the stamp" always leads, since everything predates everything.
    names = sorted(cohorts, key=lambda n: (n != "before the stamp", n))
    groups = {name: [s for s in modern if (s.built_with or "before the stamp") == name]
              for name in names}
    newest = names[-1]

    def label(name: str) -> str:
        return "pre-stamp" if name == "before the stamp" else name.split("/")[0]

    head = "  check " + "".join(f"{label(name):>17}" for name in names)
    rule = "  " + "-" * (len(head) - 2)
    sizes = "        " + "".join(f"{('n=' + str(len(groups[n]))):>17}" for n in names)

    def rate(name: str, check: str) -> str:
        here = groups[name]
        hits = sum(1 for s in here if check in s.fired)
        return f"{hits}/{len(here)}  {100 * hits / len(here):3.0f}%" if here else "-"

    rows = []
    for check in sorted(counted, key=lambda c: -sum(
        1 for s in groups[newest] if c in s.fired
    )):
        rows.append(f"  {check:<6}" + "".join(f"{rate(n, check):>17}" for n in names))

    return [
        "how often each advisory fires, by the instructions that made the draft:",
        "",
        head,
        sizes,
        rule,
        *rows,
        "",
        f"Sorted by the {newest} column, which is the one that answers whether "
        f"the last change landed.",
    ]


def report(scores: list[Score]) -> str:
    """The sweep as a page: a row per case, then how often each check fires.

    The base rates are the point. A single case tells you whether that case is
    good; the column tells you whether the check is.
    """
    usable = [s for s in scores if not s.unreadable]
    if not usable:
        return "Nothing to score."

    lines = [
        f"{len(usable)} drafts scored. No model called.",
        "",
        f"{'draft':<10}{'cast':>5}{'secrets':>9}{'valid':>7}{'winnable':>10}  what broke",
    ]
    for s in usable:
        lines.append(
            f"{s.name:<10}{s.cast:>5}{s.secrets:>9}{str(s.valid):>7}"
            f"{str(s.winnable):>10}  {', '.join(s.broke)}"
        )

    bad = [s for s in scores if s.unreadable]
    if bad:
        lines += ["", "would not parse:"]
        lines += [f"  {s.name}  {s.unreadable[:70]}" for s in bad]

    # A draft with no secrets predates the layer half these checks measure, and
    # counting it drags every base rate towards "everything is broken". The
    # corpus keeps them because they still exercise the solver; the statistics
    # leave them out and say so.
    modern = [s for s in usable if s.secrets]
    skipped = len(usable) - len(modern)

    # Which instructions made these (D-166). Every base rate in this report is a
    # rate for one set of prompts, and a corpus that mixes several says nothing
    # about any of them. Drafts from before the stamp existed show as unknown.
    cohorts = Counter(s.built_with or "before the stamp" for s in modern)

    counted: Counter[str] = Counter()
    for s in modern:
        counted.update(s.fired)

    lines += [
        "",
        f"valid after solving: {sum(1 for s in usable if s.valid)}/{len(usable)}    "
        f"winnable: {sum(1 for s in modern if s.winnable)}/{len(modern)} "
        f"(of the {len(modern)} with secrets)",
        "",
        "built by "
        + ", ".join(f"{name} x{n}" for name, n in cohorts.most_common()),
        "",
    ]

    # More than one set of instructions in the folder means the pooled rate
    # belongs to none of them, and saying so and then printing it anyway was
    # half a report (D-175). Split into a column per cohort, newest last,
    # because the question is always whether the last change moved anything.
    if len(cohorts) > 1:
        return "\n".join(lines + _by_cohort(modern, counted, cohorts))

    lines.append("how often each advisory fires" + _footnote(skipped) + ":")
    for check, hits in counted.most_common():
        share = hits / len(modern)
        note = "  <- fires on nearly everything, so it says nothing" if share >= 0.9 else ""
        lines.append(f"  {check:<5}{hits:>4}/{len(modern)}{100 * share:>6.0f}%{note}")
    return "\n".join(lines)
