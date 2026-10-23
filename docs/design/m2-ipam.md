# M2 design: ipam.py subnet allocator

Status: agreed Oct 23, 2026. Input for aider architect mode.
Background and reasons: `docs/recon/terraform-aws-vpc.md`.

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

Load with `yaml.safe_load`, never `yaml.load`.

## Validation

Collect **every** error before raising; never stop at the first. Each
message names the YAML location and says what to change, e.g.
`tiers[1] (private): hosts 5000 needs a /19, larger than the VPC /20`.

- `vpc.cidr`: a string; a valid IPv4 network with host bits zero
  (`10.0.0.1/16` is an error that suggests `10.0.0.0/16`); prefix
  between /16 and /28 (AWS VPC limits).
- `vpc.azs`: a non-empty list of unique, non-empty strings.
- `tiers`: a non-empty list; each `name` is a unique, non-empty string.
- Each tier has **exactly one** of `prefix` or `hosts`.
  - `prefix`: an int from 16 to 28 (AWS subnet limits), and not smaller
    than the VPC prefix.
  - `hosts`: an int ≥ 1. Resolve to the largest prefix (smallest subnet)
    `p` with `2**(32 - p) - 5 >= hosts`, then clamp to at most 28
    (AWS's minimum subnet is /28). Error if the result is smaller than
    16 or than the VPC prefix.
  - Reject `bool` where an int is expected (`True` is an int in Python).
- Unknown keys anywhere are errors (catches typos like `prefx`).
- Capacity: `len(azs) * sum(2**(32 - p) for each tier) <= 2**(32 - vpc_prefix)`.
  On failure, report needed vs. available addresses.

AWS reserves 5 addresses in every subnet (network, +1 router, +2 DNS,
+3 reserved, broadcast), so usable hosts = `2**(32 - p) - 5`.

## Algorithm

1. Expand to one request per (tier, AZ).
2. Sort by prefix ascending (largest subnet first); break ties by the
   tier's position in the YAML, then the AZ's position. This makes the
   output deterministic.
3. Place requests end to end from the VPC network address.

Because every size is a power of two and larger blocks come first, each
next address is already aligned for the next block: no padding, no
gaps, and it fits if and only if the capacity check passes.

## Interface

Standard library `ipaddress` only, plus PyYAML. Python 3.10+.

```python
class ConfigError(Exception):
    errors: list[str]           # all problems found

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

Output is keyed by `(tier, az)`, never by list position. Later, stability
can be added as `allocate(config, existing=None)` without changing callers.

## Tests

The tests must check results with their own logic (e.g. pairwise
`IPv4Network.overlaps`), not by calling helpers from `ipam.py`.

Example-based:

- The README-style config above allocates as expected, with exact CIDRs.
- **M1 regression:** a /16 with 5 AZs and three /24 tiers gives 15
  distinct CIDRs; `10.0.4.0/24` appears exactly once.
- Mixed sizes /23, /24 and /26 all come out aligned.
- `hosts: 400` → /23 (507 usable); `hosts: 1` → /28.
- A config with several mistakes reports all of them in one `ConfigError`.
- Over capacity by one block fails; exactly full succeeds.

Hypothesis properties, over generated valid configs (VPC /16–/24,
1–6 AZs, 1–7 tiers, tier prefixes from the VPC prefix to 28):

- Allocation succeeds **if and only if** the capacity check passes.
- When it succeeds:
  - no two allocations overlap;
  - every allocation is inside the VPC;
  - every allocation is aligned (its network address is a multiple of
    its size);
  - every (tier, AZ) gets exactly one allocation with the tier's prefix;
  - `usable_hosts == size - 5`;
  - running `allocate` twice gives identical results.

## Files

- `cidrwright/__init__.py`
- `cidrwright/ipam.py`
- `tests/test_ipam.py`
