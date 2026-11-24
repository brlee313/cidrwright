# 0007. No default egress; each rule is granted at both ends

- **Status:** Accepted
- **Date:** 2026-11-12
- **Milestone / issue:** M3 / #11

Decided Nov 2, 2026 in the M3 spec review (design question Q6), recorded
2026-11-12 in Part B.

## Context

A security group filters traffic in two directions: **ingress** (what an
instance may accept) and **egress** (what it may send). Routes are a
separate layer: they decide where allowed traffic can go, and traffic
must pass both.

A new AWS security group comes with one egress rule: all protocols, all
ports, to `0.0.0.0/0`. That is every address: other instances in the
VPC, AWS service endpoints, and the internet wherever a route exists.

A connection needs both ends to agree. Inside the VPC, the other tiers'
ingress rules still protect them, but with open egress a compromised
tier can probe everything. Outside, the attacker controls the
destination (their server or S3 bucket accepts anything), so the
compromised tier's own egress is the **only** check left. Open egress
plus a route out means data can leave.

## Decision

No tier gets default allow-all egress. An IR rule
`Rule(src, dst, proto, match)` grants one direction, and the emitter
makes it real at **each end that is one of our tiers**:

- source is a tier → an **egress** rule on the source's group, to the
  destination;
- destination is a tier → an **ingress** rule on the destination's group,
  from the source.

An end that isn't ours (`Internet()`) gets no rule. Replies need no
rules (security groups are stateful). `Internet()` as a destination is
allowed only from a public tier (the proxy pattern); private tiers never
pair with `Internet()` in either direction (spec Q3, Q6).

Example: `web → app tcp 8080` → egress on web's group (to app's group,
8080) **and** ingress on app's group (from web's group, 8080).

## Alternatives considered

- **Keep AWS's default allow-all egress, filter only ingress**: the
  common setup, but it leaves exfiltration and probing unchecked from
  any compromised tier.
- **Separate egress entries in the YAML**: two lines per grant that must
  stay in sync; breaks **One grant, one line** (spec §2.3).
- **Split ingress/egress in the IR**: puts an AWS detail in the
  cloud-neutral IR ([0006](0006-symbolic-endpoints.md)).

## Consequences

- A compromised tier can reach only what the policy grants it.
- One YAML line still means one grant; the doubling happens in the
  emitter and is tested there (M4).
- Every outbound need must be written down: tiers with no outbound rule
  can't start connections (e.g. no OS updates) until a grant is added
  (spec §3 comments).
- The AWS emitter must make sure the default egress rule is removed
  (verify how Terraform handles it in M4).
- Limit: security groups can't block DNS to the Route 53 Resolver, so
  egress rules alone don't close DNS as a leak path; see the M4 DNS
  governance decision.
- Revisit if a target cloud can't filter egress by destination group;
  its emitter must then refuse or use a narrower equivalent, never
  open egress (0006's fail-closed rule).

## Links

- Spec: `docs/design/m3-policy.md` §2.2–2.4, §3, §4.1, §10 (Q3, Q6)
- Related: [0006](0006-symbolic-endpoints.md)
