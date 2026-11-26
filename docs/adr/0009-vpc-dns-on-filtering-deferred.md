# 0009. VPC DNS stays on; DNS filtering is decided before M5

- **Status:** Proposed
- **Date:** YYYY-MM-DD (the day it is accepted)
- **Milestone / issue:** M4 / #20

Decided Nov 25, 2026 on the M4 design day. Settles the DNS question the
M3 spec left open (§3 example comments; deferred Nov 3).

## Context

Instances look up names through the cloud's built-in resolver (on AWS,
the Route 53 Resolver at the VPC base address + 2). Ordinary firewall
rules don't apply to it: AWS security groups can't block DNS to or from
the Resolver (Azure and GCP behave the same by default). So no policy
entry can force DNS through the proxy, or stop data leaving the VPC
inside DNS queries (DNS tunneling).

The emitter must write `aws_vpc` either way, and that resource says
whether VPC DNS is on. Interface VPC endpoints with private DNS (the
usual private path to AWS services; Secrets Manager arrives in M4
Part B) need both `enableDnsSupport` and `enableDnsHostnames` set to
true. Terraform's default for `enable_dns_hostnames` is false. Which DNS
server instances use comes from the VPC's DHCP options set; unless one
is written, AWS uses the account's default set (`AmazonProvidedDNS`).

AWS offers two ways to govern Resolver traffic by name:

- **Route 53 Resolver DNS Firewall** filters queries with domain lists.
  A query that matches no rule is answered normally. If the firewall
  can't answer, the query is blocked unless fail-open is enabled (off by
  default).
- **A Resolver outbound endpoint with a forwarding rule** sends names to
  another DNS server (e.g. the proxy); AWS-internal names (private zones,
  endpoints) still resolve locally.

## Decision

1. **VPC DNS stays on**, and instances use AWS's resolver.
2. **The emitter writes DNS settings explicitly**, including values equal
   to the default. In M4 that is, for every VPC: `enable_dns_support =
   true`, `enable_dns_hostnames = true`, and a DHCP options set with
   `AmazonProvidedDNS` as the server, associated with the VPC (exact
   fields, including `domain_name`, in the Part A spec). Later DNS
   controls follow the same rule: a DNS Firewall allow-list is written
   with its final block-all rule and fail-open disabled; a forwarding
   setup with its forwarding rule.
3. **Deferred on the record:** DNS Firewall vs outbound forwarding, and
   the network-YAML vocabulary for allowed names (`dns:`). Trigger:
   before M5's first `apply`, tracked by issue #24 (M5; blocks the first
   apply). Until then, a `dns:` key is rejected as an unknown top-level
   key (existing rule). When `dns:` is added it is **required**: a
   network file without it is an error that names the fix. No silent
   default.

## Alternatives considered

- **Proxy is the resolver** (VPC DNS off): breaks private DNS for VPC
  endpoints and private hosted zones; every client would need
  endpoint-specific names or hosts files (drift). Also can't be enforced
  on GCP, where the metadata-server resolver is always reachable.
- **Keep `enable_dns_hostnames` at its default (false):** fewer settings,
  but breaks private DNS on Part B's Secrets Manager endpoint.
- **Rely on the account's default DHCP options set:** nothing to emit, but
  the result depends on account state the repo doesn't show; a changed
  default would be invisible in `plan`.
- **Do nothing, permanently:** any instance resolves any name; fails open
  and leaves DNS tunneling open.
- **Pick DNS Firewall or forwarding now:** we don't yet know which domains
  real workloads need, what each option costs and how it behaves, or
  whether Azure and GCP can filter by name (ADR 0006: the vocabulary must
  stay cloud-neutral). M4 deploys nothing, so waiting costs nothing until
  M5, and issue #24 keeps the deadline visible.
- **Missing `dns:` means block all:** fails closed, but silently breaks
  every existing network file the day `dns:` lands.
- **Missing `dns:` means today's behavior:** non-breaking, but fails
  open, against "Defaults must fail closed". (Same reasoning as making
  `proto` required in M3 spec rev 4.)

## Consequences

- Private endpoints and private hosted zones work from M4 Part B on.
- Golden files show the DNS attributes and the DHCP options set; an
  invariant test checks them on every VPC. A manual change to either
  shows up as drift in `plan`.
- The M3 spec §3 example showed the proxy as resolver (old entries 4–7:
  app → proxy DNS, proxy → internet DNS); spec rev 6 drops those rules
  (7 entries, 10 IR rules), on this branch.
- Harder: two more resources per VPC, so goldens grow. Leaving
  `domain_name` out would change instances' search domain from AWS's
  default; the Part A spec settles it, M5 verifies it.
- Harder: until the trigger, deployments would get unfiltered DNS;
  issue #24 blocks M5's first `apply` until the deferred decision is made.
  Inputs to gather are listed in that issue.
- When `dns:` lands, every existing network file must add it (a loud,
  one-time break).
- Revisit if a workload needs DNS fully off, or if AWS lets security
  groups govern Resolver traffic.

## Links

- M3 spec `docs/design/m3-policy.md` §3 and §7 (rev 6)
- ADR [0006](0006-symbolic-endpoints.md), [0007](0007-least-privilege-egress.md)
- Private DNS needs both VPC attributes:
  https://docs.aws.amazon.com/vpc/latest/privatelink/interface-endpoints.html
- DNS Firewall evaluation and no-match behavior:
  https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-overview.html
- DNS Firewall fail-open setting (default closed):
  https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/resolver-dns-firewall-vpc-configuration.html
- Tests (planned, Part A): invariant "every VPC sets both DNS attributes
  to true and has an associated `AmazonProvidedDNS` DHCP options set"
