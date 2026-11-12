# 0006. Policy rules name roles, not addresses or cloud objects

- **Status:** Accepted
- **Date:** 2026-11-12
- **Milestone / issue:** M3 / #11

Decided Nov 2, 2026 in the M3 spec review (design question Q2), recorded
2026-11-12 in Part B.

## Context

The policy compiler (`policy.py`) turns the `policy:` section into rules
that emitters (AWS in M4, Azure in M6) make real. A rule's source and
destination have to be written in some form, and the obvious forms
cause problems:

- **Addresses (CIDRs) go stale, and then they widen access.** Subnets come
  from IPAM, which places them by size and YAML order
  ([0004](0004-placement-order.md)). Changing tier sizes moves the
  ranges, so every address-based rule must be updated by hand. If one is
  missed, the old range now holds a *different* tier, and the stale rule
  grants that tier access nobody asked for.
- **Addresses match location, not role.** A CIDR rule admits anything
  launched in the subnet (a debug box, a stray service), not just the
  tier's instances. That breaks **Explicit grants** (spec §2.2).
- **Cloud object IDs lock in one cloud.** An AWS security group ID
  (`sg-…`) exists only after deploy and only on AWS. Azure has no use
  for it, so M6 would need new policy files or a translation table.

## Decision

Policy rules name their endpoints by role: `Tier(name)`, `Internet()`
or `Vpn()`. `policy.py` compiles them into a cloud-neutral IR
(`Rule(src, dst, proto, match, entry)`, spec §4.1) that contains no
addresses and no provider objects. Each emitter maps a role to its own
cloud's construct, e.g. AWS: `Tier("app")` → a reference to the app
tier's security group. If an emitter can't express a rule exactly, it
must refuse it (fail closed), never widen it.

## Alternatives considered

- **CIDR sources and destinations**: the lowest common denominator that
  every cloud accepts, but stale after re-allocation and matches
  anything in the range (see Context).
- **Provider IDs in the IR**: exact on AWS, but they don't exist until
  deploy and mean nothing on other clouds.
- **CIDRs in the IR, filled in from IPAM at compile time**: no stale
  hand edits, but still grants by location, and ties the compiler to
  IPAM's output.

## Consequences

- Re-running IPAM never changes the IR; `policy.py` doesn't import
  `ipam.py`.
- The compiler is tested offline with no cloud knowledge; the spec §7
  expected IR is a golden test.
- Adding a cloud (M6) means a new emitter, not compiler changes.
- Emitters carry the cloud-specific work and the duty to refuse:
  e.g. if Azure NSGs can't filter ICMP by type/code, the Azure emitter
  rejects such rules rather than allowing all ICMP (STATUS, M6 risk).
- `Internet()` and `Vpn()` still need concrete forms per cloud (AWS:
  `0.0.0.0/0`; VPN client range from `vpn:`); that is the emitters'
  job (M4).
- Revisit if a target cloud can only express rules by address; its
  emitter would then need IPAM's allocation as an input.

## Links

- Spec: `docs/design/m3-policy.md` §2.2, §4.1, §7, §10 (Q2)
- Related: [0007](0007-least-privilege-egress.md) (egress derived by
  emitters from the same IR)
- Tests: `tests/test_policy.py` (golden IR from §3/§7), added in this PR
