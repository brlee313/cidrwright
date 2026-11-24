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
| Finished | Nov 6, 2026 (PR #14 → `3c72a26`) |
| Elapsed working time | ~7 hr |
| Aider cost | $0.44 (architect plan $0.12, editor instructions $0.14, edits $0.18) |
| OpenRouter usage | start of M3 $5.7958 → at merge $6.6558 (Δ $0.86; $0.42 not explained by aider's logged cost) |
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
  module to avoid a circular import). (ConfigError mod Nov 16, commit hash: 1825689)
- pyright in the dev loop: issue #13, done Nov 12 (PR #15 → `37ee4ca`): pinned, configured for `.venv`, required CI check "Tests and types".


## Part B: policy compiler (#11)

### Metrics

| Metric | Value |
| --- | --- |
| Started | Nov 2, 2026 (issue); work began Nov 12, 14:21, after #13 merged |
| Finished | Nov 24, 2026 (PR #17 → merge commit) |
| Elapsed working time | ~16.6 hr + Nov 24 session (Nov 12 14:21–17:30; Nov 16 10:28–16:06; Nov 21 10:20–14:06; Nov 22 12:21–16:24; Nov 24 11:23–13:16 ) |
| Cost (OpenRouter, source of truth) | at Part B start $6.6558 → $11.6280 before merge (Δ $4.97). Aider's own log shows about half of that: aider 0.86.2 undercounts the 5.5 models (~0.5×); confirmed against OpenRouter's `/activity` (Nov 21) |
| Tests | 190 (end of Part A) → 409 (`test_policy.py`, `test_policy_props.py` with 7 properties, `test_model.py` updates) |
| pyright (standard mode) | 0 errors at every stage commit; 32 errors in test helpers fixed by hand in Stage 1 (`entry()` typed `object`) |
| Mutations | 5 run on `policy.py` (B–F); all 5 caught; 3 were covered by one test or by message wording only → 3 tests added |
| Review rework | aider plan raised 12 open points (A1–A12), settled in spec rev 5 before coding; hint/wording fixes after Stage 1; Stage 5 plan found 4 design gaps (all accepted); spec synced with the code at the end |

### Commits

| Commit | What |
| --- | --- |
| `2760079` | Lessons log: Part A merge metrics |
| `8778268` | ADR 0006 symbolic endpoints; amend-note rule; ADR 0003 pointer |
| `713bcc3` | ADR 0007 least-privilege egress |
| `1825689` | `ConfigError`, `describe` moved to `errors.py` (pure move) |
| `24d05f0` | Spec rev 5 (plan review A1–A12); `TierRef` in ADR 0006 |
| `cb509c7` | Stage 1: IR dataclasses, structural validation (P-02, P-10–P-23) |
| `9139e27` | Hints name a real public tier; self-pair wording for internet/vpn |
| `f6dad4c` | Stage 2: proto, ports, ICMP validation (P-30–P-45) |
| `f560157` | Stage 3: `compile_policy`, cross-entry checks (P-50, P-51) |
| `45929a6` | Stage 4: `Network.rules`, policy gating, golden spec test |
| `2006864` | Stage 5: Hypothesis properties P0–P6, valid by construction |
| `bbef45c` | Stage 6: tests for mutants C, D, E |
| `35e79c4` | Spec synced with Part B code |

### Mutation check

Each mutation was predicted first (reach → change → notice), then run
on a clean tree and undone with `git restore`. Mutants are found by
exact text, not line number.

| # | Mutation in `policy.py` | Kind | First run | After fix |
| --- | --- | --- | --- | --- |
| B | span cap `span > MAX_PORT_SPAN` → `>=` | too strict | Caught: 2 example cases (1024-port ranges) + P0 | — |
| C | overlap `a.start <= b.end` → `<` | too lax | Caught by **1** test (`P51-one-port`) | + `P51-one-port-via-list` |
| D | duplicate check (`r.match == o.match`) deleted | too lax for ICMP type + code; otherwise message only | Caught by 4 tests, **all on message wording**; the accepted duplicate had no test | + `P50-icmp-code` |
| E | all-codes cover check (`b.code is None`) deleted | too lax | Caught by **1** test (`P51-icmp-covered`) | + `P51-icmp-covered-via-list` |
| F | `proto` dropped from the conflict key | too strict | Caught by 14 tests (example, golden spec, all 7 properties) | — |

### Lessons

1. **Too-strict and too-lax bugs are caught by different tests.**
   Properties built from valid input catch a validator that rejects too
   much (B, F: caught many times over). They can never catch one that
   accepts too much, because valid input never contains the bad case.
   Only example tests with invalid input can (C, D, E: 0–1 behavior
   tests each before Stage 6).
2. **A killed mutant isn't automatically covered.** D failed 4 tests,
   but only because the error message changed. Its dangerous behavior
   (accepting the same ICMP type and code twice) had no test. Trace
   each behavior a mutant changes and check what catches each one.
3. **Write the expected answer before running.** In a "second item in
   the list" test, the first draft put the clash on the first item. The
   expected message, written beforehand, disagreed with the output and
   exposed it. An expected value copied from the output agrees by
   construction and locks in bugs.
4. **Property-test strategies must stay inside the property's domain.**
   The Stage 5 generator builds valid input by construction (port
   "decks", pinned boundaries such as `st.just(1024)`); out-of-domain
   cases get their own example tests.
5. **Plan review is cheap; rework is not.** Aider's architect plan
   ($0.22) raised 12 open points, all settled in the spec before any
   code; the Stage 5 plan found 4 real design gaps (ascending-only
   input, the 64512–65535 tail, P0, P6).
6. **Use the provider's numbers for cost.** Aider's log showed about
   half the real spend; OpenRouter's `/activity` matched the usage delta
   exactly. Log usage at the start and end of each part.
7. **Readable tests name what the message names.** New tests pass
   endpoints as `src=`/`dst=` keywords instead of relying on helper
   defaults, so the input shows what the expected message mentions.
8. **Triage findings; don't widen the PR.** The P-22 hint names the
   first public tier, not the egress tier: a quality issue, not a
   correctness one. Documented in the spec and filed as #16.

### Carry-overs

- #16: P-22 hint should name an egress tier.
- Older tests rely on helper defaults for endpoints; convert to
  keywords in their own PR.
- File loading still duplicated between `model.load_network` and
  `ipam.load_config`; with `ConfigError` in `errors.py`, a shared
  helper in `yamlio` no longer has an import cycle.
