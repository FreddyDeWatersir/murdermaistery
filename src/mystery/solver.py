"""Bind constraints to places and slots, then fill in the rest of the timeline.

The language model says what must be true. This decides where and when so that
all of it can hold at once (D-022). No model is involved and none ever will be:
the whole point of the split is that this half is deterministic, cheap, and
cannot hallucinate.

The search is plain backtracking. With a handful of constraints over a five by
five grid the space is small enough that nothing cleverer is warranted, and
readability matters more here than speed.

A constraint this cannot place is left unbound rather than raising, so the
failure arrives through rule V3 with the constraint named. That is what makes it
possible to relax or regenerate one constraint instead of discarding the whole
mystery.
"""

import random
from dataclasses import dataclass

from mystery.models import Constraint, Mystery, PlaceId, SlotId

Grid = dict[str, dict[str, PlaceId]]
Cell = tuple[PlaceId, SlotId]


@dataclass
class _Assignment:
    """A constraint sitting in a cell, and who it put there.

    `moved` records only the people this assignment actually placed, so undoing
    it cannot rip someone out of the grid who was already there for another
    reason.
    """

    constraint: Constraint
    cell: Cell
    moved: list[str]


def solve(mystery: Mystery, seed: int = 0) -> Mystery:
    """Return a copy of `mystery` with constraints bound and the grid filled.

    Deterministic for a given seed. That is what makes solver tests possible,
    and what will eventually let a daily puzzle be reproduced from its seed
    alone rather than stored.
    """
    rng = random.Random(seed)

    cells = [(place.id, slot.id) for place in mystery.places for slot in mystery.slots]
    rng.shuffle(cells)

    # Hardest first. A constraint over four people has far fewer legal cells
    # than one over a single person, so placing it early means backtracking
    # finds dead ends near the root instead of at the leaves.
    ordered = sorted(
        mystery.constraints,
        key=lambda c: (-len(c.people), not c.exclusive, c.id),
    )

    grid: Grid = {character.id: {} for character in mystery.characters}
    assignments: list[_Assignment] = []

    if not _place_all(ordered, cells, grid, assignments):
        grid = {character.id: {} for character in mystery.characters}
        assignments = []
        _place_greedily(ordered, cells, grid, assignments)

    _fill_free_cells(mystery, grid, assignments, rng)

    bound = {a.constraint.id: a.cell for a in assignments}
    return mystery.model_copy(
        update={
            "placements": grid,
            "constraints": [_bind(c, bound.get(c.id)) for c in mystery.constraints],
        }
    )


def _bind(constraint: Constraint, cell: Cell | None) -> Constraint:
    if cell is None:
        return constraint.model_copy(update={"place": None, "slot": None})
    place, slot = cell
    return constraint.model_copy(update={"place": place, "slot": slot})


def _legal(
    constraint: Constraint, cell: Cell, grid: Grid, assignments: list[_Assignment]
) -> bool:
    """Can this constraint occupy this cell, given everything placed so far?"""
    place, slot = cell

    # A constraint that arrived already bound is not ours to move.
    if constraint.is_bound and (constraint.place, constraint.slot) != cell:
        return False

    # Nobody it names may already be somewhere else in this slot.
    for person in constraint.people:
        existing = grid.get(person, {}).get(slot)
        if existing is not None and existing != place:
            return False

    people = set(constraint.people)

    # An exclusive constraint needs the cell to itself.
    if constraint.exclusive:
        present = {p for p, by_slot in grid.items() if by_slot.get(slot) == place}
        if not present <= people:
            return False

    # And nobody may walk into a cell another exclusive constraint owns.
    for other in assignments:
        if (
            other.cell == cell
            and other.constraint.exclusive
            and not people <= set(other.constraint.people)
        ):
            return False

    return True


def _place_all(
    remaining: list[Constraint],
    cells: list[Cell],
    grid: Grid,
    assignments: list[_Assignment],
) -> bool:
    """Depth-first search over constraints. True once every one has a cell."""
    if not remaining:
        return True

    constraint, rest = remaining[0], remaining[1:]

    for cell in cells:
        if not _legal(constraint, cell, grid, assignments):
            continue

        _assign(constraint, cell, grid, assignments)
        if _place_all(rest, cells, grid, assignments):
            return True
        _undo(grid, assignments)

    return False


def _place_greedily(
    ordered: list[Constraint],
    cells: list[Cell],
    grid: Grid,
    assignments: list[_Assignment],
) -> None:
    """Fallback for a constraint set that is unsatisfiable as a whole.

    Take whatever fits, hardest first, and leave the rest unbound so that V3
    reports them by name.
    """
    for constraint in ordered:
        for cell in cells:
            if _legal(constraint, cell, grid, assignments):
                _assign(constraint, cell, grid, assignments)
                break


def _assign(
    constraint: Constraint, cell: Cell, grid: Grid, assignments: list[_Assignment]
) -> None:
    place, slot = cell
    moved = []

    for person in constraint.people:
        if grid.setdefault(person, {}).get(slot) is None:
            grid[person][slot] = place
            moved.append(person)

    assignments.append(_Assignment(constraint=constraint, cell=cell, moved=moved))


def _undo(grid: Grid, assignments: list[_Assignment]) -> None:
    last = assignments.pop()
    _, slot = last.cell
    for person in last.moved:
        grid[person].pop(slot, None)


# How often an unconstrained character stays where they already were, rather
# than wandering. Without this the grid is valid and reads like nonsense:
# four rooms in four slots for no reason. People mostly stand still.
STICKINESS = 0.75


def _fill_free_cells(
    mystery: Mystery,
    grid: Grid,
    assignments: list[_Assignment],
    rng: random.Random,
) -> None:
    """Everyone has to be somewhere in every slot, including when no constraint
    cares where.

    Two rules. Free placement respects exclusivity, so a cell an exclusive
    constraint has claimed is closed to everyone outside it. And movement has
    inertia: a character with no reason to be anywhere in particular stays where
    they were, which is both what people do and what makes a timeline legible to
    a player reconstructing it.
    """
    closed: dict[Cell, set[str]] = {
        a.cell: set(a.constraint.people) for a in assignments if a.constraint.exclusive
    }

    place_ids = [place.id for place in mystery.places]
    in_order = sorted(mystery.slots, key=lambda s: s.index)

    for character in mystery.characters:
        previous: str | None = None

        for slot in in_order:
            already = grid.setdefault(character.id, {}).get(slot.id)
            if already is not None:
                previous = already
                continue

            options = [
                place
                for place in place_ids
                if character.id in closed.get((place, slot.id), {character.id})
            ] or place_ids

            if previous in options and rng.random() < STICKINESS:
                chosen = previous
            else:
                chosen = rng.choice(options)

            grid[character.id][slot.id] = chosen
            previous = chosen
