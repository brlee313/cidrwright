# 0010. One SG rule resource per tier end; tiers reference each other's SGs

- **Status:** Proposed
- **Date:** YYYY-MM-DD (the day it is accepted)
- **Milestone / issue:** M4 / #?

Decided Nov 25, 2026 on the M4 design day. Sets how the AWS emitter
realizes the IR from [0006](0006-symbolic-endpoints.md) and
[0007](0007-least-privilege-egress.md).

## Context

M3 compiles the policy into IR rules: (source, destination, proto,
match). ADR 0007 requires each rule to be granted at both ends: egress on
the source, ingress on the destination. "One grant, one line" (M3 spec
§2.3) requires that deleting one policy entry removes exactly its access.

The Terraform AWS provider offers three ways to write SG rules: inline
`ingress`/`egress` blocks in `aws_security_group`, the older
`aws_security_group_rule`, and `aws_vpc_security_group_ingress_rule` /
`_egress_rule`. The provider calls the last pair the current best
practice; each holds one peer (one CIDR or one referenced SG). Mixing
inline rules with rule resources on the same SG causes conflicts,
perpetual diffs and overwritten rules.

A tier has one subnet per AZ. A rule can name the peer tier by its
subnet CIDRs or by its security group. An SG reference matches traffic
from any network interface that has that SG attached, whatever its
address.

When Terraform creates an SG in a VPC, it removes AWS's default
allow-all egress rule. Each VPC also has a default SG; an instance
launched without an SG gets it, and by default it allows all traffic
between its members and all outbound traffic. The CIS AWS Foundations
Benchmark (6.5) and AWS Security Hub (EC2.2, severity High) require the
default SG to have no inbound and no outbound rules.

## Decision

1. **Each IR rule becomes one resource for each end that has an SG**:
   an `aws_vpc_security_group_ingress_rule` on the destination's SG and an
   `aws_vpc_security_group_egress_rule` on the source's SG. Tier → tier
   makes two; a rule with `internet` at one end makes one, on the tier's
   side (`internet` has no SG). Never inline `ingress`/`egress` blocks,
   never `aws_security_group_rule`.
2. **The peer** in each resource is:
   - another tier → `referenced_security_group_id` = that tier's SG;
   - `internet` → `cidr_ipv4 = "0.0.0.0/0"` (M3 spec §2.4; never `::/0`);
   - `vpn` → **deferred** to the M4 Part C ADR (routing vs masquerade):
     an SG reference to the WireGuard host's SG if it masquerades, or the
     `client_pool` CIDR if it routes. Until then the emitter refuses IR
     rules with a `Vpn()` endpoint (error, not a guess).
3. **One SG per tier.** The emitter creates it and outputs its ID (and
   the tier's subnet IDs) as Terraform outputs. Workloads in a tier are
   expected to attach it; the emitter doesn't launch them, so it can't
   enforce this. A workload that doesn't attach it gets the emptied
   default SG (#4) and no access.
4. **The VPC's default SG is emptied**: the emitter writes
   `aws_default_security_group` with no rules, so anything launched
   without a tier SG gets no access (same "write it explicitly" rule as
   ADR 0009; meets CIS 6.5 / Security Hub EC2.2).

## Alternatives considered

- **Subnet CIDRs for tier peers:** one resource per peer subnet, so one
  IR rule becomes 2 × AZs resources and the count changes when an AZ is
  added. Resizing a tier moves its subnets and rewrites every rule that
  names it: a capacity change shows up as a firewall change, with a
  window during `apply` where rules point at old ranges. Grants access
  by location: an instance in the app subnet without the app SG would
  reach the database.
- **Inline rules:** one change rewrites the SG's whole rule set; tiers
  that reference each other risk dependency cycles; can't be mixed with
  rule resources later.
- **`aws_security_group_rule`:** superseded by the per-rule VPC resources.
- **Leave the default SG as AWS creates it:** an instance launched
  without a tier SG could talk to every other such instance and reach
  anything outbound.

## Consequences

- One policy entry → its IR rules → one resource per tier end each;
  deleting the entry deletes exactly those. Golden diffs show only real policy
  changes; resizing a tier or adding an AZ changes no rule resource.
- Rules follow roles (ADR 0006), so moving subnets needs no rule changes.
- Invariant tests (Part A): every IR rule maps to exactly one ingress
  resource if its destination is a tier and exactly one egress resource
  if its source is a tier, and nothing else; tier peers use `referenced_security_group_id`;
  `0.0.0.0/0` appears only for `internet` rules on public tiers; no inline
  blocks; the default SG has no rules.
- Harder: SG references work only inside one VPC (or peered VPCs);
  cross-VPC designs would need a new decision. Rule resources are
  addressed by name, so names must be deterministic (Part A spec).
- Harder: until Part C, a network with `vpn` rules can't be emitted.
- Scope is new VPCs (greenfield, as in [0002](0002-greenfield-planner.md)).
  In an existing VPC, emptying the default SG would cut off anything still
  using it.
- Revisit if CIDRwright supports multi-VPC networks, adopts existing
  VPCs (decision 4 then needs a plan-time check), or if the provider
  replaces these resources.

## Links

- M3 spec `docs/design/m3-policy.md` §2.3, §2.4, §4 (IR)
- Provider best practice:
  https://www.pulumi.com/registry/packages/aws/api-docs/vpc/securitygroupingressrule/
  (generated from the Terraform AWS provider docs)
- Don't mix inline and rule resources:
  https://aquasecurity.github.io/tfsec/v0.61.3/checks/aws/vpc/disallow-mixed-sgr
- One CIDR per rule as current practice:
  https://github.com/cloud-gov/terraform-provision/pull/1782
- Default egress removed on create; default SG behavior:
  https://www.pulumi.com/guides/how-to/aws-security-group/ ;
  https://docs.datadoghq.com/security/code_security/iac_security/iac_rules/terraform/aws/vpc_default_security_group_accepts_all_traffic/
- Default SG controls: CIS AWS Foundations 6.5
  https://www.tenable.com/audits/items/CIS_Amazon_Web_Services_Foundations_v7.0.0_L2.audit:14c7a209497d0068d11349c1cc75b4c2 ;
  Security Hub EC2.2 https://docs.aws.amazon.com/securityhub/latest/userguide/ec2-controls.html
- Tests (planned, Part A): invariants above
