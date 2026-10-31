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

- **Build valid input by construction**, not by filtering random input.
  A rare `assume()` or `.filter()` is fine; filtering out most draws
  starves Hypothesis.
- **The generator must produce the inputs that separate the rules.** The
  example-test rule above applies here too: arbitrary name order, repeated
  sizes, bases other than `10.0.0.0`. A property can only catch a bug the
  generator gives it a chance to show.
- **Compute expected values by definition, not by the formula.** E.g.
  "smallest block with at least `h` usable hosts" by brute force over
  prefixes, not by copying `bit_length()` from the code.
- **Check the definition's edges too.** A definition can miss a rule it
  takes for granted: "smallest block with enough hosts" passed a /29,
  because nothing said /28 is the minimum. Assert the allowed range
  explicitly.
- **Random draws miss rare inputs. Mix them in.** If a bug changes the
  result on only a few inputs (13 of 65,531 for an off-by-one in the
  hosts formula), uniform draws almost never hit them. Add those values
  with `st.one_of(..., st.sampled_from(BOUNDARY))` and pin the exact
  cases with `@example`. Explicit examples run first.
- **Reach code the dict path can't.** A check that `validate` always runs
  first (e.g. `allocate`'s re-check) is only reachable through a
  hand-built object. Test it that way.
- **Use Hypothesis defaults.** Don't turn off the deadline or change
  `max_examples` unless a test actually needs it, and say why in the
  test. `settings.load_profile` in a test module changes settings for
  the whole session.
- **Count only a property's own assertion as a defense.** A property
  that fails because the mutant made the input invalid (e.g. a capacity
  error) is a side effect; it stops catching the bug if the generator
  changes.

### Reading a Hypothesis failure

- The printed input is **shrunk**: Hypothesis removed what it could while
  the test still failed. It is small, not always minimal. For each part,
  ask "would it still fail without this?" Parts that can go are leftovers.
- `Failing explicit example`: an `@example` failed; no random search or
  shrinking happened.
- `Hypothesis found N distinct failures`: separate failing assertions,
  each with its own input. Each is a separate finding.
- `Explanation: These lines were always and only run by failing test
  cases`: points at the code involved, often the real cause.
- A run with many failing properties is slow (minutes), because each one
  is shrunk.

### Predicting which tests a mutation fails

Don't read every test. Narrow in three steps:

1. **Reach:** which tests run the mutated line with input that gets
   there? `grep` for callers, and remember hidden routes (shared helpers
   such as `base()`, generators).
2. **Change:** on that input, does the mutant give a different result?
3. **Notice:** does an assertion look at what changed?
