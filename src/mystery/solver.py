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
from mystery.models import Claim, Constraint, Mystery, PlaceId, SlotId

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
            "false_claim": _repair_the_lie(mystery, grid, placed),
        }
    )


def _repair_the_lie(mystery: Mystery, grid: Grid, placed: dict[str, Cell]) -> Claim | None:
    """Make sure the killer's story can actually be broken.

    A model asked to invent a lie will sometimes have the killer claim a room
    that was empty. Nobody can then contradict them, and the case is unsolvable
    however many questions the player asks. A real case had exactly this, with
    zero possible contradictors.

    Which room the killer *names* carries no story: it is not a scene, nothing
    happened there, and nobody's motive depends on it. So it is safe to move,
    unlike everything else in the timeline. Prefer a room with at least two
    people in it, all of whom are hiding something of their own, since a witness
    with nothing to hide settles the case in one question (D-039).
    """
    claim = mystery.false_claim
    if claim is None or mystery.killer is None:
        return None

    murder = _murder_cell(mystery, placed)
    slot = murder[1] if murder else claim.slot
    compromised = {s.holder for s in mystery.secrets}

    def witnesses(place: PlaceId) -> set[str]:
        return {
            person
            for person, by_slot in grid.items()
            if by_slot.get(slot) == place
            and person not in (mystery.killer, mystery.victim)
        }

    if len(witnesses(claim.place)) >= 2 and claim.place != (murder[0] if murder else None):
        return claim

    ranked = sorted(
        (p.id for p in mystery.places if p.id != (murder[0] if murder else None)),
        key=lambda place: (
            len(witnesses(place)) >= 2,
            all(w in compromised for w in witnesses(place)),
            len(witnesses(place)),
        ),
        reverse=True,
    )

    if not ranked or not witnesses(ranked[0]):
        return claim

    log.info(
        "solver.relocated_lie",
        was=claim.place,
        now=ranked[0],
        witnesses=len(witnesses(ranked[0])),
    )
    return claim.model_copy(update={"place": ranked[0], "slot": slot})


def _importance(constraint: Constraint, mystery: Mystery) -> tuple:
    """How hard we should fight to keep this constraint where the model put it.

    The murder never moves: everything else in the case is arranged around it.
    After that, exclusive scenes outrank open ones because privacy is what makes
    a moment matter, and bigger scenes outrank smaller ones because they are
    harder to reschedule.
    """
    is_murder = mystery.killer in constraint.people and mystery.victim in constraint.people
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
                    person, slot, place_ids, grid, live, rng, cell_of
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
) -> PlaceId:
    """Move someone out of a room they should not be in, as gently as possible.

    Preference: a room they were in an adjacent slot, so it reads as them not
    having moved rather than as teleportation; then any room no exclusive
    constraint has claimed; then anywhere.
    """
    forbidden = set()
    for constraint in bound:
        place, at = cell_of(constraint)
        if constraint.exclusive and at == slot and person not in constraint.people:
            forbidden.add(place)

    options = [p for p in place_ids if p not in forbidden]
    if not options:
        return rng.choice(place_ids)

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
    """Where and when the killer was alone with the victim."""
    if mystery.killer is None or mystery.victim is None:
        return None
    for constraint in mystery.constraints:
        if (
            constraint.id in placed
            and mystery.killer in constraint.people
            and mystery.victim in constraint.people
        ):
            return placed[constraint.id]
    return None


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

    # Never reschedule a scene involving the victim to after they are dead.
    murder = _murder_cell(mystery, placed)
    if murder is not None and mystery.victim in people:
        index = {s.id: s.index for s in mystery.slots}
        if index.get(slot, -1) > index.get(murder[1], -1):
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
            ] or place_ids

            if sticky and previous in options and rng.random() < STICKINESS:
                chosen = previous
            else:
                chosen = rng.choice(options)

            grid[character.id][slot.id] = chosen
            previous = chosen
