# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-02
- **Milestone / issue:** between M2 and M3 / #9

## Context

M2's design decisions (greenfield planning, AZs as opaque keys, placement
order, and others) are recorded only in a project status file outside
the repo, and in passing in the spec and lessons log. Someone reading the
repo, or an AI agent given only the repo, can't see why the code is built
the way it is, and could undo a decision on purpose or by accident. M3
will add decisions with larger effects (how zones map to AWS, the policy
model), and they need a permanent place in the repo.

## Decision

Record significant design decisions as Architecture Decision Records in
`docs/adr/`, one file per decision, numbered `NNNN-title.md`, using
`docs/adr/template.md`. The rules for when to write one, status values,
and superseding are in `docs/adr/README.md`. Backfill the M2 decisions
that constrain later milestones.

## Alternatives considered

- **Keep decisions in the status file**: it's outside the repo, gets
  trimmed, and agents working in the repo don't see it.
- **One `DECISIONS.md` file**: easy to start, but entries get edited in
  place and lose their history; separate files make superseding explicit.
- **Spec "Decisions" sections only**: specs are per milestone, but
  decisions outlive and cross milestones (e.g. greenfield planning
  matters most in M5).

## Consequences

- Each decision has a stable link for PRs, issues, and aider prompts
  (`/read-only docs/adr/NNNN-...md`).
- Small extra work per decision; mitigated by the template and the
  "about one screen" limit.
- Accepted ADRs are not edited for substance, so changing a decision
  means writing a new ADR, which slows reversals on purpose.

## Links

- Issue #9
- Format based on Michael Nygard's "Documenting Architecture Decisions"
  (2011).
