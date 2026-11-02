# NNNN. Title as a short decision ("Tiers are data, not code")

- **Status:** Proposed | Accepted | Superseded by NNNN | Deprecated
- **Date:** YYYY-MM-DD (the day it was accepted)
- **Milestone / issue:** M? / #?

<!-- Backfilled ADRs: add "Decided: <month>, recorded: <date>" and
     link the PR or commit where the decision was made. -->

## Context

What problem or constraint forced a choice? State the facts a reader
needs, with links (spec, recon notes, issue). No solution yet.

## Decision

What we do, in one or two sentences, in active voice: "`allocate()`
places subnets largest first, then by tier YAML position, then by AZ
YAML position."

## Alternatives considered

- **Option**: why not.
- **Option**: why not.

## Consequences

- What becomes easier.
- What becomes harder, or what we give up.
- What would make us revisit this decision.

## Links

- Spec, PR, tests that enforce it (`tests/test_...::test_...`).
