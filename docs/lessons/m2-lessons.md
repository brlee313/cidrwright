# M2 lessons (working log)

Raw log, written as things happen. Polish into patterns and standing
rules at the end of M2.

Each entry: **symptom** (exact text), **cause**, **rule**.
Tags: `agent` (aider/AI wrong), `context` (AI lacked information),
`env` (shell, PATH, OS), `git`, `process`, `worked` (something that
went right and is worth repeating).

## Oct 23, 2026

### Architect review found spec gaps (`worked`)
- **What:** `/ask` for a plan before any code. The architect found that
  "no gaps" was promised but untested, that PyYAML silently keeps the
  last of duplicate keys, and that YAML 1.1 turns `no` into `False`.
  Review of its plan found more: the `hosts` test was circular (checked
  the code against its own output).
- **Rule:** plan with `/ask` first, review the plan against the spec,
  fold agreed changes into the spec in git, then implement.

### Architect proposed a fix for a problem it couldn't see (`agent`, `context`)
- **Symptom:** `ModuleNotFoundError: No module named 'cidrwright'`.
  Architect proposed `pythonpath = ["."]` in pyproject.toml.
- **Cause:** pytest ran from conda base (`/opt/anaconda3/...` in the
  traceback); the package was installed only in `.venv`. The architect
  didn't know about the editable install, so it worked around the
  symptom. Its fix would have made tests pass in the wrong environment.
- **Rule:** before accepting a fix, ask what the agent can't see. Read
  tracebacks for paths. Keep the good parts of an answer
  (`testpaths`), drop the rest.

### Bare `pytest` found the wrong environment (`env`)
- **Symptom:** same traceback as above.
- **Cause:** `--test-cmd "pytest -q"` resolves through `PATH`, and conda
  base was ahead of `.venv`. `source ~/.zshrc` reactivates base and
  flips the order: the prompt showed `(base) (.venv)`.
- **Rule:** name the interpreter: `--test-cmd ".venv/bin/python -m pytest -q"`.
  Leftmost prompt label = most recently activated environment.

### Commit landed on `main` (`git`)
- **Symptom:** `[main e10bb0a] M2: design spec for ipam allocator`.
- **Cause:** the branch was never created (or was switched away from).
- **Fix:** `git switch -c m2-ipam`, then `git branch -f main origin/main`.
  Harmless because it wasn't pushed; branch protection would have
  rejected the push anyway.
- **Rule:** read the `[branch hash]` line after every commit, or run
  `git branch --show-current` first.

### `!` in a pasted comment broke zsh (`env`)
- **Symptom:** `zsh: event not found: .aiderignore`; none of the pasted
  block ran.
- **Cause:** zsh history expansion on `!`, plus `#` not treated as a
  comment at the interactive prompt.
- **Rule:** `setopt interactivecomments` in `~/.zshrc` (done). Watch for
  `!` in pasted text.

### macOS blocked access to Downloads (`env`)
- **Symptom:** `mv: rename ... Operation not permitted`.
- **Cause:** macOS privacy protection: VS Code had no Downloads access.
  "Operation not permitted" is the privacy block; "Permission denied"
  would be file permissions.
- **Rule:** move downloads in Finder, or grant the app access in
  Privacy & Security, then quit and reopen it.

### `git check-ignore` gave no answer for folders that don't exist yet (`git`)
- **Symptom:** empty output for `.pytest_cache __pycache__ .hypothesis`.
- **Cause:** rules like `__pycache__/` match directories only, and git
  can't tell a missing path is a directory.
- **Rule:** check folders with a trailing slash:
  `git check-ignore -v __pycache__/`.

### `git diff` shows nothing for new files (`git`)
- **Cause:** it compares tracked files only.
- **Rule:** stage first, then review with `git diff --cached`.


## Oct 25–26, 2026

### Traceability check found what 41 passing tests didn't (`worked`)
- **Worksheet:** appendix of `docs/reviews/m2-stage1-tests.md`.
- **What:** mapped each spec requirement to its tests, rating coverage
  (full / partial / missing) and assertion strength (strong = location
  + specific content; medium; weak = "it raised"). One third of the
  requirements gave 11 findings.
- **Rule:** passing tests show the code does what the tests check; only
  mapping against the spec shows the tests check what the spec requires.
  Gaps hide next to a tested case: list vs. string, one key missing vs.
  both, close match vs. no match.

### Tautological assertion (`agent`)
- **Symptom:** `assert 2 ** (32 - 23) - 5 == 507` in `test_hosts_resolution`.
- **Cause:** only literals, so it can't fail. The agent was covering the
  spec's "(507 usable)" when Stage 1 had no API reporting usable hosts.
- **Rule:** trace every value in an assertion to its source; at least one
  side must come from the code under test. If deleting `ipam.py` wouldn't
  break it, it tests nothing.

### Non-discriminating and can't-fail-for-its-purpose tests (`agent`)
- **Symptom:** `test_cidr_forms_rejected` checked a substring every branch
  of the message code produced. `test_prefix_vs_vpc_skipped_when_vpc_invalid`
  used VPC `"nope"`, which has no prefix to compare, so it passed whether
  or not the comparison was skipped.
- **Rule:** a check must be able to tell the right behavior from a
  plausible wrong one. Ask: what bug would make this pass anyway?

### Rejection tests only (`agent`)
- **Symptom:** nearly every test fed bad input and expected an error.
- **Cause:** a validator that rejects everything satisfies them all.
- **Rule:** validators fail in two directions; test acceptance too,
  especially at boundaries (/16 and /28 accepted, /15 and /29 rejected).

### Delegated audit, spot-checked (`worked`)
- **What:** gave aider the rubric with `/ask` for the remaining
  requirements, demanding quoted assert lines. Spot-checked 6 claims:
  5 right (incl. two finds I'd missed); 1 "strong" rating too generous;
  its reason column contradicted its rating.
- **Rule:** ask agents to quote, so claims can be grepped. Use a control
  (a finding you already know) to calibrate trust. Read reasons against
  verdicts.

### Spec vs. code on error order (`process`)
- **What:** the test expected `config` (from the last key, `extra`)
  first, contradicting "document order". The code's rule (a mapping's
  own problems first) is better: a missing key has no document position.
- **Rule:** when a test disagrees with the spec, decide which is right;
  don't just "fix the test". Here the spec changed.

### Manual search missed two acceptance tests (`process`)
- **Symptom:** I searched for `config = validate(` and field access;
  `assert validate(base()) == EXAMPLE_CONFIG` has neither.
- **Rule:** search for the call itself, then filter out known-rejection
  patterns. Verify agent "already done" claims too; this one was right.

### Stage 1 was never committed (`git`, `process`)
- **Symptom:** `git status` before mutation checks: `cidrwright/` and
  `tests/` untracked.
- **Cause:** commit step skipped; `git restore` can't recover untracked
  files, so the mutations would have had no undo. Also, Stage 1 and the
  fix pass went into one commit, so git couldn't show whether the fix
  pass changed `ipam.py`.
- **Rule:** "working tree clean" before any experiment. Separate commits
  are what let you check an agent's claims about what it changed.

### Mutation checks: 4 of 4 caught, predictions exact (`worked`)
- **What:** `+4→+5`, bool check removed, clamp `28→29`, multicast range
  removed. Each failed exactly the predicted cases. The bool mutation was
  caught by a test the review had strengthened.
- **Rule:** predict the failing cases first ("test X, case Y, because Z").
  Overlapping rules hide a missing rule (the range check still rejected
  `prefix: True`); only content checks catch that. Mutations caught by a
  single case show where property tests are needed.

### Editor departed from the approved plan, three times (`agent`)
- **Symptom:** `test_excluded_ranges` renamed; an added `got` parameter
  in `test_bad_hosts_rejected`; `test_quote_hint_for_numbers` merged into
  two existing tests. All reasonable, none announced.
- **Rule:** read the diff against the plan; check planned tests exist by
  content, not name; check for duplicate test names. Ask the agent to
  list departures at the end of its reply.

### The aider log as a record of edits (`process`)
- **What:** `Applied edit to <file>` lines in `.aider.chat.history.md`
  showed `ipam.py` wasn't touched by the fix pass, and that the test
  file was edited in two rounds (a re-sent plan).
- **Rule:** when commits can't show what changed, the chat log can.

### Terminology: "prefix" (`process`)
- `/24` is written after the address but denotes the *prefix length*:
  the number of leading bits that identify the network. Kept the YAML
  key `prefix`; docstrings say "prefix length".

### `.DS_Store` in every repo (`env`)
- **Rule:** ignore it once, globally:
  `git config --global core.excludesFile ~/.gitignore_global`.
