# Recon: terraform-aws-vpc @ b3abd6d (v6.7.3)

Milestone M1 of CIDRwright: read an unfamiliar codebase with aider's
`/map` and `/ask`, verify every answer against the code, and record what
to copy or avoid before writing `ipam.py`.

- Module: github.com/terraform-aws-modules/terraform-aws-vpc, pinned to
  commit `b3abd6d` (Sept 18 2026). Line numbers below refer to this version.
- Tooling: aider v0.86.2, `--no-auto-commits --map-tokens 2048`, files
  loaded with `/read-only` (never `/add`).
- Models: GPT-4o (2024-08-06) at first, then Claude Sonnet 5.5, both via OpenRouter.

## How aider's repo map handled HCL

- HCL is parsed: `resource`, `variable`, `locals` and `output` blocks
  appear with excerpt lines.
- Files are listed alphabetically, not by rank. Rank shows only in which
  files make it into the 2048-token budget and how much of each survives.
- Ranking rewards names that repeat. `cidr_block`, `rule_number` and
  `required_version` crowded out rarer but important variables
  (`public_subnets`, `azs`, `single_nat_gateway`). Nine `versions.tf`
  files were pure noise.
- Missing from the first map: `examples/complete/main.tf` (where the CIDRs
  are actually computed), all NAT gateway resources, and almost all of
  `variables.tf` (2 of about 200 variables).
- Map lines are cut at about 100 characters. The key line
  `cidr_block = ... element(concat(var.public_subnets, [""]), count.index)`
  was cut off before the variable name.
- After `/read-only` of three files, those files dropped out of the map,
  which confirms read-only files are excluded. The freed budget went to
  `vpc_cidr` lines in 7 examples (boosted because `examples/complete` was
  in the chat) plus `wrappers/` and flow-log IAM noise. NAT and
  `cidrsubnet` logic were still absent. The map adapts to names in the
  chat, not to what the question means.
- Conclusion: for Terraform, the map shows where things are, not what they
  do. Load files with `/read-only` before trusting an answer about logic.

## Where aider was wrong or vague

1. **Generic-plausible** (GPT-4o, map only, Q2): answered from general
   Terraform habits ("typically hardcoded or passed as variables") with no
   file, line or value. In fact the CIDRs are computed with `cidrsubnet`.
2. **Substitution** (GPT-4o, files loaded, Q1): asked how the *module*
   computes CIDRs, it answered with the *example*. The module computes
   nothing: `main.tf:153` picks the nth string from `var.public_subnets`
   with `element()`.
3. **Terminology error** (GPT-4o): called `cidrsubnet`'s second argument
   the "prefix length". It is newbits: /16 + 8 = /24.
4. **Missed** (GPT-4o): the offsets `k+4`, `k+8`... give each tier 4 slots,
   so a 5th AZ makes `private[4] == public[0] == 10.0.4.0/24`. Nothing
   catches this until AWS rejects it at apply time.
5. **Line numbers**: aider sends files without line numbers, so no model
   can know them. GPT-4o silently left them out; Sonnet 5.5 said why it
   couldn't give them. Ask for quotes, then find them with `grep -n`.
6. **Aider's file prompts**: after answers, aider offers to add files it
   saw mentioned. It offered the root `main.tf` when the answer was about
   `examples/complete/main.tf`, and "Yes" would add a file as editable,
   not read-only. Answer N or D during recon.

## Same question, two models (files loaded, identical prompt)

| | GPT-4o (2024-08) | Sonnet 5.5 |
| --- | --- | --- |
| Module vs. example | Answered about the example | "The module doesn't compute IPv4 subnet CIDRs at all" |
| `cidrsubnet` 2nd arg | "prefix length" (wrong) | "adds 8 bits", /56 → /64 (right) |
| Line numbers | Silently left out | Explained why it couldn't |
| Extras | none | Volunteered `element()` wraparound, AZ name/ID regex, `outpost_az` exception |
| Cost per ask | $0.09 | $0.08 |

Lesson: on reading tasks, the model mattered more than the context. Both
had the same files; only one understood them. A stronger model's mistakes
are rarer and more convincing, so verifying every claim is still required.

## Answers (all verified against the code)

**Q1. How does the module compute subnet CIDRs per AZ?** It doesn't.
`public_subnets` is a `list(string)` the caller supplies
(`variables.tf:198`). `main.tf:153`:
`cidr_block = element(concat(var.public_subnets, [""]), count.index)`.
The only `cidrsubnet` calls in `main.tf` are for IPv6.

**Q2. Where do the CIDRs in examples/complete come from?** The caller
computes them (`examples/complete/main.tf:32-37`):
`cidrsubnet(local.vpc_cidr, 8, k + 4)` and so on, with
`vpc_cidr = "10.0.0.0/16"` (line 11). Each tier gets a hand-picked offset
band of 4 slots. All subnets are the same size (/24). There is no overlap
check and no allowance for AWS's 5 reserved addresses. `azs` comes from a
live AWS data source, so the example can't even plan without credentials.

**Q3. How many NAT gateways?** `nat_gateway_count` at `main.tf:1203`:
`single_nat_gateway` → 1; `one_nat_gateway_per_az` → `length(var.azs)`;
default → `max_subnet_length` (lines 10-16; leaves out intra and outpost).
Index i ties NAT gateway i to public subnet i and private route table i;
`single_nat_gateway` pins all of them to 0 (lines 351, 1233-1240). The
default mode can create more NAT gateways than expected, and they bill
hourly.

**Q4. More AZs than subnets, or the reverse?** `element()` wraps around,
so mismatched lists silently reuse earlier entries. An empty list errors.

**Q5. Why the regex on availability_zone?** `^[a-z]+-` tells a zone name
(`us-east-1a`) from a zone ID (`use1-az1`); the module sets
`availability_zone` or `availability_zone_id` and leaves the other null
(`main.tf:151-152`). Zone IDs are stable across AWS accounts; names are not.

**Q6. Tiers.** Seven fixed tiers (public, private, database, redshift,
elasticache, intra, outpost), each a copy-pasted block with no `for_each`
over tier names. One tier (redshift) takes 21 variables, 8 resources,
11 outputs, 21 wrapper references, plus locals and a hard-coded map
(`main.tf:81-88`). The copies have drifted apart: `tags_per_az` only on
public and private; `lower()` only on database and redshift; a stray comma
in the database `format()`. Adding a tier means 60+ hand edits across four
or more files.

## Patterns to copy

- Accept both AZ names and AZ IDs.
- Fall back to a shared route table when a tier doesn't need its own.

## Patterns to avoid

- Callers hand-compute CIDRs with fixed offsets; nothing checks overlap.
- Fixed tiers written as duplicated code blocks.
- `element()` silently wrapping when list lengths differ.
- The `one_nat_gateway_per_az` guard (`main.tf:146`): too few public
  subnets → zero public subnets created → NAT `element()` on an empty
  list → a confusing plan error far from the real mistake. (Reasoned from
  the code, not yet run; confirm in M5.)
- Splitting `locals` across several blocks: `nat_gateway_count` lives at
  line 1203, not in the top block. Grep for definitions; don't assume.
- Network ACL defaults that allow all traffic (`0.0.0.0/0`, protocol -1),
  leaving the real filtering to security groups. Revisit in M3.

## Decisions this forces for ipam.py (M2)

- **Tiers are data, not code.** Generators loop over whatever tiers the
  YAML lists. Goal: adding a tier is a one-line YAML change.
- **Mixed sizes** (/24, /23, /26) need alignment-aware packing, largest
  first.
- **Subtract 5 reserved addresses** per subnet when checking usable hosts.
- **Detect overlap before Terraform.** First test case: the 5-AZ collision
  above.
- **Validate the whole YAML up front**, with errors in the user's terms.
- **Zones:** list zone names or IDs in the YAML, or emit the AWS data
  source and resolve at plan time. Decide in architect mode.

## Aider setup lessons

- Use a current model. `~/.aider.conf.yml`:
  `model: openrouter/anthropic/claude-sonnet-5.5`,
  `weak-model: openrouter/anthropic/claude-haiku-5.5` (confirmed on OpenRouter),
  `edit-format: diff`.
- `/model` switches mid-session but ignores the config file; aider fell
  back to "whole" edit format for the unrecognized model. Restart with
  flags and confirm the prompt shows `diff>`.
- Cost: map only ~4k tokens ($0.01) per ask; three files loaded ~33k
  tokens ($0.08-0.09). `/drop` files when done with them.
- Session total: about $0.53 across GPT-4o and Sonnet 5.5.
