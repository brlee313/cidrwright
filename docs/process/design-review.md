# How design decisions are made and reviewed

Every significant design decision in CIDRwright is recorded as an ADR
(`docs/adr/`). This page describes how those decisions are reached and
checked, so a reader can judge the process, not just the result.

## Roles

- **I decide and review.** I choose between options, accept or reject
  each finding, and sign off on every ADR and expected test answer.
- **The AI assistant drafts, researches and challenges.** It lays out
  options, gathers evidence from vendor documentation, writes drafts, and
  questions my answers. Its claims are checked like anyone else's:
  quote the claim, then confirm it in the code (`grep`) or the vendor
  docs. That applies both ways: "this is missing" and "this is already
  done" both get checked.

## The method

1. **List the real options side by side.** Include "do nothing" as a
   baseline, so its cost is visible.
2. **Trace a bad input through each option.** Take one wrong or missing
   value and follow it step by step: where is it checked, and does it
   fail at emit (offline, in seconds), at `terraform plan`, at `apply`,
   or never?
3. **Catalog the mistakes, then map checks to them.** List what can go
   wrong in an input, then which check catches each one. A mistake that no
   stage catches gets its own check first.
4. **Decide now only what is due.** For each open question: does current
   work depend on it, is it cheap to reverse, will we know more later, and
   what does waiting cost? A deferred decision is written down with its
   options, the inputs to gather, and a trigger, and a deadline that
   matters gets a tracked issue.
5. **Review the draft ADR against a checklist** (below), then revise.

## Review checklist

- Context states facts only, with sources; no solution yet.
- Someone could implement it from the Decision section alone.
- Every rule says what fails and what is allowed, and something enforces
  it (code, or at least a visible gate).
- Each rejected alternative has a real, decisive reason.
- Consequences state the costs and a revisit trigger, not just benefits.
- Spec-level detail (field names, message wording) lives in the spec.
- About one screen long.

The most useful habit: **trace a bad input, don't just read.** Reading
finds wrong statements; tracing finds missing ones.

## Beyond ADRs

- **Expected answers are worked out independently.** A test the AI wrote
  against code the AI wrote proves only that the two agree. For golden
  files and other expected outputs, I derive the answer from the spec or
  the input by hand, and compare it with the test line by line, before
  trusting a green run.
- **Autonomy is set by risk, not by habit.** Each milestone gets an agent
  mode based on three questions: is "done" written down, is there a
  strong automated gate, and how bad and reversible is a mistake? The
  emitter work runs near-loop (specs plus tests as the gate); the first
  real AWS deployment drops back to in-loop (credentials, cost, unknown
  failures); a refactor with byte-identical goldens can run out-loop.

## Worked example: availability zones (ADR 0008)

The network file names zones with opaque keys (`a`, `b`); a committed
target file maps each key to an AWS zone ID. Cataloging mistakes in that
file found one that nothing else catches: **two keys mapped to the same
zone ID**. The Terraform is valid, `plan` and `apply` succeed, and the
network looks redundant while sitting in one data center. So the target
loader rejects duplicate IDs.

The same review corrected an early assumption. The first draft said a
zone ID from the wrong region fails at `plan`; it actually fails at
`apply`, possibly after the VPC exists (a partial build). Because the
recommendation rested on that claim, the design changed: a region check
was added so the mistake fails offline, at emit.

## Worked example: DNS (ADR 0009)

Tracing one DNS query showed that AWS security groups never see traffic
to the VPC's built-in resolver, so no firewall rule can govern DNS. The
emitter had to decide one thing immediately, whether VPC DNS is on,
because it writes the VPC resource and a later part needs private DNS.
Domain filtering was deferred to before the first real deployment, with
a blocking issue as the gate. The review also found that "fails closed"
depended on configuration we write ourselves (a final block-all rule),
not on the AWS product's defaults.
