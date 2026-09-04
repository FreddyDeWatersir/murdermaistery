"""Turn constraints into a timeline.

Two paths in, decided by whether the model handed us a grid.

**Repair.** The model proposed placements as part of writing the story, so most
cells are already motivated: this character is in the storeroom *because of the
affair*. Those reasons cannot be reconstructed from a constraint list, so the
proposal is kept and only the cells that break a constraint are moved. This is
minimal-conflict repair, and it is the path that matters (D-029).

**Build.** No grid arrived, so one is constructed from nothing by backtracking.
Correct, fast, and narratively dead, which is why STICKINESS exists here and
does not exist on the repair path: it is a crude stand-in for the motivation the
model would have supplied.

A constraint that cannot be satisfied either way is left unbound rather than
raising, so the failure arrives through rule V3 with the constraint named.
"""

import random

import structlog

from mystery.models import Constraint, FalseClaim, Mystery, PlaceId, SlotId, with_doors_both_ways

Grid = dict[str, dict[str, PlaceId]]
Cell = tuple[PlaceId, SlotId]

log = structlog.get_logger()

# How often a character with no constraint governing them stays where they were,
# on the build-from-nothing path. Without it the grid is valid and reads as a
# random walk. On the repair path the model supplies real reasons and this is
# not used.
STICKINESS = 0.75

# Repair passes. Evicting an intruder from one exclusive cell can push them into
# another, so it iterates. If it has not converged by now the constraint set is
# probably contradictory and the validator should say so rather than this
# looping forever.
MAX_REPAIR_PASSES = 8


def solve(mystery: Mystery, seed: int = 0) -> Mystery:
    """Return a copy of `mystery` with constraints bound and the grid complete.

    Deterministic for a given seed, which is what makes solver tests possible and
    what will let a daily puzzle be stored as an integer rather than a document.
    """
    rng = random.Random(seed)

    # Doors before anything else: the floor plan is not the solver's problem to
    # reason about, but it is a shape every later reader assumes is consistent,
    # and a one-sided door is a bookkeeping slip with one right answer (D-093).
    mystery = mystery.model_copy(
        update={"places": with_doors_both_ways(mystery.places)}
    )

    if mystery.placements:
        return _repair(mystery, rng)
    return _build(mystery, rng)


# --------------------------------------------------------------------------
# Repair: keep what the model proposed, move only what breaks
# --------------------------------------------------------------------------


def _repair(mystery: Mystery, rng: random.Random) -> Mystery:
    grid: Grid = {
        character.id: dict(mystery.placements.get(character.id, {}))
        for character in mystery.characters
    }

    # A scheduling clash is not a story problem. If two constraints both want the
    # same person at the same moment, both scenes are usually fine and one of
    # them simply has to happen at a different time. Unbind the less load-bearing
    # one and it gets a new slot below, rather than the whole mystery being
    # thrown away (D-022, D-033).
    keep, freed = _resolve_clashes(mystery)
    placed = {c.id: (c.place, c.slot) for c in keep}

    _settle(mystery, grid, keep, rng)
    _rehome(mystery, grid, placed, freed, rng)
    _settle(mystery, grid, [c for c in mystery.constraints if c.id in placed], rng, placed)
    _fill_holes(mystery, grid, placed, rng, sticky=False)
    _lay_the_body_to_rest(mystery, grid, placed)

    return mystery.model_copy(
        update={
            "placements": grid,
            "constraints": [_bind(c, placed.get(c.id)) for c in mystery.constraints],
            "false_claims": _repair_the_lies(mystery, grid, placed),
        }
    )


def _repair_the_lies(
    mystery: Mystery, grid: Grid, placed: dict[str, Cell]
) -> list[FalseClaim]:
    """Make sure every story in the case can actually be broken.

    A model asked to invent a lie will sometimes have somebody claim a room that
    was empty. Nobody can then contradict them, the lie never surfaces, and a
    red herring nobody can detect is not a red herring, it is a wasted
    character. A real case had exactly this on the killer, with zero possible
    contradictors.

    Which room a liar *names* carries no story: it is not a scene, nothing
    happened there, and nobody's motive depends on it. So it is safe to move,
    unlike everything else in the timeline.

    The killer's lie is held to a higher bar than the rest (D-063). Theirs wants
    two witnesses who are themselves compromised, because a witness with nothing
    to hide settles the case in one question (D-039). An innocent's lie only
    needs one person who can say they were not there, because the interesting
    work on an innocent lie is not detecting it, it is finding out what it was
    covering.
    """
    murder = _murder_cell(mystery, placed)

    def is_the_murder_cell(place: PlaceId, slot: SlotId) -> bool:
        """Only the room *and* the hour together are off limits.

        Claiming the vault at nine is claiming the murder scene. Claiming it at
        seven, before anyone died, is an ordinary alibi and a perfectly good
        thing for an innocent to lie about.
        """
        return murder is not None and (place, slot) == murder

    def witnesses(place: PlaceId, slot: SlotId, liar: str) -> set[str]:
        return {
            person
            for person, by_slot in grid.items()
            if by_slot.get(slot) == place and person not in (liar, mystery.victim)
        }

    def truth(liar: str, slot: SlotId) -> PlaceId | None:
        return grid.get(liar, {}).get(slot)

    compromised = {secret.holder for secret in mystery.secrets}
    repaired: list[FalseClaim] = []

    for claim in mystery.false_claims:
        is_killer = claim.character == mystery.killer
        # The killer lies about the murder itself. Everyone else lies about
        # whichever moment they were embarrassed by, and that stays where the
        # model put it.
        slot = murder[1] if (is_killer and murder) else claim.slot
        wanted = 2 if is_killer else 1

        here = witnesses(claim.place, slot, claim.character)
        already_good = (
            len(here) >= wanted
            and not is_the_murder_cell(claim.place, slot)
            and claim.place != truth(claim.character, slot)
        )
        if already_good:
            repaired.append(
                claim if slot == claim.slot else claim.model_copy(update={"slot": slot})
            )
            continue

        ranked = sorted(
            (
                place.id
                for place in mystery.places
                if not is_the_murder_cell(place.id, slot)
                and place.id != truth(claim.character, slot)
            ),
            key=lambda place: (
                len(witnesses(place, slot, claim.character)) >= wanted,
                all(w in compromised for w in witnesses(place, slot, claim.character)),
                len(witnesses(place, slot, claim.character)),
            ),
            reverse=True,
        )

        if not ranked:
            repaired.append(claim)
            continue

        # Nowhere in the house has anybody who could contradict them. Keep what
        # the model wrote if it is at least false, since an unbreakable lie is
        # an advisory problem and a lie that is not a lie is a V8 failure that
        # stops the whole run.
        nowhere_better = not witnesses(ranked[0], slot, claim.character)
        still_a_lie = claim.place != truth(claim.character, slot) and not is_the_murder_cell(
            claim.place, slot
        )
        if nowhere_better and still_a_lie:
            log.warning("solver.unbreakable_lie", liar=claim.character, place=claim.place)
            repaired.append(claim.model_copy(update={"slot": slot}))
            continue

        log.info(
            "solver.relocated_lie",
            liar=claim.character,
            was=claim.place,
            now=ranked[0],
            witnesses=len(witnesses(ranked[0], slot, claim.character)),
        )
        repaired.append(claim.model_copy(update={"place": ranked[0], "slot": slot}))

    return repaired


def _importance(constraint: Constraint, mystery: Mystery) -> tuple:
    """How hard we should fight to keep this constraint where the model put it.

    The murder never moves: everything else in the case is arranged around it.
    After that, exclusive scenes outrank open ones because privacy is what makes
    a moment matter, and bigger scenes outrank smaller ones because they are
    harder to reschedule.
    """
    scene = mystery.murder_scene
    is_murder = scene is not None and constraint.id == scene.id
    return (is_murder, constraint.exclusive, len(constraint.people), constraint.id)


def _resolve_clashes(mystery: Mystery) -> tuple[list[Constraint], list[Constraint]]:
    """Split bound constraints into the ones that keep their slot and the ones
    that have to be rescheduled."""
    ranked = sorted(
        (c for c in mystery.constraints if c.is_bound),
        key=lambda c: _importance(c, mystery),
        reverse=True,
    )

    keep: list[Constraint] = []
    freed: list[Constraint] = [c for c in mystery.constraints if not c.is_bound]
    claimed: dict[tuple[str, str], str] = {}

    for constraint in ranked:
        clash = any(
            claimed.get((person, constraint.slot), constraint.place) != constraint.place
            for person in constraint.people
        )
        if clash:
            freed.append(constraint)
            continue
        for person in constraint.people:
            claimed[(person, constraint.slot)] = constraint.place
        keep.append(constraint)

    return keep, freed


def _settle(
    mystery: Mystery,
    grid: Grid,
    bound: list[Constraint],
    rng: random.Random,
    placed: dict[str, Cell] | None = None,
) -> None:
    """Move only what breaks: put named people where their constraint says, then
    clear anyone else out of a room that is supposed to be private."""
    place_ids = [place.id for place in mystery.places]
    sealed = _sealed(mystery, placed or {c.id: (c.place, c.slot) for c in bound if c.is_bound})
    live = [c for c in bound if c.is_bound or (placed and c.id in placed)]

    def cell_of(constraint: Constraint) -> Cell:
        return placed[constraint.id] if placed and constraint.id in placed else (
            constraint.place,
            constraint.slot,
        )

    for _ in range(MAX_REPAIR_PASSES):
        moved = False

        for constraint in live:
            place, slot = cell_of(constraint)
            for person in constraint.people:
                if grid.setdefault(person, {}).get(slot) != place:
                    grid[person][slot] = place
                    moved = True

        for constraint in live:
            if not constraint.exclusive:
                continue
            place, slot = cell_of(constraint)
            for person in list(grid):
                if person in constraint.people or grid[person].get(slot) != place:
                    continue
                grid[person][slot] = _somewhere_else(
                    person, slot, place_ids, grid, live, rng, cell_of, sealed
                )
                moved = True

        if not moved:
            break


def _somewhere_else(
    person: str,
    slot: SlotId,
    place_ids: list[PlaceId],
    grid: Grid,
    bound: list[Constraint],
    rng: random.Random,
    cell_of,
    sealed=lambda place, slot: False,
) -> PlaceId:
    """Move someone out of a room they should not be in, as gently as possible.

    Preference: a room they were in an adjacent slot, so it reads as them not
    having moved rather than as teleportation; then any room no exclusive
    constraint has claimed; then anywhere.
    """
    forbidden = {p for p in place_ids if sealed(p, slot)}
    for constraint in bound:
        place, at = cell_of(constraint)
        if constraint.exclusive and at == slot and person not in constraint.people:
            forbidden.add(place)

    options = [p for p in place_ids if p not in forbidden]
    if not options:
        # Even with nowhere legal to stand, not on top of the body.
        loose = [p for p in place_ids if not sealed(p, slot)]
        return rng.choice(loose or place_ids)

    neighbours = [p for p in grid.get(person, {}).values() if p in options]
    return rng.choice(neighbours) if neighbours else rng.choice(options)


def _rehome(
    mystery: Mystery,
    grid: Grid,
    placed: dict[str, Cell],
    freed: list[Constraint],
    rng: random.Random,
) -> None:
    """Find a new place and time for each constraint that lost its slot.

    Unlike the first pass this is allowed to move people, because a constraint
    with nowhere to go is a scene deleted from the story, and a character
    standing in a slightly different room is not.
    """
    cells = [(place.id, slot.id) for place in mystery.places for slot in mystery.slots]
    rng.shuffle(cells)

    for constraint in sorted(freed, key=lambda c: _importance(c, mystery), reverse=True):
        for place, slot in cells:
            if _room_for(constraint, place, slot, mystery, placed):
                for person in constraint.people:
                    grid.setdefault(person, {})[slot] = place
                placed[constraint.id] = (place, slot)
                break


def _murder_cell(mystery: Mystery, placed: dict[str, Cell]) -> Cell | None:
    """Where and when the killing happens, as the model defines it (D-071)."""
    scene = mystery.murder_scene
    return placed.get(scene.id) if scene is not None else None


def _lay_the_body_to_rest(
    mystery: Mystery, grid: Grid, placed: dict[str, Cell]
) -> None:
    """The victim does not go anywhere after being killed.

    Both the model and the rescheduler will happily walk a corpse to the next
    scene, so this is enforced rather than hoped for (V7).
    """
    cell = _murder_cell(mystery, placed)
    if cell is None:
        return

    place, slot = cell
    index = {s.id: s.index for s in mystery.slots}
    after = index.get(slot)
    if after is None:
        return

    for s in mystery.slots:
        if s.index > after:
            grid.setdefault(mystery.victim, {})[s.id] = place


def _sealed(mystery: Mystery, placed: dict[str, Cell]):
    """Is this room closed to the living at this hour? (D-147)

    Once the killing has happened, the murder room has a body in it. The
    discovery says nobody found that body until after the evening, so nobody can
    be standing in there, and V10 rejects a case where anybody is.

    That rule was being checked and never enforced. The model's own grid is
    validated before the solver runs, so a draft that got this right still came
    out broken: `_fill_holes` puts every character with a gap in their evening
    into a room chosen at random, `_somewhere_else` clears people out of private
    scenes into a room chosen at random, and neither of them knew that one room
    was full. Two real drafts died this way in one evening, at about forty cents
    each, and the advice printed was "try another seed", which is the program
    telling a person to pay again for its own bug.

    The victim is exempt, and has to be: V7 requires them to stay exactly where
    they fell.
    """
    cell = _murder_cell(mystery, placed)
    if cell is None:
        return lambda place, slot: False

    room, when = cell
    index = {s.id: s.index for s in mystery.slots}
    after = index.get(when)
    if after is None:
        return lambda place, slot: False

    def sealed(place: PlaceId, slot: SlotId) -> bool:
        return place == room and index.get(slot, -1) > after

    return sealed


def _room_for(
    constraint: Constraint,
    place: PlaceId,
    slot: SlotId,
    mystery: Mystery,
    placed: dict[str, Cell],
) -> bool:
    """Could this constraint be rescheduled into this cell without disturbing
    anything already settled?"""
    people = set(constraint.people)

    # Never reschedule a scene involving the victim to after they are dead, and
    # never reschedule any scene at all into the room the body is lying in
    # (D-147). The second half used to be missing, so a perfectly good scene
    # could be moved on top of the corpse.
    murder = _murder_cell(mystery, placed)
    if murder is not None:
        index = {s.id: s.index for s in mystery.slots}
        later = index.get(slot, -1) > index.get(murder[1], -1)
        if later and (mystery.victim in people or place == murder[0]):
            return False

    for other in mystery.constraints:
        if other.id not in placed:
            continue
        other_place, other_slot = placed[other.id]
        if other_slot != slot:
            continue
        # Nobody may be needed in two rooms at once, which is the clash we are
        # here to avoid recreating.
        if other_place != place and people & set(other.people):
            return False
        # A private room stays private, in both directions.
        if other_place == place and (
            (other.exclusive and not people <= set(other.people))
            or (constraint.exclusive and not set(other.people) <= people)
        ):
            return False

    return True


# --------------------------------------------------------------------------
# Build: no proposal, construct from nothing
# --------------------------------------------------------------------------


def _build(mystery: Mystery, rng: random.Random) -> Mystery:
    cells = [(place.id, slot.id) for place in mystery.places for slot in mystery.slots]
    rng.shuffle(cells)

    # Hardest first. A constraint over four people has far fewer legal cells than
    # one over a single person, so placing it early means backtracking finds dead
    # ends near the root instead of at the leaves.
    ordered = sorted(
        mystery.constraints, key=lambda c: (-len(c.people), not c.exclusive, c.id)
    )

    grid: Grid = {character.id: {} for character in mystery.characters}
    assignments: list[tuple[Constraint, Cell, list[str]]] = []

    if not _search(ordered, cells, grid, assignments):
        grid = {character.id: {} for character in mystery.characters}
        assignments = []
        for constraint in ordered:
            for cell in cells:
                if _legal(constraint, cell, grid, assignments):
                    _assign(constraint, cell, grid, assignments)
                    break

    placed = {c.id: cell for c, cell, _ in assignments}
    _fill_holes(mystery, grid, placed, rng, sticky=True)

    return mystery.model_copy(
        update={
            "placements": grid,
            "constraints": [_bind(c, placed.get(c.id)) for c in mystery.constraints],
        }
    )


def _legal(
    constraint: Constraint,
    cell: Cell,
    grid: Grid,
    assignments: list[tuple[Constraint, Cell, list[str]]],
) -> bool:
    place, slot = cell

    if constraint.is_bound and (constraint.place, constraint.slot) != cell:
        return False

    for person in constraint.people:
        existing = grid.get(person, {}).get(slot)
        if existing is not None and existing != place:
            return False

    people = set(constraint.people)

    if constraint.exclusive:
        present = {p for p, by_slot in grid.items() if by_slot.get(slot) == place}
        if not present <= people:
            return False

    for other, other_cell, _ in assignments:
        if other_cell == cell and other.exclusive and not people <= set(other.people):
            return False

    return True


def _search(
    remaining: list[Constraint],
    cells: list[Cell],
    grid: Grid,
    assignments: list[tuple[Constraint, Cell, list[str]]],
) -> bool:
    if not remaining:
        return True

    constraint, rest = remaining[0], remaining[1:]

    for cell in cells:
        if not _legal(constraint, cell, grid, assignments):
            continue
        _assign(constraint, cell, grid, assignments)
        if _search(rest, cells, grid, assignments):
            return True
        _undo(grid, assignments)

    return False


def _assign(
    constraint: Constraint,
    cell: Cell,
    grid: Grid,
    assignments: list[tuple[Constraint, Cell, list[str]]],
) -> None:
    place, slot = cell
    moved = [
        person
        for person in constraint.people
        if grid.setdefault(person, {}).get(slot) is None
    ]
    for person in moved:
        grid[person][slot] = place
    assignments.append((constraint, cell, moved))


def _undo(grid: Grid, assignments: list[tuple[Constraint, Cell, list[str]]]) -> None:
    _, cell, moved = assignments.pop()
    _, slot = cell
    for person in moved:
        grid[person].pop(slot, None)


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


def _bind(constraint: Constraint, cell: Cell | None) -> Constraint:
    if cell is None:
        return constraint.model_copy(update={"place": None, "slot": None})
    place, slot = cell
    return constraint.model_copy(update={"place": place, "slot": slot})


def _fill_holes(
    mystery: Mystery,
    grid: Grid,
    placed: dict[str, Cell],
    rng: random.Random,
    *,
    sticky: bool,
) -> None:
    """Everyone has to be somewhere in every slot.

    On the build path this applies inertia, because nothing else gives a
    character a reason to stand still. On the repair path the model already
    supplied reasons and holes are rare, so filling is plain.
    """
    closed: dict[Cell, set[str]] = {
        placed[c.id]: set(c.people)
        for c in mystery.constraints
        if c.exclusive and c.id in placed
    }
    place_ids = [place.id for place in mystery.places]
    sealed = _sealed(mystery, placed)

    for character in mystery.characters:
        previous: str | None = None

        for slot in sorted(mystery.slots, key=lambda s: s.index):
            already = grid.setdefault(character.id, {}).get(slot.id)
            if already is not None:
                previous = already
                continue

            options = [
                place
                for place in place_ids
                if character.id in closed.get((place, slot.id), {character.id})
                and not (character.id != mystery.victim and sealed(place, slot.id))
            ] or [p for p in place_ids if not sealed(p, slot.id)] or place_ids

            if sticky and previous in options and rng.random() < STICKINESS:
                chosen = previous
            else:
                chosen = rng.choice(options)

            grid[character.id][slot.id] = chosen
            previous = chosen

# How many arrangements to try before giving up on a draft (D-147).
SOLVER_TRIES = 24


def solve_until_valid(
    mystery: Mystery, seed: int = 0, tries: int = SOLVER_TRIES
) -> tuple[Mystery, int, list]:
    """Solve, and if the result does not hold, solve it again differently.

    The two halves of making a case cost wildly different amounts. Drafting is a
    call to the strongest model and about forty cents; solving is arithmetic and
    free. So a draft that survives the proposed rules and then fails the final
    ones should never cost another draft: the arrangement is what failed, and
    there are more arrangements.

    Deterministic. Seeds are tried in order from the one asked for, so the same
    command produces the same case, and the seed that worked is returned so it
    can be said out loud.

    Returns the solved mystery, the seed that produced it, and the violations of
    the last attempt, which are empty exactly when it worked.
    """
    from mystery.validator import validate

    worst: list = []
    for offset in range(max(1, tries)):
        solved = solve(mystery, seed=seed + offset)
        result = validate(solved)
        if result.ok:
            if offset:
                log.info("solver.reseated", tried=offset + 1, seed=seed + offset)
            return solved, seed + offset, []
        worst = result.violations

    return solve(mystery, seed=seed), seed, worst

