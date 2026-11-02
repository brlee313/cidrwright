# 0002. The subnet planner is greenfield: it does not preserve existing allocations

- **Status:** Accepted
- **Date:** 2026-10-31
- **Milestone / issue:** M2 / #5

Decided in M2 (Oct 23–31, 2026), recorded 2026-11-02 (#9). Merged in
PR #6 as `0921ec3`.

## Context

`allocate(config)` turns a YAML config into a `(tier, az) → CIDR` plan.
A planner can either compute every plan from scratch or take the
currently deployed subnets as input and keep them where they are.
Preserving allocations needs a source of truth for what is deployed
(Terraform state or AWS), rules for what to do when a kept subnet no
longer fits, and a much larger test space. Nothing is deployed until M5.

## Decision

`allocate()` is a pure function of the config. It computes every plan
from scratch and takes no account of earlier plans or deployed subnets.
Preserving existing allocations is a stated non-goal of the M2 spec.
The signature leaves room for a later `allocate(config, existing=None)`.

## Alternatives considered

- **Preserve existing allocations now**: needs deployed state that
  doesn't exist before M5, and would roughly double M2's scope.
- **Stable hashing (CIDR derived from tier and AZ names)**: avoids some
  moves but wastes space, and can't pack mixed sizes without collisions.

## Consequences

- `allocate()` is deterministic and needs no AWS access or state, so it
  is easy to test with properties (`tests/test_ipam.py`).
- **Re-planning can move subnets.** Adding a tier or AZ, changing a
  size, or reordering the YAML can change existing CIDRs. Once subnets
  exist in AWS, Terraform would replace them (destroy and recreate),
  which takes down anything running in them.
- Safe through M4 (nothing is applied). **Revisit before M5's first
  real `terraform apply`**: either implement `existing=`, or add a guard
  that refuses a plan that moves an already deployed subnet.

## Links

- Spec: `docs/design/m2-ipam.md` (non-goals)
- Related: [0004](0004-placement-order.md) (what determines the plan)
