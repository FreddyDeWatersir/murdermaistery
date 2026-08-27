# STATE

**NEXT:** Draft, in whatever rough form, the minimum a mystery must contain for
validator rule V1 to be checkable, and the rule itself as a single assertable
sentence. Then it becomes a failing pytest and we build up to green.

---

**Where things are, 27 August 2026**

- Repo live at github.com/FreddyDeWatersir/murdermaistery, scaffolded and pushed
- uv, pytest and ruff configured. `uv run pytest` green on a smoke test
- No domain code yet. `src/mystery/` is empty
- Two mysteries hand built, one played to a correct solution in 28 questions
- Core risk provisionally retired: the game is fun
- Twenty one decisions logged in `docs/decisions.md`

**The working loop**

1. Read this NEXT line
2. Agree what the unit is before writing anything
3. Federico drafts, pseudocode or English is fine
4. Claude returns working code plus what changed and why
5. Claude asks one question about it that reading the code does not answer
6. Commit, rewrite this NEXT line, log any decision

**Files**

- `STATE.md` — this, always current, always one concrete next action
- `docs/decisions.md` — every non-obvious choice, numbered, append only
- `docs/findings-playtest-01.md` — the playtest debrief and variety analysis
- `docs/prototypes/` — the paper prototype method and both hand built cases

**Open questions, in priority order**

1. Notebook versus solver: if the contradiction tracker flags everything
   automatically, what is left for the player to do. Gates the interface
2. Is variety structural or cosmetic, and what goes in the topology library
3. Ground truth schema in full, with hard requirements from findings F2, F3, F4, F9
4. Where game state lives between turns

**Errands, not gates**

- Blind replay of a third prototype, some evening. See D-020
