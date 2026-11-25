# 0008. AZ keys map to zone IDs in a committed target file

- **Status:** Proposed
- **Date:** YYYY-MM-DD (the day it is accepted)
- **Milestone / issue:** M4 / #?

Decided Nov 24–25, 2026 on the M4 design day. Closes the question that
[0003](0003-az-keys-opaque.md) left open (moved to M4, M3 spec §10 Q1).

## Context

The network YAML names AZs with opaque keys (`azs: [a, b]`, ADR 0003).
To emit Terraform, each key must become a real AWS zone, which AWS names
two ways:

- **Zone name** (`us-east-1a`): in Regions with independently mapped
  AZs (accounts created before Nov 2025), the same name can be a
  different physical zone in each account.
- **Zone ID** (`use1-az1`): the same physical zone in every account.
  AWS recommends IDs across accounts and announces outages by ID.

AWS's multi-account pattern records zone IDs and keeps the mapping
outside the template (in Parameter Store). Picking AZs from the
`aws_availability_zones` data source by index needs credentials, has no
guaranteed order, and fails only at `plan`. Our constraint (0003):
planning and emitting run offline.

## Decision

Keys stay opaque. A separate, committed **target file** holds the
deployment facts:

```yaml
cloud: aws           # must be "aws"; any other value is an error
region: us-east-1
azs:                 # key -> zone ID
  a: use1-az1
  b: use1-az2
```

Run as `cidrwright emit <network.yaml> --target <target.yaml>`.
`--target` is required: no default, no discovery. The emitter writes
`availability_zone_id` (never `availability_zone`) on each subnet.

`target.py` loads the file with the M2 conventions (duplicate, unknown
or missing keys rejected; all errors collected into one `ConfigError`)
and checks, offline:

1. Each value matches `^[a-z0-9]+-az[0-9]+$`, so a zone name pasted in
   place of an ID (`us-east-1a`) is rejected.
2. No two keys map to the same zone ID (that would put "two AZs" in one
   physical zone; nothing later would notice).
3. Each ID's prefix matches `region`, via a region → prefix table in
   `target.py` (`us-east-1` → `use1`). Prefixes can't be derived from
   region names (`eu-central-1` → `euc1`). A region not in the table is
   an error. The table starts with the regions the tests use; each entry
   comes from AWS's published AZ ID list and has a test.

At emit, the network's `azs` keys and the target's keys must be the same
set; a missing or extra key is an error (only emit sees both files).

## Alternatives considered

- **Zone names** (keys plus region, or names in a mapping): names differ
  per account; keys gain meaning.
- **Mapping in the network YAML** (a map, or a `targets:` section):
  breaks the M2 list shape; adding or changing a region edits the design.
- **Resolve at plan time** (data source by index, Parameter Store,
  `.tfvars`): needs credentials or fails late; goldens never show IDs.
- **Mapping in a CLI flag or env var**, or a **default target**: not
  reproducible from the repo; a default yields valid-looking output for
  the wrong place ("Defaults must fail closed").
- **No region check**: a wrong-region ID fails only at `apply`, possibly
  after the VPC exists (a partial build).

## Consequences

- Retargeting changes only the target file, as 0003 promised, and the
  repo shows where every subnet lands (`grep use1-az4`).
- Goldens are per (network, target) pair; tests need a target fixture
  (`tests/data/targets/use1.yaml`).
- Harder: each deployment is two files to keep in step (caught at emit).
  The prefix table must be maintained; a new region is a one-line PR,
  and a wrong entry rejects valid IDs (fails closed, but confusing).
- `cloud:` lets the M6 Azure emitter reject an AWS target clearly. The
  account isn't in the file: zone IDs don't depend on it, and M5's
  credentials decide it.
- **Deferred: edge zones** (Local, Wavelength; IDs like `use1-bos1-az1`).
  Check 1 rejects them. They hang off a parent zone, aren't part of the
  redundancy set, and Wavelength uses carrier gateways. Revisit if a user
  needs edge subnets: that needs a zone-kind concept in the model, not a
  wider pattern.
- Not checked offline: that a zone exists and is enabled. M5 option: emit
  `aws_availability_zone` lookups by `zone_id` so `plan` fails first.
- Revisit if the prefix table becomes a burden or AWS changes the ID
  format.

## Links

- [0003](0003-az-keys-opaque.md); M3 spec `docs/design/m3-policy.md` §10 Q1
- AZ IDs: https://docs.aws.amazon.com/ram/latest/userguide/working-with-az-ids.html ;
  https://docs.aws.amazon.com/global-infrastructure/latest/regions/az-ids.html
- AWS pattern: https://docs.aws.amazon.com/prescriptive-guidance/latest/patterns/use-consistent-availability-zones-in-vpcs-across-different-aws-accounts.html
- Outages by ID (use1-az4): Dec 22, 2021
  https://www.theregister.com/2021/12/22/aws_outage/ ; May 7, 2026
  https://www.networkworld.com/article/4168878/aws-hit-by-us-east-1-outage-after-data-center-thermal-event.html
- Data source by index failing: https://discuss.hashicorp.com/t/the-index-is-greater-than-or-equal-to-the-length-of-the-collection/59708
- Edge zone IDs: https://docs.aws.amazon.com/local-zones/latest/ug/available-local-zones.html
- Tests (planned, Part A): `tests/test_target.py`
