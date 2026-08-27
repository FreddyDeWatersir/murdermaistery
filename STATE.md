# STATE

**NEXT:** The language model. One call that takes a seed (setting, cast size,
solution topology) and returns a cast plus a set of unbound constraints, parsed
into the Pydantic models. Feed it straight into `solve()` and then `validate()`.
That completes the spine end to end.

---

**Where things are, 27 August 2026**

- Repo: github.com/FreddyDeWatersir/murdermaistery
- `src/mystery/models.py` — Mystery, Character, Place, Slot, Constraint
- `src/mystery/validator.py` — V1, V2, V3
- `src/mystery/solver.py` — backtracking constraint placement, seeded and
  reproducible, with movement inertia so grids read like people rather than
  random walks
- Seventeen tests green, ruff clean
- Architecture note: https://claude.ai/code/artifact/537fe482-a219-4b13-a108-062bff885a1f
- Twenty four decisions in `docs/decisions.md`

**The four layers, and how much of each exists**

| Layer | What it does | State |
|---|---|---|
| Generation | model writes constraints, solver binds them, knowledge is derived | solver and validator done, model next, derivation after |
| Play | agents answer in character, claims logged, contradictions tracked | nothing |
| Resolution | accusation, reveal, clue post mortem | nothing |
| Delivery | terminal, then web, then Lambda and CI | nothing |

**The working loop**

1. Read this NEXT line
2. Agree what the unit is before writing anything
3. Claude writes the code, runs it, and reports what changed and why
4. Claude asks one question that reading the code does not answer
5. Commit, rewrite this NEXT line, log any decision

**Validator rules**

| Rule | What | Guards | Status |
|---|---|---|---|
| V0 | No holes in the grid | hand-edited files, at the parse boundary | unwritten |
| V1 | Bound constraints agree with the timeline | the solver | live |
| V2 | Exclusive constraints are private | the solver | live |
| V3 | Every constraint was placed | the solver | live |

**Constraint vocabulary**

- Live: co-location, exclusivity. `Alone` needed no new type, it is
  `people=[x], exclusive=True` (D-024)
- Next: `Overheard`, an exclusive exchange plus a fixed number of named witnesses
- Later: `Sees` (adjacency and paths, not co-location), `Sustains`, `Apart`

**Open questions, in priority order**

1. Notebook versus solver: if the contradiction tracker flags everything
   automatically, what is left for the player to do. Gates the interface
2. What goes in the topology library, since variety is structural not cosmetic
3. Where game state lives between turns

**Errands, not gates**

- V0 and moving fixtures to JSON. Hygiene, parked behind the spine
- Blind replay of a third prototype, some evening. See D-020
