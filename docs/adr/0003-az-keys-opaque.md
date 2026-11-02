# 0003. AZs are opaque keys; IPAM needs no AWS access

- **Status:** Accepted
- **Date:** 2026-10-31
- **Milestone / issue:** M2 / #5

Decided in M2 (Oct 23–31, 2026), recorded 2026-11-02 (#9). Merged in
PR #6 as `0921ec3`.

## Context

Subnets live in availability zones, and AWS names a zone in two ways:
by zone name (`us-east-1a`), which can point to a different physical
zone in each account, and by zone ID (`use1-az1`), which is the same
everywhere. The M1 recon found that terraform-aws-vpc accepts either one
(a regex on `^[a-z]+-` picks which field to set), and that its
`examples/complete` reads AZs from a live AWS data source, so it can't
even plan without credentials.

## Decision

In the YAML and in IPAM, AZs are opaque keys (e.g. `[a, b, c]`) that
match `^[a-z][a-z0-9_-]{0,63}$`. IPAM uses them only as labels and for
order. Mapping a key to an AWS zone name or zone ID is a later stage's
job (M3), not IPAM's.

## Alternatives considered

- **Require real zone names in IPAM**: ties planning to one region and
  invites the name-vs-ID confusion into the allocator.
- **Resolve zones from AWS in IPAM**: the recon example's mistake; every
  plan and test would need credentials.

## Consequences

- IPAM runs and is tested entirely offline.
- The same config can target different regions or accounts by changing
  only the mapping.
- M3 must decide how keys map to zones: zone names, zone IDs, or a data
  source resolved at plan time. This is the first new ADR of M3 (0006).
- Key order matters: it is the AZ placement order ([0004](0004-placement-order.md)).

## Links

- Recon: `docs/recon/terraform-aws-vpc.md` (Q2, Q5)
- Spec: `docs/design/m2-ipam.md` (name rules)
