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


### `traceability check` mapping spec items to tests one by one
| # | Spec item | Test(s) | What it asserts | Assertion Strength | coverage | Reason |
| --------- | --------- | ------- | --------------- | ----------- |----------- | ----------- |
|S1 | Top level must be a mapping |test_missing_and_bad_top_level (case 2: [])|exactly 1 error; it starts with config| medium| partial  |location + count, no content; list tested, string not|
|S2 |Missing vpc or tiers is an error|test_missing_and_bad_top_level (case 1: {})|'vpc' and 'tiers' appear somewhere in the joined text|medium| partial |content only, no location or count; a wrong message like “unknown key ‘vpc’” would pass; only both-missing tested, never one|
|S3 |Missing cidr or azs is an error|none |- | n/a | missing|?|
|S4 | Exactly one of prefix/hosts|ttest_prefix_and_hosts_both, test_prefix_and_hosts_neither| “not both” / “needs ‘prefix’ or ‘hosts’” in the message|medium|full|content checked; no location check |
|S5 |Unknown keys error, with a “did you mean” hint |test_prefix_typo_hint, test_many_mistakes_reported_together| hint text present; location tiers[0] (public) appears in the multi-error test|medium|partial| only a tier-level typo with a close match is tested|
|S6 |An empty file gets its own message|test_load_empty_file|"empty" is in the message |medium|full| content only|
|C1 |`vpc.cidr` must be a string|test_cidr_not_a_string.|vpc.cidr location and "string" in message| strong |partial| only tested case for int type, YAML may produce other types not caught by test |
|C2 | only the `a.b.c.d/nn` form. Netmask ,hostmask and bare addresses results in errors that show the '`/nn` form.|test_cidr_forms_rejected|vpc.cidr location "expected values" in message content|strong|partial||
|C3 | Host bits → suggestion |test_host_bits_suggests_network|  location vpc.cidr + the suggested CIDR| strong | full |location + specific fix|
|C4 |VPC prefix between /16 and /28|test_vpc_prefix_range|any("/16 to /28") in message|medium|partial|test for values /15 and /29 in case a < instead of <=  for off-by-one mistakes|
|C5 |Exclude 5 ranges and the message names the range and why|test_excluded_range| multicast address is in message|medium|partial|only test 1 of 5 cases, missing loopback, link-local, reserved and this network|
|C6 |public ranges are allowed|test_public_range_allowed|If validate rejected it, the ConfigError would fail the test. So "does not raise" is the assertion, even though there is no assert statement.|weak|partial|only one sample is tested and result is not checked directly|