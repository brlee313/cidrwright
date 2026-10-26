# M2 Stage 1: test review and fix list

Review of `tests/test_ipam.py` against `docs/design/m2-ipam.md`, Oct 25, 2026.
Method: traceability check (one row per spec requirement), done by hand
for Structure and `vpc.cidr`, by aider `/ask` for the rest, with four
aider claims spot-checked against the code (all held up; one strength
rating was too generous).

Starting point: 41 tests passing.

## Rules for the fix pass

- **Tests only**, unless a new test exposes code that breaks the spec.
  Then fix the code minimally and list every code change separately, so
  it can be reviewed on its own.
- Every assertion must involve a value produced by the code under test.
  No assertion built only from literals.
- When a test checks one error, check its location **and** content on
  the **same message**, not on all errors joined together.
- Content checks must be specific to the error being tested: a substring
  that every branch of the message code produces doesn't count.
- Use `pytest.mark.parametrize` for families of cases.
- Public API only; no helpers starting with `_`.

## A. Tests that can't fail

1. `test_hosts_resolution`: delete `assert 2 ** (32 - 23) - 5 == 507`
   and its `if`. It uses only literals. Usable hosts get checked for real
   in Stage 2 through `Allocation.usable_hosts`.
2. `test_prefix_vs_vpc_skipped_when_vpc_invalid`: `"nope"` has no prefix
   to compare, so the test passes whether or not the comparison is
   skipped. Use a VPC that parses but is invalid, such as `10.0.0.0/29`,
   with a tier prefix of 20. Assert exactly one error, at `vpc.cidr`.

## B. Valid input must be accepted

The suite has only three tests that feed valid input and use the result,
so a validator that rejected everything would pass most of it.

3. The spec's example YAML, as a dict, through `validate`: assert the
   result equals a hand-built expected `Config`.
4. VPC prefixes /16 and /28 accepted.
5. Tier prefixes 16 and 28 accepted; a tier prefix equal to the VPC
   prefix accepted.
6. Names and AZ keys with digits, `_` and `-` accepted; a 32-character
   tier name and a 64-character AZ key accepted.
7. `test_capacity_exactly_full_ok`: assert on the returned `Config`, not
   only that nothing was raised.

## C. Rejection cases with no test

8. Top level is a string.
9. `vpc` missing alone, and `tiers` missing alone: location `config`,
   content says which key is missing.
10. `vpc` missing `cidr`, and missing `azs`: location `vpc`.
11. `vpc` is not a mapping; unknown key inside `vpc`.
12. `azs` is not a list. Include a string such as `"abc"`, which must not
    be accepted as three AZs named `a`, `b` and `c`.
13. AZ pattern: uppercase, leading digit, bad character, 65 characters
    all rejected.
14. `tiers` is not a list; a tier item is not a mapping.
15. Unknown key with **no** close match (e.g. `colour`): an error
    **without** "did you mean".
16. `vpc.cidr` as a list, a bool and `None`.
17. Netmask form, hostmask form and bare address, each as its own case,
    each asserting the hint that shows the `/nn` form.
18. VPC prefix /15 rejected (the current test uses /12, which can't catch
    an off-by-one at the lower edge).
19. All five excluded ranges, each asserting the message names the range.
20. Tier prefix 15 and 29 rejected; `"24"`, `24.0` and `None` rejected.
21. Tier prefix one below the VPC prefix (19 with a /20) rejected.
22. `hosts`: `True`, a string, a float and a negative number rejected.
23. Quote hint on the number path: an AZ written as `1`, a name written
    as `123`.
24. `load_config` with a Python tag, e.g. `vpc: !!python/name:builtins.len`:
    `ConfigError` from the YAML layer. Assert the file name and a
    YAML-level message, so a "vpc is not a mapping" error from an unsafe
    loader would fail the test.
25. YAML syntax error: assert the line number, not only the file name.
26. Duplicate keys at the top level and inside `vpc`.

## D. Weak assertions to strengthen

27. `{}` case in `test_missing_and_bad_top_level`: check each message
    separately: location `config`, the key name, and "missing".
28. `test_prefix_and_hosts_both` / `_neither`: assert the `tiers[0]`
    location.
29. AZ item not a string (`False`): assert `vpc.azs[1]` and the quote
    hint on the same message.
30. `test_many_mistakes_reported_together`: add a content check for each
    error, so the two errors at `tiers[0] (public)` and the two at
    `tiers[1]` can't be swapped for other errors at the same location.
31. Capacity tests: assert the error is at `config`.
32. Empty file: assert location `config`.
33. Empty `azs` and empty `tiers`: add a content check that says the list
    is empty.

## Spec changes made during the review

- Error order: a mapping's own problems (unknown or missing keys) come
  before the problems inside it. The code already did this; the spec now
  says so.
- The capacity error is reported at `config`.

## Appendix: manual traceability worksheet (Structure and `vpc.cidr`)

Done by hand on Oct 25, 2026, before the fix pass. It describes the
tests as they were then; the fix list above addresses each gap. The
remaining requirements were audited by aider and spot-checked.

Strength: strong = location + specific content; medium = one of them,
or content that matches on every code path; weak = only "it raised".

| # | Spec item | Test(s) | What it asserts | Strength | Coverage | Reason |
| --- | --- | --- | --- | --- | --- | --- |
| S1 | Top level must be a mapping | `test_missing_and_bad_top_level` (case 2: `[]`) | exactly 1 error; it starts with `config` | medium | partial | location + count, no content; list tested, string not |
| S2 | Missing `vpc` or `tiers` is an error | `test_missing_and_bad_top_level` (case 1: `{}`) | `'vpc'` and `'tiers'` appear somewhere in the joined text | medium | partial | content only, no location or count; a wrong message like "unknown key 'vpc'" would pass; only both-missing tested, never one |
| S3 | Missing `cidr` or `azs` is an error | none | — | n/a | missing | no test omits these keys |
| S4 | Exactly one of `prefix`/`hosts` | `test_prefix_and_hosts_both`, `test_prefix_and_hosts_neither` | "not both" / "needs 'prefix' or 'hosts'" in the message | medium | full | content checked; no location check |
| S5 | Unknown keys error, with a "did you mean" hint | `test_prefix_typo_hint`, `test_many_mistakes_reported_together` | hint text present; location `tiers[0] (public)` appears in the multi-error test | medium | partial | only a tier-level typo with a close match is tested |
| S6 | An empty file gets its own message | `test_load_empty_file` | "empty" in the message | medium | full | content only |
| C1 | `vpc.cidr` must be a string | `test_cidr_not_a_string` | `vpc.cidr` location and "string" in the message | strong | partial | only an int tested; YAML can also give a list, bool or `None` |
| C2 | Only the `a.b.c.d/nn` form; netmask, hostmask and bare addresses rejected, with the `/nn` form shown | `test_cidr_forms_rejected` | `vpc.cidr` location; "a.b.c.d/nn" in the message | medium | partial | every branch of the message contains "a.b.c.d/nn", so the check passes whichever hint was chosen; it should assert the hint itself, e.g. "e.g. 10.0.0.0/16" |
| C3 | Host bits set → suggestion | `test_host_bits_suggests_network` | location `vpc.cidr` + the suggested CIDR | strong | full | location + specific fix |
| C4 | VPC prefix between /16 and /28 | `test_vpc_prefix_range` | "/16 to /28" in a message; only /12 and /29 tested | medium | partial | /29 rejected is tested; missing /15 rejected (/12 can't catch an off-by-one at the lower edge) and /16, /28 accepted |
| C5 | 5 excluded ranges; message names the range and why | `test_excluded_range` | multicast range in the message | medium | partial | only 1 of 5 ranges; loopback, link-local, reserved and this-network untested |
| C6 | Public ranges are allowed | `test_public_range_allowed` | no assert; an exception would fail the test, so "does not raise" is the check | weak | partial | one sample; the returned `Config` isn't checked |
