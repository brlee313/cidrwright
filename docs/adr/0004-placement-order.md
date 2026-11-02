# 0004. Placement order: largest first, then tier YAML position, then AZ YAML position

- **Status:** Accepted
- **Date:** 2026-10-31
- **Milestone / issue:** M2 / #5

Decided in M2 (Oct 23–31, 2026), recorded 2026-11-02 (#9). Merged in
PR #6 as `0921ec3`.

## Context

Tiers can have different subnet sizes (e.g. /23, /24, /26) in one VPC.
The M1 recon showed what fixed offsets do: `cidrsubnet(vpc, 8, k + 4)`
gives each tier four slots, so a fifth AZ makes `private[4]` equal
`public[0]` (`10.0.4.0/24`), and nothing catches it before AWS. Because
the planner is greenfield ([0002](0002-greenfield-planner.md)), the
order rule fully decides where every subnet goes, so it is part of the
output contract.

## Decision

`allocate()` packs subnets one after another from the VPC's network
address, sorted by:

1. prefix length ascending (largest blocks first),
2. then the tier's position in the YAML,
3. then the AZ's position in the YAML.

It never sorts names alphabetically.

## Alternatives considered

- **Fixed offset band per tier** (the recon pattern): collides when AZs
  outnumber slots; can't mix sizes.
- **Alphabetical order**: renaming a tier or AZ would move other subnets.
  YAML order is the order the user wrote and can see.
- **Best-fit or smallest-first**: smallest-first leaves gaps to realign
  larger blocks; best-fit is harder to predict, for no gain in a fresh
  plan.

## Consequences

- Packing largest-first keeps every block aligned with no gaps: each
  block's size divides the offset where it starts.
- No overlap by construction; capacity is checked before placing.
- The plan is deterministic: the same YAML gives the same CIDRs.
- Reordering tiers or AZs in the YAML changes the plan, which matters
  once subnets are deployed (see 0002).
- Enforced by `test_allocate_m1_regression`,
  `test_allocate_az_yaml_order_not_alphabetical`,
  `test_allocate_mixed_sizes_aligned`, and the Stage 3 properties.

## Links

- Spec: `docs/design/m2-ipam.md`
- Recon: `docs/recon/terraform-aws-vpc.md` (Q2 collision)
