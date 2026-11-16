# Sample central repo (fixture)

A generic product used by the W1 tests: `profile/`, `docs/`, one story per state, the `FIX-1` walk and planted violations.

- `docs/stories/F-100/S-101` to `S-114`: one story at every state, with the artefacts that state needs.
- `docs/stories/F-100/FIX-1.md`: starts at Ready. `walk/FIX-1/` holds what each step of the walk adds.
- `docs/stories/F-100/S-199.md`: planted violation, about to be moved to In Review with no archunit.txt.
- `planted/violations.json`: each violation as the tool call an agent would make, with the hook that must refuse it.

Nothing here is real. `tools/baton/tests/W1/test_fixture_walk.py` drives it.
