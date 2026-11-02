# 0005. Tiers are data, not code

- **Status:** Accepted
- **Date:** 2026-10-31
- **Milestone / issue:** M2 / #5

Decided in M1–M2 (Oct 23–31, 2026), recorded 2026-11-02 (#9). Merged in
PR #6 as `0921ec3`.

## Context

The M1 recon of terraform-aws-vpc (v6.7.3) found seven fixed tiers
(public, private, database, redshift, elasticache, intra, outpost), each
a copy-pasted block. One tier (redshift) takes 21 variables, 8 resources,
11 outputs, and 21 wrapper references. The copies have drifted apart
(`tags_per_az` on only two tiers, `lower()` on only two). Adding a tier
means 60+ hand edits across four or more files.

## Decision

Tiers are a list in the YAML config, each with a name
(`^[a-z][a-z0-9_-]{0,31}$`) and a size. Every stage (IPAM now; policy
and Terraform emitters later) loops over whatever tiers the config
lists. No code names a specific tier. Adding a tier is a one-entry YAML
change.

## Alternatives considered

- **Fixed tiers in code** (the recon module's approach): the duplication
  and drift found in M1.
- **A fixed set of tiers with optional extras**: still puts tier names
  in code, and still needs edits to add one.

## Consequences

- One code path per stage, tested once for all tiers.
- Tier-specific behavior (e.g. "this tier gets a NAT route", "this tier
  is public") must be expressed as tier attributes in the YAML, not as
  name checks. M3 and M4 add those attributes and must validate them up
  front.
- A tier's position in the YAML matters: it sets placement order for
  same-size tiers ([0004](0004-placement-order.md)).

## Links

- Recon: `docs/recon/terraform-aws-vpc.md` (Q6, "Decisions this forces")
- Spec: `docs/design/m2-ipam.md`
