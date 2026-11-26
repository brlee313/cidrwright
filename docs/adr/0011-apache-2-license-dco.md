# 0011. License under Apache-2.0; contributions by DCO sign-off, no CLA

- **Status:** Accepted
- **Date:** 2026-11-26
- **Milestone / issue:** — / #18

## Context

CIDRwright started under the MIT License. Before the first outside
contribution, the license had to match the project's goals:

- **Wide use and collaboration** come first; there are no plans to
  sell CIDRwright, a hosted version, or commercial licenses.
- **Users are companies.** It is cloud-infrastructure tooling, and
  corporate legal teams look for an explicit patent grant before staff
  use or contribute to a project. MIT has none.
- **Bruce is the sole copyright holder** today, so changing the license
  needs no one else's consent. Later it would need every contributor's.

## Decision

From 2026-11-26 CIDRwright is licensed under the **Apache License 2.0**,
with a `NOTICE` file. Contributors certify the **Developer Certificate of
Origin 1.1** with a `Signed-off-by` line on every commit, checked on each
pull request. There is no CLA.

## Alternatives considered

- **Keep MIT**: equally permissive, but no patent grant or explicit
  inbound-contribution terms.
- **AGPLv3 (+ CLA for dual licensing)**: keeps every fork's changes
  public, but many companies ban AGPL, cutting users and contributors;
  dual licensing only matters if we sell licenses.
- **MPL-2.0**: file-level copyleft (changes to CIDRwright's own files
  must be shared). A reasonable middle; rejected as less familiar to
  corporate legal than Apache-2.0 and not needed for the goals above.
- **FSL / BSL (source-available)**: block competing commercial use, but
  are not open source and deter contributors.
- **CLA instead of DCO**: only needed to relicense or sell exceptions
  later; adds friction for every contributor.

## Consequences

- Companies can use, modify and sell CIDRwright, including in closed
  products, as long as they keep the `LICENSE` and `NOTICE` and mark
  changed files. We accept that private forks are possible.
- Contributors get and give a patent license (Apache-2.0 §3), with
  inbound = outbound terms (§5).
- Without a CLA, a future license change needs every contributor's
  consent (or rewriting their code). Treat this decision as permanent.
- Every commit needs sign-off, including AI-tool commits
  (`git rebase --signoff main` before opening a PR).
- Copies released before 2026-11-26 remain available under MIT.
- Revisit only if the project's goal changes to selling CIDRwright.

## Links

- [`LICENSE`](../../LICENSE), [`NOTICE`](../../NOTICE),
  [`CONTRIBUTING.md`](../../CONTRIBUTING.md)
- Precedent: Prometheus, Envoy, Helm and Moby use Apache-2.0 with DCO.
