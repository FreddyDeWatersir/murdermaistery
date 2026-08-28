"""Run the pipeline end to end and look at what came out.

    uv run python -m mystery.cli --setting "a gallery private view"

Looking at output is not optional. The solver's first grid passed every test and
was unreadable nonsense, and nothing in the suite noticed. A validator tells you
a mystery is not broken; only your eyes tell you it is any good.
"""

import argparse
import sys
from pathlib import Path

from mystery.topology import DEFAULT as DEFAULT_TOPOLOGY
from mystery.daily import BUFFER, shortfall, todays_case, waiting
from mystery.example import OPENING_NIGHT
from mystery.palette import draw as draw_palette
from mystery.library import ART
from mystery.library import LIBRARY as LIBRARY_DIR
from mystery.library import catalogue
from mystery.library import entries as saved_cases
from mystery.library import load as load_case
from mystery.library import save as save_case
from mystery.solvable import report
from mystery.topology import LIBRARY, assess
from mystery.topology import catalogue as topologies
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


# Attempts per case before giving up for the night. A failure that a complaint
# can fix is worth retrying; a systematic one is not, and unbounded retry against
# a paid API with nobody awake is how a bad night becomes a bad bill (D-078).
ATTEMPTS = 3


def _fill(args, want: int) -> int:
    """The nightly job. Generate until the buffer is full or something is wrong.

    Note what it does *not* do: decide which case is today's. That is drawn from
    the buffer when somebody asks for it, so a night where this fails entirely
    costs a shorter queue rather than a missing game.
    """
    from mystery.solvable import analyse

    needed = shortfall(want=want)
    if not needed:
        print(f"  Buffer is full: {len(waiting())} cases waiting. Nothing to do.")
        return 0

    print(f"  {len(waiting())} waiting, want {want}. Generating {needed}.")
    made = 0

    for n in range(needed):
        for attempt in range(ATTEMPTS):
            seed = args.seed + n * ATTEMPTS + attempt
            request = GenerationRequest(
                setting=args.setting,
                cast_size=args.cast,
                slot_count=args.slots,
                place_count=args.places,
                topology=args.topology,
                seed=seed,
            )
            try:
                draft = generate(request, drafter=anthropic_drafter(), cache_dir=CACHE)
            except GenerationFailed as failure:
                print(f"  seed {seed}: {failure}")
                continue
            except Exception as error:  # noqa: BLE001
                # Nothing a complaint can fix: no key, no network, no service.
                # Retrying costs money and changes nothing.
                print(f"  Stopping: {error}")
                return 1

            solved = solve(draft, seed=seed)
            result = validate(solved)
            if not result.ok:
                print(f"  seed {seed}: invalid, {[v.rule for v in result.violations]}")
                continue
            if not analyse(solved).winnable:
                print(f"  seed {seed}: valid but not winnable")
                continue

            kept = save_case(solved, args.setting, args.topology, seed)
            print(f"  {kept.id}")
            made += 1
            break
        else:
            print(f"  Gave up after {ATTEMPTS} attempts. {made} made, buffer short.")
            return 1

    print(f"  {made} added. {len(waiting())} waiting.")
    return 0


def _bundle(case_id: str) -> int:
    """One case, its art, and nothing else, in a file you can email.

    The shelf and the art are both under `var/`, which is gitignored on purpose:
    the pictures are megabytes and the cases are personal. That is right for a
    repository and useless for moving one good case to a laptop, which is what
    this is for (D-083).
    """
    import zipfile

    case = load_case(case_id)
    art = ART / case.id
    out = Path(f"{case.id}.zip")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as bundle:
        source = next(LIBRARY_DIR.glob(f"*__{case.id}.json"), None) or (
            LIBRARY_DIR / f"{case.id}.json"
        )
        bundle.write(source, f"cases/{source.name}")

        pictures = sorted(art.rglob("*.png")) if art.exists() else []
        for picture in pictures:
            bundle.write(picture, f"art/{picture.relative_to(art)}")

    size = out.stat().st_size / 1_000_000
    print(f"  {out}  ({len(pictures)} pictures, {size:.1f} MB)")
    print(f"  On the other machine: uv run python -m mystery.cli --unbundle {out}")
    return 0


def _unbundle(path: Path) -> int:
    import zipfile

    if not path.exists():
        print(f"  No such bundle: {path}")
        return 1

    with zipfile.ZipFile(path) as bundle:
        names = bundle.namelist()
        case_files = [n for n in names if n.startswith("cases/") and n.endswith(".json")]
        if not case_files:
            print("  That zip has no case in it.")
            return 1

        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        for name in case_files:
            (LIBRARY_DIR / Path(name).name).write_bytes(bundle.read(name))

        case_id = Path(case_files[0]).stem.split("__", 1)[-1]
        pictures = [n for n in names if n.startswith("art/") and n.endswith(".png")]
        for name in pictures:
            target = ART / case_id / Path(name).relative_to("art")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(name))

    print(f"  {case_id} is on the shelf, with {len(pictures)} pictures.")
    print(f"  Play it: uv run python -m mystery.web --case {case_id}")
    return 0


def _casts() -> str:
    """Every saved cast, one line each, for reading three cases side by side.

    The thing being looked for is not whether one cast is good. It is whether
    the third one is made of different people from the first (D-075), and that
    only shows up when they are next to each other.
    """
    blocks = []
    for case in saved_cases():
        people = [
            f"    {c.name:<22} {c.gender or '?':<6} {c.role or '(no role given)'}\n"
            f"    {'':<22} {'':<6} {c.manner or '(no manner given)'}"
            for c in case.mystery.characters
        ]
        blocks.append(f"  {case.id}  ({case.topology or 'the_lie'})\n" + "\n".join(people))
    return "\n\n".join(blocks) or "  Nothing saved yet."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate, solve and check one mystery.")
    parser.add_argument("--setting", default="a private view at a small art gallery")
    parser.add_argument("--cast", type=int, default=5)
    parser.add_argument("--slots", type=int, default=5)
    parser.add_argument("--places", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--topology",
        default=DEFAULT_TOPOLOGY,
        choices=sorted(LIBRARY),
        help="the shape of the solution. Run --topologies to see what each one means",
    )
    parser.add_argument(
        "--topologies", action="store_true", help="list the shapes a case can have and stop"
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="ignore var/mysteries and call the model"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the whole pipeline on the case shipped with the code. No key, no "
        "network, no spend. This is how you check the machinery still works",
    )
    parser.add_argument(
        "--case", help="look at a case you already have, by name. Calls no model"
    )
    parser.add_argument(
        "--cases", action="store_true", help="list the cases on the shelf and stop"
    )
    parser.add_argument(
        "--casts",
        action="store_true",
        help="print the cast of every saved case together, for reading three of "
        "them side by side. Calls no model",
    )
    parser.add_argument(
        "--fill",
        nargs="?",
        type=int,
        const=BUFFER,
        metavar="N",
        help="top the buffer up to N unplayed cases and stop. This is the nightly "
        "job: it does not make today's case, it makes sure there is always one "
        "ready. Bounded attempts, and it stops on the first error it cannot fix",
    )
    parser.add_argument(
        "--today",
        action="store_true",
        help="which case is today's, and how many are waiting behind it",
    )
    parser.add_argument(
        "--bundle",
        metavar="CASE",
        help="pack a case and its pictures into one zip you can carry to another "
        "machine. Nothing in it is machine-specific",
    )
    parser.add_argument(
        "--unbundle",
        metavar="FILE",
        help="unpack a bundle onto this machine's shelf, art included",
    )
    parser.add_argument(
        "--material",
        type=int,
        metavar="N",
        help="show the manners, motive and threads the next N seeds would be "
        "dealt, and stop. Free, and the fastest way to see whether variety is "
        "actually varying",
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

    if args.topologies:
        print(topologies())
        return 0

    if args.cases:
        print(catalogue())
        return 0

    if args.casts:
        print(_casts())
        return 0

    if args.bundle:
        return _bundle(args.bundle)

    if args.unbundle:
        return _unbundle(Path(args.unbundle))

    if args.today:
        case = todays_case()
        queue = waiting()
        print(f"  Today:   {case.id if case else 'NOTHING. Run --fill'}")
        print(f"  Waiting: {len(queue)} ({', '.join(c.id for c in queue) or 'none'})")
        return 0

    if args.fill:
        return _fill(args, args.fill)

    if args.material:
        for seed in range(args.seed, args.seed + args.material):
            print(f"\n=== seed {seed} " + "=" * 52)
            print(draw_palette(seed, args.setting, args.topology, args.cast).brief())
        return 0

    request = GenerationRequest(
        setting=args.setting,
        cast_size=args.cast,
        slot_count=args.slots,
        place_count=args.places,
        topology=args.topology,
        seed=args.seed,
    )

    if args.case:
        saved = load_case(args.case)
        solved = saved.mystery
        print(f"\n{solved.title}\n")
        print(render(solved))
        print("\n" + report(solved))
        for advisory in assess(solved, saved.topology or args.topology):
            print(f"  [{advisory.check}] {advisory.message}")
        return 0

    # The dry run swaps the model for a case that is already in the repo. Every
    # other stage is the real one, parse boundary included (D-070).
    drafter = (
        (lambda request, complaints: OPENING_NIGHT) if args.dry_run else anthropic_drafter()
    )

    try:
        draft = generate(
            request,
            drafter=drafter,
            cache_dir=None if (args.no_cache or args.dry_run) else CACHE,
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

    if result.ok:
        kept = save_case(solved, args.setting, args.topology, args.seed)
        print(f"\nSaved as {kept.id}. Come back with --case {kept.id}")
        print("\n" + report(solved))

    # Advisories on a broken mystery are noise: fix correctness first.
    advisories = assess(solved, args.topology) if result.ok else []
    if advisories:
        print("\nValid, but:")
        for advisory in advisories:
            print(f"  [{advisory.check}] {advisory.message}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
