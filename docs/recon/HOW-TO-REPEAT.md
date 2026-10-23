# How to repeat the M1 recon

This guide lets someone with no prior context repeat CIDRwright's
milestone M1: reading the `terraform-aws-vpc` Terraform module with the
AI coding tool aider, then checking every answer against the code. The
findings are in [terraform-aws-vpc.md](terraform-aws-vpc.md).

Time: about 1–2 hours. Cost: well under $1 in API fees.

## What you will and won't reproduce

- **Reproducible:** the code (pinned to one commit), the commands, the
  questions, and the checks. The answer key below stays valid because the
  code can't change under you.
- **Not reproducible:** aider's exact wording. Model answers vary from run
  to run and between model versions. Judge each answer by whether it
  passes the checks, not by whether it matches ours word for word.

## 1. Prerequisites

| Need | Version used | Notes |
| --- | --- | --- |
| git | any recent | |
| Python | 3.10+ | aider is a Python tool |
| aider | 0.86.2 | See "Installing aider" below |
| OpenRouter account and API key | — | openrouter.ai; add a few dollars of credit |

### Installing aider

The original run used a plain pip install:

```bash
python -m pip install aider-chat
```

This puts aider and its many pinned dependencies into whichever Python
environment `python` points to, so it can clash with other packages there.
Aider's own recommended installer avoids that by giving aider an isolated
environment (it uses `uv` and installs Python 3.12 if needed):

```bash
python -m pip install aider-install
aider-install
```

Either works for this guide. Confirm with `aider --version`.

Make the key available to aider:

```bash
export OPENROUTER_API_KEY=sk-or-...   # add to ~/.zshrc or ~/.bashrc to keep it
```

Never commit this key or paste it into a chat.

## 2. Configure aider

Create `~/.aider.conf.yml`:

```yaml
model: openrouter/anthropic/claude-sonnet-5.5
weak-model: openrouter/anthropic/claude-haiku-5.5
edit-format: diff
map-tokens: 2048
```

- **model** answers your questions. Use a current frontier model; a 2024
  model (GPT-4o) gave noticeably worse answers in our run.
- **weak-model** writes commit messages and summaries. Both model
  names were confirmed on openrouter.ai/models in Oct 2026; any small,
  cheap model works here.
- **edit-format: diff** must be set explicitly. Aider 0.86.2 doesn't
  recognize newer models and otherwise falls back to "whole" format.
- **map-tokens: 2048** sets the size of the repo map. Keep it the same
  so your map is comparable to ours.

## 3. Get the code, pinned

Clone it **outside** any project of your own, so its files never mix
with yours:

```bash
mkdir -p ~/projects/recon && cd ~/projects/recon
git clone https://github.com/terraform-aws-modules/terraform-aws-vpc.git
cd terraform-aws-vpc
git checkout b3abd6d    # v6.7.3, Sept 18 2026; all line numbers refer to this
```

## 4. Start aider in read-only habits

```bash
aider --no-auto-commits
```

Check the startup lines:

- `Main model: openrouter/anthropic/claude-sonnet-5.5 with diff edit format`
- The prompt reads `diff>`.

If it shows a different model, `whole edit format`, or a map size other
than 2048, the config wasn't picked up. Aider reads `.aider.conf.yml` from
your home folder, then the repo root, then the current folder (later ones
win), and also reads `AIDER_*` environment variables and `.env` files. To
find a stray setting:

```bash
env | grep -i aider
grep -i model ~/.aider.conf.yml .aider.conf.yml ~/.env .env 2>/dev/null
```

In the original run, an older `~/.aider.conf.yml` still named GPT-4o;
editing its `model:` lines fixed it.

Rules for the whole session:

- **Never use `/add`.** It makes files editable. Use `/read-only` instead.
- When aider asks **"Add file to the chat?"**, answer **N** or **D**
  (don't ask again). "Yes" adds the file as editable.
- Don't use `/model` to switch models mid-session: it ignores your config
  file. Restart aider instead.

## 5. Procedure

Run each step and paste aider's output into a scratch file as you go.

### Step A: look at the map

```
/map
```

Record: Are `resource` and `variable` blocks shown (HCL parsed)? Which
files made it in? What important files are missing? Remember that files
are listed alphabetically; rank shows only in what survives the budget.

### Step B: ask with the map only

```
/ask How does this module compute subnet CIDRs per availability zone?
/ask Then where do the CIDRs in examples/complete come from?
```

Record whether answers name specific files, lines and values, or speak in
generalities ("typically", "often").

### Step C: load the files and ask again

```
/read-only main.tf variables.tf examples/complete/main.tf
/map
/ask How does this module compute subnet CIDRs per AZ? Quote the exact lines and give line numbers.
/ask Where do the CIDRs in examples/complete come from? Quote the exact lines.
/ask How does this module decide how many NAT gateways to create? Explain single_nat_gateway and one_nat_gateway_per_az, and quote the expressions that implement them.
/ask What happens if I pass 3 AZs but only 2 public subnets? Which subnet goes in which AZ?
/ask Why does the availability_zone line use a regex?
/ask What subnet tiers does this module support, and what would it take to add a new tier? List every resource and variable a new tier would need.
```

Compare the second `/map` with the first: the loaded files should drop out.

Note: aider sends files to the model **without line numbers**, so a model
cannot know them. Asking for line numbers is a test of honesty, not
accuracy: a good answer says it can't give them. Find the lines yourself
in step 6.

### Step D (optional): compare models

Repeat Step C with an older or cheaper model (restart aider with
`--model openrouter/openai/gpt-4o-2024-08-06`) and compare.

## 6. Verify every answer

In a second terminal in the same folder, check each claim. A claim passes
only if the code says it.

| Question | Check | What the code says |
| --- | --- | --- |
| Q1 module CIDRs | `grep -n "cidr_block *= .*public_subnets" main.tf` | Line 153: `element(concat(var.public_subnets, [""]), count.index)`. The module **computes nothing** for IPv4; it picks the nth CIDR the caller passed. `grep -n cidrsubnet main.tf` shows only IPv6 uses. |
| Q2 example CIDRs | `grep -n "cidrsubnet\|vpc_cidr =" examples/complete/main.tf` | Lines 32–37: `cidrsubnet(local.vpc_cidr, 8, k + 4)` etc.; line 11: `vpc_cidr = "10.0.0.0/16"`. The second argument (8) is **newbits**, bits added to the prefix: /16 + 8 = /24. It is not the prefix length. |
| Q2 collision | `python3 -c "import ipaddress as i; s=list(i.ip_network('10.0.0.0/16').subnets(new_prefix=24)); print(s[4])"` | With 5 AZs, private index 4 and public index 0+4 are both `10.0.4.0/24`. Nothing in Terraform catches this before AWS does. |
| Q3 NAT count | `grep -n "nat_gateway_count *=" main.tf` | Line 1203: single → 1; per-AZ → `length(var.azs)`; default → `local.max_subnet_length` (lines 10–16, excludes intra and outpost). Note it's **not** in the first `locals` block. |
| Q3 placement | `grep -n "single_nat_gateway ? 0 : count.index" main.tf` | Lines 351, 1233–1240: with `single_nat_gateway`, everything uses index 0. |
| Q3/Q4 guard | `sed -n 146p main.tf` | `one_nat_gateway_per_az` with fewer public subnets than AZs creates **zero** public subnets. |
| Q4 wraparound | (Terraform docs for `element`) | `element()` wraps around, so short lists silently reuse earlier entries; an empty list errors. |
| Q5 regex | `sed -n 151,152p main.tf` | `^[a-z]+-` matches zone names (`us-east-1a`) but not zone IDs (`use1-az1`); the module sets one field or the other. |
| Q6 tiers | `grep -c '^variable ".*redshift' variables.tf` and `grep -n '^resource "[^"]*" "[^"]*redshift' main.tf` | 7 fixed tiers, each copy-pasted. Redshift alone: 21 variables, 8 resources; `grep -c '^output "redshift' outputs.tf` gives 11 outputs. |

For each question, record:

1. Did the answer pass the check?
2. If not, what kind of miss was it: generic (no specifics), substitution
   (answered a nearby question), terminology error, or omission?
3. Tokens and cost, from the line aider prints after each answer.

## 7. Done when

- All six questions are asked and checked against the table above.
- You've recorded at least one place where aider was wrong, vague, or
  needed a push.
- You can explain, without notes, why `cidrsubnet` with fixed index
  offsets can't handle mixed subnet sizes like /24, /23 and /26 in one
  network.
