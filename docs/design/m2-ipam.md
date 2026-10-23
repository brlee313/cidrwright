# M2 design: ipam.py subnet allocator

Status: revised Oct 23, 2026 after architect review. Input for aider
architect mode. Background and reasons: `docs/recon/terraform-aws-vpc.md`.

## Scope

`cidrwright/ipam.py` reads a YAML network description, validates all of
it, and returns one IPv4 CIDR per (tier, AZ), packed with no overlap and
no gaps. Tests in `tests/test_ipam.py` with pytest and hypothesis.

## Non-goals (M2)

- **Does not preserve existing allocations.** This is a greenfield
  planner: changing the YAML (adding an AZ, a tier, or resizing a tier)
  may move every subnet. Safe because nothing is deployed until M5.
  Stability (pinned/existing allocations) is a later milestone; the
  interface below leaves room for it.
- No AWS calls and no credentials. AZs are opaque keys; mapping them to
  zone names, zone IDs or a data source is the Terraform generator's job
  (M3).
- No Terraform output. No IPv6. No route tables, NAT or ACLs.
- No CI changes.

## Input YAML

```yaml
vpc:
  cidr: 10.0.0.0/16
  azs: [a, b, c]
tiers:
  - {name: public,   prefix: 24}
  - {name: private,  hosts: 400}
  - {name: database, prefix: 26}
```

Subnets are laid out by size (largest first), not in YAML order: in the
example above, `private` comes first in the address space. Say so in the
module docstring.

## Loading

- `load_config(path)` reads with a `yaml.SafeLoader` subclass that
  **rejects duplicate mapping keys** (PyYAML otherwise keeps the last
  value silently). Never use `yaml.load`.
- YAML syntax errors and duplicate keys become a `ConfigError` that names
  the file and line.
- A missing or unreadable file raises the normal `OSError`; don't wrap it.

## Validation

`validate(data)` collects **every** error, in document order, and raises
one `ConfigError` at the end. It never stops at the first problem.

### Message format

`<location>: <problem and what to change>`

- Locations: `vpc`, `vpc.cidr`, `vpc.azs`, `vpc.azs[2]`, `tiers`,
  `tiers[1]`, and `tiers[1] (private)` once the tier's name is valid.
  The top level is `config`.
- Example: `tiers[1] (private): hosts 5000 needs a /19, larger than the VPC /20`.
- When a YAML 1.1 bareword was turned into a bool or number (an AZ
  written as `no`, a name written as `on`), the message says to quote it.

### Rules

- **Structure.** The top level is a mapping with exactly the keys `vpc`
  and `tiers`; `vpc` has exactly `cidr` and `azs`; each tier has `name`
  and exactly one of `prefix` or `hosts`. Missing keys are errors.
  Unknown keys are errors, with a "did you mean ...?" hint when one is
  close (`difflib.get_close_matches`). An empty file gets its own
  message.
- **`vpc.cidr`**
  - A string in the form `a.b.c.d/nn` only. Netmask or hostmask forms
    (`10.0.0.0/255.255.0.0`) and bare addresses are errors that show
    the `/nn` form.
  - A valid IPv4 network with host bits zero. `10.0.0.1/16` is an error
    that suggests `10.0.0.0/16`.
  - Prefix between /16 and /28 (AWS VPC limits).
  - Must not overlap any range that can never be a VPC:
    `0.0.0.0/8` (this network), `127.0.0.0/8` (loopback),
    `169.254.0.0/16` (link-local), `224.0.0.0/4` (multicast),
    `240.0.0.0/4` (reserved). The message names the range and why.
    Public ranges are allowed (AWS permits them).
- **`vpc.azs`**: a non-empty list. Each item matches
  `^[a-z][a-z0-9_-]{0,63}$`. Duplicates are reported at the second
  occurrence.
- **`tiers`**: a non-empty list of mappings. Each `name` matches
  `^[a-z][a-z0-9_-]{0,31}$` and is unique.
- **`prefix`**: an int (not a `bool`), from 16 to 28 (AWS subnet
  limits), and not smaller than the VPC prefix. Skip the VPC comparison
  if the VPC is invalid.
- **`hosts`**: an int (not a `bool`), at least 1. Resolve to the
  largest prefix `p` with `2**(32 - p) - 5 >= hosts`, computed with
  integers only (`32 - (hosts + 4).bit_length()`), then clamp to at most
  28 (AWS's minimum subnet is /28). If the result is below 16 or below
  the VPC prefix, report one error using the stricter bound.
- **Capacity**: `len(azs) * sum(2**(32 - p) for each tier) <= 2**(32 - vpc_prefix)`.
  Check it only when the VPC, the AZs and every tier are valid;
  otherwise skip it rather than report a misleading number. On failure,
  report addresses needed vs. available.

AWS reserves 5 addresses in every subnet (network, +1 router, +2 DNS,
+3 reserved, broadcast), so usable hosts = `2**(32 - p) - 5`.

## Algorithm

1. Re-check capacity and that every tier prefix is at least the VPC
   prefix (a `Config` can be built without `validate`). Raise
   `ConfigError` if either fails.
2. Expand to one request per (tier, AZ).
3. Sort by prefix ascending (largest subnet first), then by the tier's
   YAML position, then the AZ's YAML position.
4. Place requests end to end from the VPC network address.

Because every size is a power of two and larger blocks come first, each
next address is already aligned for the next block: no padding, no
gaps, and it fits if and only if the capacity check passes.

Expected result for the example YAML:

| Tier | Prefix | Subnets (AZ a, b, c) |
| --- | --- | --- |
| private | /23 | 10.0.0.0/23, 10.0.2.0/23, 10.0.4.0/23 |
| public | /24 | 10.0.6.0/24, 10.0.7.0/24, 10.0.8.0/24 |
| database | /26 | 10.0.9.0/26, 10.0.9.64/26, 10.0.9.128/26 |

## Interface

Standard library `ipaddress` only, plus PyYAML. Python 3.10+.

```python
class ConfigError(ValueError):
    errors: list[str]           # all problems found; str() is one per line

@dataclass(frozen=True)
class Tier:
    name: str
    prefix: int                 # resolved, even if given as hosts

@dataclass(frozen=True)
class Config:
    vpc: ipaddress.IPv4Network
    azs: tuple[str, ...]
    tiers: tuple[Tier, ...]

@dataclass(frozen=True)
class Allocation:
    tier: str
    az: str
    network: ipaddress.IPv4Network
    usable_hosts: int

def load_config(path) -> Config: ...          # read file, then validate
def validate(data: object) -> Config: ...     # raises ConfigError
def allocate(config: Config) -> dict[tuple[str, str], Allocation]: ...
```

- The returned dict is keyed by `(tier, az)`, never by list position,
  and its insertion order is address order.
- Later, stability can be added as `allocate(config, existing=None)`
  without changing callers.
- `cidrwright/__init__.py` holds only `__version__ = "0.1.0"`.

## Tests

- Tests use only the public API and check results with their own logic
  (e.g. pairwise `IPv4Network.overlaps`), never helpers from `ipam.py`.
- Error tests assert on substrings (`"tiers[1] (private)"`, `"/19"`),
  not whole messages.
- `load_config` tests write YAML to pytest's `tmp_path`.

### Example-based

- The example YAML gives exactly the table above.
- **M1 regression:** a /16 with 5 AZs and three /24 tiers gives 15
  distinct CIDRs; `10.0.4.0/24` appears exactly once.
- Mixed /23, /24 and /26 tiers all come out aligned.
- `hosts: 400` → /23 (507 usable); `hosts: 1` → /28; `hosts: 11` → /28;
  `hosts: 12` → /27.
- One config with about six mistakes reports all of them in one
  `ConfigError`.
- Capacity: a /24 VPC with 4 AZs and one /26 tier (exactly full)
  succeeds; adding a /28 tier fails.
- Small cases: `True` as a prefix; a `prefx` typo; `10.0.0.1/16`
  suggests `10.0.0.0/16`; netmask form rejected; `224.0.0.0/16`
  rejected; duplicate YAML keys; an unquoted `no` AZ; an empty file;
  a name that breaks the pattern.

### Hypothesis

**Generator.** Build configs that fit by construction (choose sizes
within the remaining space) rather than generating at random and
filtering, which starves Hypothesis of examples. Keep a second, smaller
strategy that can overflow, for the capacity property. VPC: /16–/24,
not in the excluded ranges; 1–6 AZs; 1–7 tiers; some tiers given as
`hosts`. Feed dicts through `validate`, then `allocate`.

**Properties** of every fitting config:

- no two allocations overlap;
- every allocation is inside the VPC;
- every allocation is aligned (its network address is a multiple of
  its size);
- **no gaps:** in address order, the first allocation starts at the VPC
  network address and each one starts where the previous ended;
- **placement order:** in address order, the keys are sorted by
  (prefix, tier's YAML position, AZ's YAML position);
- every (tier, AZ) gets exactly one allocation;
- `usable_hosts == size - 5`.

**Capacity property** (overflow strategy): allocation fails with a
`ConfigError` mentioning capacity **if and only if** the test's own sum
exceeds the VPC size.

**`hosts` resolution** (one tier, one AZ, a /16 VPC, hosts from 1 to
65531): with `p` the resulting prefix, `usable(p) >= hosts`, and either
`p == 28` or `usable(p + 1) < hosts`. This checks the definition, not
the formula.

**Fuzz:** arbitrary nested data (`st.recursive` over None, bools, ints,
floats, strings, lists and dicts) passed to `validate` either returns a
`Config` or raises `ConfigError`, never any other exception.

## Stages

Implement in three stages. After each: run `pytest -q`, review the diff,
and commit it by hand before starting the next.

1. **Validation:** the data types, `ConfigError`, `validate`,
   `load_config`, and their example-based tests.
2. **Allocation:** `allocate` and its example-based tests.
3. **Properties:** all Hypothesis tests.

## Files

- `cidrwright/__init__.py`
- `cidrwright/ipam.py`
- `tests/test_ipam.py`
