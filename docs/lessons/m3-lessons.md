# M3 lessons log

Loop-mode metrics and lessons for M3, recorded per part so each part's
time and cost can be compared on its own. Part B (#11) is the
calibration point against M2; Part A (#12) is extra scope found while
checking M2's code.

## Part A: network model (#12)

### Metrics

| Metric | Value |
| --- | --- |
| Started | Nov 2, 2026 (issue and branch `m3-network-model`) |
| Finished | <merge date> (PR #<n> → `<merge hash>`) |
| Elapsed working time | ~7 hr |
| Aider cost | $0.44 (architect plan $0.12, editor instructions $0.14, edits $0.18) |
| OpenRouter usage | start of M3 $5.7958 → at merge $<x> |
| Tests | 124 (M2) → 190 (66 new in `tests/test_model.py`) |
| pyright (standard mode) | 6 errors found after the code was committed, all fixed; M2 code had 0 |
| Mutations | 6 run; 4 caught at first, 1 gap (fixed), 1 equivalent |
| Review rework | plan review: 3 corrections folded into the spec before coding |

### Commits

| Commit | What |
| --- | --- |
| `fd31d72` | Spec committed as `docs/design/m3-policy.md` |
| `485f3a2` | `yamlio.py` move: the only `ipam.py` change (pure move, IDE refactoring, $0) |
| `bdc9e98` | Spec clarification from plan review (M-02 boolean check, error-merge order) |
| `588a571` | `model.py`, `policy.py` (Part A subset), `tests/test_model.py` |
| `a5e043c` | `model.py`: explicit `i is not None` filter in `_assemble` (Pylance) |
| `f269639` | `tests/test_model.py`: type-clean (pyright) |
| `71df955` | Tests pinning missing-key-first ordering (mutation M4) |

### Mutation check

Run with a script that applies one mutation, runs pytest, and restores
with `git restore`; the tree was confirmed clean after each run.

| # | Mutation | First run | After fix |
| --- | --- | --- | --- |
| M1 | M-02: `not isinstance(v, bool)` → `v not in (True, False)` | Caught by 3 tests (parametrized `1`/`0`, document-order test, property) | — |
| M2 | `public` not stripped before ipam | Caught (44 failures) | — |
| M3 | Within one tier: model errors before ipam errors | Caught by `test_same_tier_ipam_before_model` and the property | — |
| M4 | Missing-key (`config:`) errors always trail | **Survived** | Caught by 2 new tests (`71df955`) |
| M5 | Drop the `i is not None` filter | Survived: equivalent mutant (the earlier `pop` removes the only `None` key) | — |
| M6 | `vpn` not a reserved word | Caught by 6 tests | — |

M4 survived because every test with a missing top-level key had no
other error, so "leading" and "trailing" gave the same order. The two
new tests each pair a missing key with a later error (missing `vpc` +
bad tier `public`; missing `tiers` + bad `vpc.cidr`).

### Lessons

1. **Tests check only what you run.** Aider's `--test-cmd` ran pytest
   only. The code passed every test, and the type errors surfaced only
   in the editor (Pylance). Follow-up: pyright in the dev loop, CI and
   aider's `--lint-cmd`, before Part B.
2. **A type checker finds hidden dependencies that tests can't reach.**
   `_assemble` was correct only because of the order of two adjacent
   lines: a `pop` removed the `("tiers", None)` key before a `sorted()`
   that would crash on `None`. No input could reach the crash, so no
   test could catch it. Fixed by stating the guarantee where it's needed
   (`and i is not None`).
3. **Type errors in tests are often deliberate inputs.** Five pyright
   errors in `test_model.py` came from an intentionally non-string key
   and a value typed `object`. The fixes (build a new dict instead of
   mutating one; narrow with `isinstance`) made the tests clearer, and
   the `isinstance` asserts are real checks. `dict` is invariant in its
   key type, so widening the annotation alone doesn't work.
4. **Order rules need inputs where order can differ.** M4 survived
   because no test combined two errors whose relative order the rule
   decides. For every ordering rule, at least one test needs two errors
   that the rule puts in a definite order.
5. **Predictions miss tests you don't know about.** M3 was predicted to
   be caught by a test that doesn't actually check order within one
   tier; the test that caught it was another one. Reach → change →
   notice only works from the tests as written, so grep before
   predicting.
6. **Small mechanical slips cost time.** An unsaved edit (Auto Save is
   off) made a diff look unchanged; trailing whitespace got into a
   commit diff; a stray file named with a single space appeared in the
   repo; `pywright` was typed instead of `pyright`. That typo failed
   safely, but a near-miss package name can be a typosquat. Copy
   package names from official docs and check with `pip show`.
7. **Deterministic tools for mechanical work.** The `yamlio` move (IDE
   refactoring) and the mutation runs (a script with exact-match
   patterns that skips rather than guesses) cost $0 and were exact.
   Aider was used only where judgment was needed.

### Carry-overs

- File loading duplicated between `model.load_network` and
  `ipam.load_config`; dedupe after M3 (move `ConfigError` to its own
  module to avoid a circular import).
- pyright in the dev loop: issue #<n>, before Part B.
