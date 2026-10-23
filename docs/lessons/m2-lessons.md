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
