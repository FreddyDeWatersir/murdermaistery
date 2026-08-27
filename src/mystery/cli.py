"""Run the pipeline end to end and look at what came out.

    uv run python -m mystery.cli --setting "a gallery private view"

Looking at output is not optional. The solver's first grid passed every test and
was unreadable nonsense, and nothing in the suite noticed. A validator tells you
a mystery is not broken; only your eyes tell you it is any good.
"""

import argparse
import sys
from pathlib import Path

from mystery.critique import critique
from mystery.generator import (
    GenerationFailed,
    GenerationRequest,
    anthropic_drafter,
    generate,
)
from mystery.knowledge import analyse_alibi, derive
from mystery.models import Mystery
from mystery.solver import solve
from mystery.validator import validate

CACHE = Path("var/mysteries")


def render(mystery: Mystery) -> str:
    """The movement grid, characters down the side and time across the top."""
    slots = sorted(mystery.slots, key=lambda s: s.index)
    names = {place.id: place.name for place in mystery.places}
    width = max([len(n) for n in names.values()] + [len(s.label) for s in slots]) + 2
    label_width = max(len(c.name) for c in mystery.characters) + 2

    header = " " * label_width + "".join(s.label.ljust(width) for s in slots)
    rows = [
        character.name.ljust(label_width)
        + "".join(
            names.get(mystery.placements.get(character.id, {}).get(slot.id, ""), "?")
            .ljust(width)
            for slot in slots
        )
        for character in mystery.characters
    ]
    return "\n".join([header, *rows])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate, solve and check one mystery.")
    parser.add_argument("--setting", default="a private view at a small art gallery")
    parser.add_argument("--cast", type=int, default=5)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--places", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore var/mysteries and call the model"
    )
    parser.add_argument(
        "--play", action="store_true", help="interrogate the suspects in the terminal"
    )
    parser.add_argument(
        "--show-leaks",
        action="store_true",
        help="while playing, report when an agent cites something it does not know",
    )
    args = parser.parse_args(argv)

    request = GenerationRequest(
        setting=args.setting,
        cast_size=args.cast,
        slot_count=args.slots,
        place_count=args.places,
        seed=args.seed,
    )

    try:
        draft = generate(
            request,
            drafter=anthropic_drafter(),
            cache_dir=None if args.no_cache else CACHE,
        )
    except GenerationFailed as failure:
        print(failure)
        return 1

    solved = solve(draft, seed=args.seed)

    print(f"\n{solved.title}\n")
    print(render(solved))
    print("\nConstraints")
    for constraint in solved.constraints:
        where = f"{constraint.place}, {constraint.slot}" if constraint.is_bound else "UNPLACED"
        exclusive = " (alone)" if constraint.exclusive else ""
        print(f"  {constraint.id:28} {where}{exclusive}")
        if constraint.description:
            print(f"  {'':28} {constraint.description}")

    print("\nCast")
    for character in solved.characters:
        tag = " (victim)" if character.id == solved.victim else ""
        print(f"  {character.name}{tag}")
        if character.wants:
            print(f"      wants: {character.wants}")
        if character.manner:
            print(f"      manner: {character.manner}")
        if character.under_pressure:
            print(f"      pressed: {character.under_pressure}")

    if solved.secrets:
        print("\nSecrets")
        for secret in solved.secrets:
            gate = f"  (only after {secret.revealed_by})" if secret.revealed_by else ""
            about = f" about {secret.about}" if secret.about else ""
            motive = "  MOTIVE" if secret.is_motive else ""
            print(f"  {secret.id:22}{about}{gate}{motive}")
            print(f"  {'':22} held by {secret.holder}: {secret.summary}")
            if secret.breaks_when:
                print(f"  {'':22} breaks when: {secret.breaks_when}")

    if solved.false_claim:
        claim = solved.false_claim
        truth = solved.placements.get(claim.character, {}).get(claim.slot)
        print(
            f"\nThe lie\n  {claim.character} will say {claim.place} at {claim.slot}. "
            f"Actually {truth}"
        )

    if solved.false_claim:
        know = derive(solved)
        analysis = analyse_alibi(solved, know)
        names = {c.id: c.name for c in solved.characters}
        if not analysis.claim_holds:
            print("\nWho can break the lie")
            for person in analysis.contradictors:
                tag = "credible" if person in analysis.credible else "compromised"
                print(f"  {names.get(person, person):20} ({tag})")
            if not analysis.contradictors:
                print("  nobody")

    result = validate(solved)

    if args.play:
        if not result.ok:
            print("\nThis mystery is broken and not worth playing:")
            for violation in result.violations:
                print(f"  [{violation.rule}] {violation.message}")
            return 1
        from mystery.agent import anthropic_responder
        from mystery.play import run

        run(solved, anthropic_responder(), show_leaks=args.show_leaks)
        return 0

    print("\nValid." if result.ok else "\nNot valid:")
    for violation in result.violations:
        print(f"  [{violation.rule}] {violation.message}")

    # Advisories on a broken mystery are noise: fix correctness first.
    advisories = critique(solved) if result.ok else []
    if advisories:
        print("\nValid, but:")
        for advisory in advisories:
            print(f"  [{advisory.check}] {advisory.message}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
