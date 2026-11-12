# Architecture Decision Records

An ADR records one decision that shapes CIDRwright's design. It says what
was decided, why, and what we gave up. Specs say *what* to build; ADRs say
*why it is built this way*, so a later reader (or an AI agent) doesn't
undo a decision without knowing its reasons.

## When to write one

Write an ADR when a decision:

- is hard or expensive to reverse (data model, file formats, public API);
- rules out a reasonable alternative someone might later suggest; or
- constrains future milestones (e.g. "IPAM needs no AWS access").

Don't write one for a choice that's obvious, local to one function, or
already enforced by a test with a clear name.

## How

1. Copy `template.md` to `NNNN-short-title.md`, using the next free
   number (4 digits, never reused).
2. Fill it in. Keep it to about one screen.
3. Add it to the index below in the same PR as the change it describes,
   or in its own PR if it records an earlier decision.

## Status values

- **Proposed**: under discussion; not yet binding.
- **Accepted**: in force.
- **Superseded by NNNN**: replaced. Leave the text as it was, change only
  the status line, and link the new ADR.
- **Deprecated**: no longer applies, with no replacement.

Accepted ADRs are not edited for substance. To change a decision, write
a new ADR that supersedes the old one.

A stale pointer or fact in an accepted ADR (not the decision itself) is
fixed by appending a dated, italic note under it ("*Update YYYY-MM-DD:
…*"), leaving the original text in place.

## Index

| No. | Title | Status |
| --- | --- | --- |
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-greenfield-planner.md) | The subnet planner is greenfield | Accepted |
| [0003](0003-az-keys-opaque.md) | AZs are opaque keys; IPAM needs no AWS access | Accepted |
| [0004](0004-placement-order.md) | Placement order: largest first, then YAML order | Accepted |
| [0005](0005-tiers-are-data.md) | Tiers are data, not code | Accepted |
| [0006](0006-symbolic-endpoints.md) | Policy rules name roles, not addresses or cloud objects | Accepted |
