# Testing guidelines

Standing rules for every test in this repo, for people and for AI agents
writing tests. They come from the M2 Stage 1 test review and from Stage 2;
the history behind each rule is in `docs/reviews/` and `docs/lessons/`.

Run the suite with the venv's interpreter, so `PATH` order doesn't matter:
`.venv/bin/python -m pytest -q`.

## Writing tests

- **Assert on the code's output.** Every assertion must involve a value
  produced by the code under test. An assertion built only from literals
  can't fail: if deleting `ipam.py` wouldn't break it, it tests nothing.
- **Work out expected values independently.** Compute them by hand (or
  with `ipaddress`) before the code exists, never with helpers from the
  code under test. When prompting an agent, don't show it the answer key;
  the value is two independent computations agreeing.
- **Error tests: location and content on the same message.** Check both
  on one message, not on all errors joined together.
- **Content must be specific to the error.** A substring that every
  branch of the message code produces doesn't count.
- **Test both directions.** Valid input must be accepted, and the test
  should check the returned value, not only that nothing was raised.
  Test boundaries on both sides (e.g. /16 and /28 accepted, /15 and /29
  rejected).
- **Choose inputs that separate the right rule from plausible wrong
  ones.** A test catches a bug only if the buggy and correct code disagree
  on its input. List AZs and same-size tiers in non-alphabetical order;
  use a VPC that doesn't start at `10.0.0.0`.
- **Check who got each address,** i.e. `(tier, az, cidr)` together, not
  just the set or count of CIDRs.
- Use `pytest.mark.parametrize` for families of cases.
- Public API only; don't call helpers whose names start with `_`.

## Fix passes

- Change tests only, unless a new test exposes code that breaks the spec.
  Then fix the code minimally and list every code change separately, so
  it can be reviewed on its own.
- When a test disagrees with the spec, decide which one is right; don't
  just "fix the test".

## Checking tests an agent wrote

- Map tests to the spec (one row per requirement: coverage and assertion
  strength). Passing tests show the code does what the tests check; only
  the mapping shows they check what the spec requires.
- Check that planned tests exist by content, not by name, and look for
  duplicate names:
  `grep -o "^def test_[A-Za-z0-9_]*" tests/test_ipam.py | sort | uniq -d`.
- Ask the agent to list every departure from the approved plan at the end
  of its reply, then read the diff against the plan anyway.

## Mutation checks

- Start from a clean tree (`git status`: "working tree clean").
- Predict first: which tests fail, which assertion, what pytest shows.
- Undo with one tool (in the editor: Cmd+Z, save), not mixed with
  `git restore`. Confirm with `git diff --stat; .venv/bin/python -m pytest -q`.
- Read pytest's `At index N diff:` line, not the truncated short summary.
  The left side is what the code produced.
- A mutation caught by only one test has a single line of defense; add a
  second, different test for it.

## Property tests (Hypothesis)

To be written from M2 Stage 3.
