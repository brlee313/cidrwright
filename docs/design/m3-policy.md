# M3 spec: network model and policy compiler

> Status: accepted (Nov 2, 2026). GitHub Milestone "M3": Part A,
> network model (#12); Part B, policy compiler (#11). ADRs: 0006
> (symbolic endpoints) and 0007 (least-privilege egress), both added in
> Part B's PR.
>
> History. Rev 2: input shape follows M2's real YAML (`vpc: {cidr,
> azs}`, tiers as a list); new `model.py` owns the whole file; `public`
> is a tier attribute stripped before IPAM; errors follow M2's
> conventions; YAML loader moves to a shared module. Rev 3 (review): P-23
> confirmed; any port-range overlap is an error (P-43, P-51); M3 split
> into Part A and Part B. Rev 4 (Nov 3): `proto` is required (no
> default), so every entry states its protocol explicitly. The §3
> example is now a complete working network (DNS over UDP and TCP via
> the proxy) and says in comments what it leaves out and why (§3.1);
> how DNS is governed (proxy resolver vs the cloud's built-in resolver)
> is deferred to M4. Clarified at Part A plan review (Nov 3): M-02
> boolean check and the `model`/`ipam` error-merge order (§6).
> Rev 5 (Nov 16, Part B plan review): IR endpoint `Tier` renamed
> `TierRef`; `ConfigError` and `describe` move to `errors.py`; open
> points A1–A12 from the architect plan settled in §4.3, §5.1 and §10.

## 1. Purpose and scope

Four modules (`errors.py` added in rev 5):

- **`cidrwright/errors.py`** (new, Part B): `ConfigError` and
  `describe()`, moved out of `ipam.py` so `policy.py` can raise
  `ConfigError` without importing `ipam` (ADR 0006). `ipam.ConfigError`
  stays importable (re-export).
- **`cidrwright/yamlio.py`** (new): the duplicate-key-rejecting YAML
  loader, moved out of `ipam.py` so `ipam.py` and `model.py` share it.
- **`cidrwright/model.py`** (new): loads `network.yaml`, owns its
  top-level keys and the tier `public` attribute, and hands each section
  to the module that owns it.
- **`cidrwright/policy.py`** (new): owns the policy endpoint words,
  validates the `policy:` section and compiles it into a cloud-neutral
  rule list (the **IR**, intermediate representation).

Emitters (AWS in M4, Azure in M6) turn the IR into security groups or
NSGs.

Changes to `ipam.py`: **one pure move** (§8), its own commit, listed
separately in the PR. No behavior change; M2's tests pass unchanged.

### 1.1 Two parts, one milestone

| | Part A: network model (#12) | Part B: policy compiler (#11) |
| --- | --- | --- |
| Modules | `yamlio.py` (move), `model.py`, `policy.py` with only `RESERVED_ENDPOINTS` and `check_tier_names` | rest of `policy.py`: validation, IR, compile |
| `Network` | `config`, `public`, `vpn`, `policy_raw` (the `policy:` value, unchecked) | `policy_raw` replaced by `rules: tuple[Rule, ...]`; `model.py` calls `policy` validation/compile |
| Rules | M-01…M-03, P-01 | P-02 and up |
| Docs | this spec | ADRs 0006, 0007 |
| Branch | `m3-network-model` off `main` | `m3-policy-compiler`, rebased on `main` after Part A merges |

Why split: Part B is the like-for-like comparison with M2 (the
estimation calibration point). Part A is new scope found while checking
M2's code; its own issue keeps its time and cost separate.

Out of scope (and where it goes):
- Security groups, Terraform, CIDRs for endpoints: M4 AWS emitter.
- AZ-key → zone name/ID mapping: M4's first ADR.
- Route tables and internet gateways (what makes a tier public on AWS):
  M4. M3 only records the `public` flag.
- `vpn:` section contents (type, client pool, peers): M4. M3 checks only
  that the section is a mapping.
- IPv6: not supported (§2.4). Revisit when IPv6 subnets are added.
- Deny rules: not supported. Revisit if the grammar ever gains a broad
  selector (CIDR blocks, wildcards, tags).
- AWS service endpoints (`Service("s3")`): M4 candidate.

## 2. Frame and named rules

### 2.1 SD3+C

| Principle | In this milestone |
| --- | --- |
| Secure by Design | Explicit grants (§2.2); cloud-neutral IR (ADR 0006); each rule lives in the module that owns its reason |
| Secure by Default | no wildcards, no `::/0`, private tiers never paired with `internet`, no default egress (ADR 0007), tiers private unless marked public, defaults only where they fail closed |
| Secure in Deployment | M4/M5: checkov in CI, hand review of rules before apply, budget alarm |
| Communications | every error names the location and the fix; this spec and the ADRs |

### 2.2 Explicit grants

Every allowed (source, destination, protocol, port/ICMP match) must
trace to a policy entry that names both endpoints. No access may widen
without a change to a policy entry.

### 2.3 One grant, one line

Each allowed (source, destination, protocol, port/ICMP code) comes from
exactly one policy entry, and from one item within it. Deleting that
entry removes the access. Enforced by P-43/P-45 (within an entry) and
P-50/P-51 (across entries): duplicates, containment and partial
overlaps are all errors.

### 2.4 Defaults must fail closed

A default is allowed only if getting it wrong blocks traffic rather
than granting it. The only default is tier `public` = `false`. `proto`
has no default: every policy entry must state it (rev 4).
IPv4 only: `internet` means `0.0.0.0/0`; no emitter may emit `::/0`.

## 3. Input

```yaml
# A small three-tier web app: internet -> web -> app -> db, admin access
# over WireGuard, and all outbound traffic from private tiers through a
# public proxy that also resolves DNS.
#
# Not shown here, by design (each is someone else's job):
# - Replies need no rules: AWS security groups are stateful.
# - The WireGuard host's own port (UDP 51820) is set up from vpn:, not by
#   a policy entry (M4).
# - What makes a tier "public" on AWS (internet gateway route, public IPs)
#   is M4's.
# - DNS governance is NOT decided yet (M4 decides, before the AWS emitter
#   design). Entries 4-7 show one option: the proxy is the resolver. The
#   other: keep the cloud's built-in resolver and filter it by domain
#   name (AWS: Route 53 Resolver DNS Firewall). Either way, every cloud's
#   built-in resolver bypasses ordinary firewall rules by default
#   (AWS VPC+2, Azure 168.63.129.16, GCP metadata server), so until M4
#   decides, this example does not guarantee DNS goes through the proxy.
# - Tiers with no outbound rule (web, db) can't start connections to
#   anything not listed (e.g. no OS updates). Intended here; add entries
#   (e.g. db -> proxy) if they need them. They can still look up names
#   through the cloud's built-in resolver (see the DNS note).
vpc:
  cidr: 10.20.0.0/16
  azs: [a, b]
tiers:
  - {name: web,   prefix: 24, public: true}   # load balancers / reverse proxies
  - {name: app,   prefix: 23}
  - {name: db,    prefix: 26}
  - {name: proxy, prefix: 28, public: true}   # forward proxy + DNS resolver
vpn:
  type: wireguard              # contents validated in M4
  client_pool: 10.99.0.0/24
  peers: [bruce-laptop, bruce-phone]
policy:
  - action: allow              # 0: public HTTPS
    from: internet
    to: web
    proto: tcp
    ports: [443]
  - action: allow              # 1: web forwards to the app
    from: web
    to: app
    proto: tcp
    ports: [8080]
  - action: allow              # 2: app talks to the database
    from: app
    to: db
    proto: tcp
    ports: [5432]
  - action: allow              # 3: admin SSH over the VPN
    from: vpn
    to: [web, app, db]
    proto: tcp
    ports: [22]
  - action: allow              # 4: app -> proxy: DNS over TCP, HTTP(S) proxy
    from: app
    to: proxy
    proto: tcp
    ports: [53, 3128]
  - action: allow              # 5: app -> proxy: DNS over UDP
    from: app
    to: proxy
    proto: udp
    ports: [53]
  - action: allow              # 6: proxy -> internet: upstream DNS (TCP), HTTPS
    from: proxy
    to: internet
    proto: tcp
    ports: [53, 443]           # HTTPS only: plain-HTTP (80) sites are unreachable on purpose
  - action: allow              # 7: proxy -> internet: upstream DNS (UDP)
    from: proxy
    to: internet
    proto: udp
    ports: [53]
  - action: allow              # 8: ping and path-MTU discovery to the app, for troubleshooting
    from: vpn
    to: app
    proto: icmp
    icmp: [{type: 8}, {type: 3, code: 4}]
```

### 3.1 Rule for examples

Every example in this spec and in later docs is either a complete,
working configuration, or says in comments what it leaves out and why.
A reader must never have to guess whether a missing rule is implied:
under Explicit grants, nothing is implied.

Top level (owned by `model.py`):

| Key | Required | Owner |
| --- | --- | --- |
| `vpc` | yes | `ipam.py` (unchanged) |
| `tiers` | yes | `ipam.py` for `name`/`prefix`/`hosts`; `model.py` for `public` |
| `vpn` | no | `model.py` checks it is a mapping; contents M4 |
| `policy` | no (absent = no rules) | `policy.py` |

Tier `public`: optional, `true` or `false`, default `false`.

Policy entry fields (each entry is a mapping; no other keys allowed):

| Key | Required | Type | Meaning |
| --- | --- | --- | --- |
| `action` | yes | `"allow"` | Only `allow`. |
| `from` | yes | endpoint, or list of endpoints | Source(s) |
| `to` | yes | endpoint, or list of endpoints | Destination(s). At most one of `from`/`to` may be a list. |
| `proto` | yes | `tcp` \| `udp` \| `icmp` | Protocol |
| `ports` | yes for tcp/udp; forbidden for icmp | list of port items | A port item is an integer, or `{start, end}` |
| `icmp` | yes for icmp; forbidden for tcp/udp | list of `{type, code?}` | `code` omitted = all codes of that type |

Endpoints: a tier name, `internet`, or `vpn`.

Constants (in code, not configurable from YAML):
- `MAX_PORT_SPAN = 1024` (`end - start + 1 <= 1024`).
- `RESERVED_ENDPOINTS = ("internet", "vpn", "*")`, defined in
  `policy.py` (the module that owns the reason).

## 4. Output and API

### 4.1 The IR (`policy.py`, Part B)

Proposed frozen dataclasses (names confirmed in the architect step):

```python
Endpoint = TierRef | Internet | Vpn       # TierRef: not ipam.Tier

@dataclass(frozen=True)
class TierRef:
    name: str

@dataclass(frozen=True)
class Internet: ...

@dataclass(frozen=True)
class Vpn: ...

@dataclass(frozen=True)
class PortRange:
    start: int        # 1..65535
    end: int          # start..65535; end - start + 1 <= MAX_PORT_SPAN

@dataclass(frozen=True)
class IcmpMatch:
    type: int         # 0..255
    code: int | None  # 0..255, or None = all codes of this type

@dataclass(frozen=True)
class Rule:
    src: Endpoint
    dst: Endpoint
    proto: str                 # "tcp" | "udp" | "icmp"
    match: PortRange | IcmpMatch
    entry: int                 # index into policy: (traceability)
```

Name: `TierRef` (rev 5), because `ipam.Tier` already exists and both
are frozen dataclasses with a `name: str` field, so a bare
`from … import Tier` could pick the wrong one without a type error.
The IR holds a *reference* to a tier, not a definition.

Compilation:
- One `Rule` per (src, dst, port item) or (src, dst, ICMP item). A
  single port `22` becomes `PortRange(22, 22)`.
- Deterministic order: entry index, then the list side's order, then
  `ports`/`icmp` item order.
- No wildcard, no egress/ingress split. Deriving src-egress + dst-ingress
  is the AWS emitter's job (ADR 0007).

### 4.2 `policy.py` API

`policy.py` does not read files or know about `vpc`. It gets what it
needs as plain values.

Part A:

```python
RESERVED_ENDPOINTS: tuple[str, ...]
def check_tier_names(names: Iterable[tuple[int, str]]) -> list[str]
                                                   # reserved-word errors
```

Part B adds:

```python
def validate_policy(raw_policy: object, tiers: Mapping[str, bool],
                    has_vpn: bool) -> list[str]        # error strings
def compile_policy(raw_policy: object, tiers: Mapping[str, bool],
                   has_vpn: bool) -> tuple[Rule, ...]  # raises ConfigError
```

`tiers` maps tier name → public. `compile_policy` validates first (same
pattern as `allocate`'s re-check) and raises `ConfigError` (from
`errors.py`) if anything is wrong. `model.py` calls only
`compile_policy` (one validation pass, one code path).

### 4.3 `model.py` API

```python
@dataclass(frozen=True)
class Network:
    config: ipam.Config               # from ipam.validate, unchanged
    public: frozenset[str]            # names of public tiers
    vpn: Mapping[str, object] | None  # raw; validated in M4
    policy_raw: object                # Part A only; Part B: rules
    # Part B: rules: tuple[policy.Rule, ...]

def validate_network(data: object) -> Network   # raises ConfigError
def load_network(path) -> Network               # yamlio loader + validate_network
```

`validate_network` steps:
1. Top-level shape and keys (`vpc`, `tiers`, `vpn`, `policy`).
2. Per tier: validate and remove `public`; reserved-word check via
   `policy.check_tier_names`.
3. Call `ipam.validate({"vpc": ..., "tiers": <tiers without public>})`;
   collect its `ConfigError.errors`. Tier indexes stay the same, so
   ipam's `tiers[i] (name):` labels still point at the right YAML entry.
4. `vpn` is a mapping, if present.
5. (Part B) Policy validation, only if steps 1–4 found no tier-related
   errors (otherwise endpoint checks would report noise such as "unknown
   endpoint" for a tier whose definition is broken). Rev 5 definition:
   `tiers` is present and a list, no `ipam` error falls in the `tiers`
   or `tiers[i]` buckets, and there are no P-01 or M-02 errors. `vpc`
   errors, the capacity error (`config:`) and unknown top-level keys do
   **not** block policy checks (policy needs only tier names and
   `public`). Inputs: `tiers = {name: public}`; `has_vpn = "vpn" in
   data`, even if `vpn` is invalid or `{}` (M-03 already reports a bad
   `vpn`, and the file is rejected anyway, so nothing fails open).
6. Raise one `ConfigError` with all errors, or return `Network`.

`ipam.load_config` stays as it is, for IPAM-only files.

## 5. Validation rules

IDs are for the spec and tests to refer to; they do not appear in
messages. Messages start with a path (`policy[3].to[1]:`), like M2.

**Model (M-…), in `model.py` (Part A):**

| ID | Rule | Example message (sketch) |
| --- | --- | --- |
| M-01 | Config must be a mapping; unknown top-level key; missing `vpc`/`tiers` (same wording style as M2). | `config: unknown key 'polcy'` |
| M-02 | Tier `public` must be a boolean (`isinstance(v, bool)`, so `1` and `0` are rejected). No quoting hint: YAML 1.1 already reads unquoted `yes`/`no`/`on`/`off` as booleans, so only quoted strings or other types reach this error. | `tiers[1] (app): public must be true or false, got string 'yes'` (from `public: "yes"`) |
| M-03 | `vpn` must be a mapping if present. | `vpn: must be a mapping, got a list` |

**Phase 1, policy config-level:**

| ID | Part | Rule | Example message (sketch) |
| --- | --- | --- | --- |
| P-01 | A | A tier may not be named a reserved word (`internet`, `vpn`, `*`). Called by `model.py` via `check_tier_names`. Note: M2's name regex already rejects `*`. | `tiers[0] (internet): 'internet' is a reserved policy endpoint; rename the tier (e.g. 'edge')` |
| P-02 | B | `policy` must be a list. `policy:` with no value (null) is an error; `policy: []` is valid (no rules); no `policy` key means no rules. | `policy: must be a list of entries, got nothing (null)` |

**Phase 2, per entry (Part B; first error per entry; all entries checked):**

| ID | Rule | Example message (sketch) |
| --- | --- | --- |
| P-10 | Entry must be a mapping. | `policy[3]: must be a mapping like {action: allow, from: web, to: app, proto: tcp, ports: [8080]}` |
| P-11 | Unknown key. | `policy[3]: unknown key 'port'; did you mean 'ports'?` |
| P-12 | `action` missing or not `allow`. | `policy[3]: missing 'action' (only 'allow' is supported)` / `policy[3].action: only 'allow' is supported` |
| P-13 | `from`/`to` missing. | `policy[3]: missing 'to'` |
| P-14 | `*` used as an endpoint (path `.to` for a single value, `.to[1]` inside a list). | `policy[3].to: '*' is not allowed; list tiers explicitly: [web, app, db, proxy]` |
| P-15 | Unknown endpoint name. The known list includes `vpn` only if there is a `vpn` key. | `policy[3].to[1]: unknown endpoint 'ap'; known: web, app, db, proxy, internet, vpn` |
| P-16 | `vpn` used but no `vpn:` section. | `policy[3].from: 'vpn' is used but no vpn: section is defined` |
| P-17 | Both `from` and `to` are lists. | `policy[3]: from and to are both lists; split into separate entries` |
| P-18 | Empty list in `from`/`to`. | `policy[3].to: empty list` |
| P-19 | Same endpoint twice in one list. | `policy[3].to[2]: 'web' is listed twice` |
| P-20 | Self-rule: same endpoint on both sides (includes `internet -> internet`). | `policy[3]: web -> web: traffic within a tier is not allowed; model the roles as separate tiers (e.g. db-primary -> db-replica)` |
| P-21 | `internet` as source with a private tier as destination. | `policy[3]: internet -> app: tier 'app' is not public (add public: true to the tier, or route through a public tier, e.g. internet -> web, web -> app)` |
| P-22 | A private tier as source with `internet` as destination. | `policy[3]: app -> internet: tier 'app' is not public; route outbound traffic through a public tier, e.g. app -> proxy, proxy -> internet` |
| P-23 | `internet` paired with `internet` or `vpn` (either direction). | `policy[3]: internet -> vpn: internet can only be paired with a public tier (VPN access goes through the WireGuard host, configured in vpn:)` |
| P-30 | `proto` missing, or not tcp/udp/icmp. | `policy[3]: missing 'proto' (one of tcp, udp, icmp)` / `policy[3].proto: 'tpc' is not one of tcp, udp, icmp` |
| P-31 | tcp/udp: `ports` missing or empty. | `policy[3]: missing 'ports' (required for tcp)` |
| P-32 | tcp/udp: `icmp` present. | `policy[3].icmp: only allowed with proto: icmp` |
| P-33 | icmp: `ports` present. | `policy[3].ports: not allowed with proto: icmp (ICMP has no ports)` |
| P-34 | icmp: `icmp` missing or empty. | `policy[3]: missing 'icmp' (required for proto: icmp; e.g. [{type: 8}])` |
| P-40 | Port, or a range's `start`/`end`, not an integer (booleans rejected), or outside 1–65535. A bad field value is reported at the field (`.ports[1].start`); a problem with the whole range (P-41 `start > end`, P-42) at the item (`.ports[1]`). | `policy[3].ports[0]: 70000 is outside 1-65535` |
| P-41 | Range: unknown key, missing `start`/`end`, `start > end`. | `policy[3].ports[1]: start 8099 is greater than end 8000` |
| P-42 | Range span > `MAX_PORT_SPAN`. | `policy[3].ports[1]: range 1-65535 covers 65535 ports; the limit is 1024` |
| P-43 | Two port items in one entry share any port (duplicate, containment or partial overlap). | `policy[3].ports[2]: 8050-8150 overlaps ports[1] (8000-8099) on 8050-8099; split so each port appears once` |
| P-44 | ICMP item: not a mapping, unknown key, missing `type`, type or code not an integer in 0–255 (booleans rejected). `code: null` is an error: omit `code` to mean all codes (null would widen the rule). | `policy[3].icmp[0].type: 300 is outside 0-255` / `policy[3].icmp[0].code: must be a number 0-255, got nothing (null); omit code to allow all codes` |
| P-45 | Same ICMP item twice, or `{type: t, code: c}` with `{type: t}` in the same entry. | `policy[3].icmp[1]: type 3 code 4 is already covered by icmp[0] (type 3, all codes)` |

P-23 rationale: `vpn` reaches the network through the WireGuard host,
not as a tier, so `internet <-> vpn` isn't a tier rule; a user writing
it would think it does something it doesn't. WireGuard's own UDP port
is M4's concern.

**Phase 3, cross-entry (Part B; runs only if every entry passed phase 2):**

| ID | Rule | Example message (sketch) |
| --- | --- | --- |
| P-50 | Two entries produce the same IR rule (same src, dst, proto, match). | `policy[3]: vpn -> web (tcp 22) duplicates policy[1]` |
| P-51 | Two entries' IR rules with the same src, dst and proto share any port (containment or partial overlap), or an ICMP `{type, code}` lies inside a `{type}` match. | `policy[4]: vpn -> web (tcp 8050-8150) overlaps policy[2] (tcp 8000-8099) on 8050-8099; split so each port is granted once` |

Overlap rule (P-43, P-51): ranges `[a1, b1]` and `[a2, b2]` overlap iff
`a1 <= b2 and a2 <= b1`. Adjacent ranges (8000–8049 and 8050–8150) do
not overlap and are allowed.

### 5.1 Check order and edge cases (rev 5)

**Order inside one entry** (decides which error is "first", §6 guard 1):
1. shape (P-10);
2. the entry's own keys: unknown keys (P-11), then missing `action`,
   `from`, `to`, `proto` (P-12, P-13, P-30), in that order;
3. values: `action` (P-12); sides (P-17, P-18); `from` items before `to`
   items, each item in list order (P-14, P-15, P-16, P-19); pairs (in list order; within each pair P-20, then P-21–P-23);
4. `proto` value (P-30), then `ports`/`icmp` presence (P-31–P-34);
5. `ports`/`icmp` items in list order (P-40–P-42, P-44), then overlaps
   within the entry (P-43, P-45).

This follows M2's rule that a mapping's own key problems come before
problems inside it.

**Wrong types** have no rule ID of their own: each is reported under
the rule that owns the key, in M2's wording (`… got a number`, via
`describe()`), never guessed or converted. Covers: `from`/`to` that is
a number, boolean, null or mapping, or a non-string list item (P-15
family); `action`/`proto` not a string (P-12/P-30); `ports`/`icmp` not a
list (P-31/P-34); a port item that is a string, float or boolean (P-40);
an ICMP item that is not a mapping (P-44). Booleans are never integers
here (M2's rule: `True` is rejected as a port or type).

**Repeated conflicts** (P-43, P-45, P-50, P-51): one message per
offending item (or later entry), naming the **earliest** item or entry
it conflicts with. Guard 1 applies in phase 3 too: at most one
cross-entry message per entry. Phase-3 messages come in order of the
later entry's index. ICMP wording for P-50/P-51:
`policy[4]: vpn -> app (icmp type 3 code 4) is already covered by policy[2] (icmp type 3, all codes)`.

## 6. Error reporting

Follows M2's conventions, plus noise guards for policy:

- One exception type: M2's `ConfigError(list[str])` (subclass of
  `ValueError`); `str()` gives one error per line. No new exception
  class.
- All errors are reported in one `ConfigError`, never stopping at the
  first.
- Order: document order (top-level keys in file order; within `policy`,
  entry index), a mapping's own key problems before problems inside it
  (M2's rule).
- **Noise guards:**
  1. **First error per policy entry.** Once an entry has an error, its
     remaining checks are skipped. All entries are still checked. Stops
     cascades such as `port:` typo → "missing ports". (Differs from M2,
     which reports every key's problem; M2 unchanged.)
  2. **Phases.** Policy checks run only if the tiers are valid (§4.3
     step 5); cross-entry checks run only if every entry is valid.
  3. **Deterministic.** Same input, same list, same order.
- **Merging `model.py`'s and `ipam`'s errors (Part A):** `ipam` errors are
  grouped by their leading path (`vpc`, `tiers[i]`, `config`; anything
  unmatched goes to a trailing bucket, so nothing is lost), then
  interleaved with `model.py`'s errors in file order. Within one tier:
  `ipam`'s errors first, then reserved name (P-01), then `public`
  (M-02). Missing top-level keys come first; the capacity error comes
  last. Verified Nov 3: `ipam`'s capacity message starts with `config:`
  and its vpc messages with `vpc` (`vpc.cidr`, `vpc.azs`, `vpc:`).
- Messages use the user's words (tier names, YAML keys, entry index),
  never Python types or IR class names.

## 7. Examples (expected IR, Part B)

From the §3 YAML (kept as `tests/data/spec-example.yaml` for the golden
test), `load_network(...).rules` is, in order:

```
Rule(Internet(),        TierRef("web"),    "tcp",  PortRange(443, 443),   entry=0)
Rule(TierRef("web"),    TierRef("app"),    "tcp",  PortRange(8080, 8080), entry=1)
Rule(TierRef("app"),    TierRef("db"),     "tcp",  PortRange(5432, 5432), entry=2)
Rule(Vpn(),             TierRef("web"),    "tcp",  PortRange(22, 22),     entry=3)
Rule(Vpn(),             TierRef("app"),    "tcp",  PortRange(22, 22),     entry=3)
Rule(Vpn(),             TierRef("db"),     "tcp",  PortRange(22, 22),     entry=3)
Rule(TierRef("app"),    TierRef("proxy"),  "tcp",  PortRange(53, 53),     entry=4)
Rule(TierRef("app"),    TierRef("proxy"),  "tcp",  PortRange(3128, 3128), entry=4)
Rule(TierRef("app"),    TierRef("proxy"),  "udp",  PortRange(53, 53),     entry=5)
Rule(TierRef("proxy"),  Internet(),        "tcp",  PortRange(53, 53),     entry=6)
Rule(TierRef("proxy"),  Internet(),        "tcp",  PortRange(443, 443),   entry=6)
Rule(TierRef("proxy"),  Internet(),        "udp",  PortRange(53, 53),     entry=7)
Rule(Vpn(),             TierRef("app"),    "icmp", IcmpMatch(8, None),    entry=8)
Rule(Vpn(),             TierRef("app"),    "icmp", IcmpMatch(3, 4),       entry=8)
```

14 rules: 1 + 1 + 1 + 3 + 2 + 1 + 2 + 1 + 2.

## 8. The `ipam.py` change (Part A; separate, reviewable on its own)

- Move `_UniqueKeyLoader` (and nothing else) from `ipam.py` to
  `cidrwright/yamlio.py`, as a public name (e.g. `UniqueKeyLoader`).
  `ipam.load_config` imports it from there.
- No behavior change. Proof: M2's load tests (duplicate keys, invalid
  YAML, UTF-8) pass unchanged, and `git diff` on `ipam.py` shows only
  the removed class and the new import.
- Its own commit (first code commit in Part A), listed separately in the
  PR description.

Part B (rev 5) makes one more pure move, also its own commit: `ConfigError`
and `_describe` go to `cidrwright/errors.py` (as `ConfigError` and
`describe`). `ipam.py` re-exports `ConfigError`, so `from cidrwright.ipam
import ConfigError` keeps working; `model.py` drops its copy of
`_describe`. Proof: all existing tests pass unchanged, and the diff shows
only removed code and new imports.

## 9. Test plan (per `docs/testing-guidelines.md`)

Part A:
- `yamlio` move: M2's existing load tests are the regression check; no
  new behavior.
- `model.py`: `public` stripped before IPAM (ipam errors still point at
  the right `tiers[i]`); `public` defaults to false; `public` accepts
  only true/false; unknown top-level key rejected; `vpn` must be a
  mapping; IPAM errors and model errors arrive in one `ConfigError` in
  document order; a valid file returns a `Network` whose `config` equals
  `ipam.validate` on the same file minus `public`.
- P-01: `internet` and `vpn` rejected as tier names with the right
  `tiers[i]` path; near-misses (`internets`, `vpn2`) accepted.
- Inputs: a `public: true` tier listed after private ones; tier names in
  non-alphabetical order.

Part B, example tests:
- One test per rule ID (P-02 and up), valid and invalid sides;
  boundaries on both sides (port 1 and 65535 accepted, 0 and 65536
  rejected; span 1024 accepted, 1025 rejected; ICMP 0 and 255 accepted,
  -1 and 256 rejected; adjacent ranges accepted, ranges sharing one port
  rejected).
- Error tests find the one message for the rule and assert its path
  prefix and a substring specific to that error **on the same message**,
  never on the joined text.
- Noise guards: two independent bad entries → one message each, in
  entry order; a `port:` typo → exactly one message for that entry; a
  broken tier → no policy messages; a malformed entry plus a duplicate
  pair → no P-50.
- Inputs that separate right from plausible-wrong rules: list items in
  non-alphabetical order; lists on the `from` side as well as the `to`
  side; ICMP with and without `code`; a public tier not named `web`;
  overlapping ranges given in either order; an entry with `ports` but
  no `proto` gives exactly one message (P-30), not a P-31 cascade.
- Compile tests check whole `Rule`s (src, dst, proto, match, entry).

Part B, properties (Hypothesis), valid networks built by construction:
- Every IR rule traces to its entry, and that entry names both endpoints.
- No two IR rules with the same src, dst and proto share a port or ICMP
  code.
- Rule count = Σ over entries of |from| × |to| × |ports or icmp items|.
- No rule pairs `Internet()` with a private tier or with `Vpn()`; no
  rule has src == dst.
- Compiling the same input twice gives equal tuples.
- Generators include rare inputs: ports 1 and 65535, spans of exactly
  1024, adjacent ranges, ICMP type 255, ICMP items with and without code.

Mutation checks: as in the guidelines, with a second, different test
for any mutation caught only once.

## 10. Decisions log (Nov 2, 2026)

The design questions behind this spec, with reasons, are summarized
here so the spec stands alone:

- **Q1** AZ-key → zone mapping is M4's (security groups are
  VPC-scoped; the policy names no zones).
- **Q2** Symbolic endpoints and a cloud-neutral IR (ADR 0006): keeps
  cloud choices out of the compiler, avoids CIDR sources (lowest common
  denominator), decouples rules from IPAM re-allocation.
- **Q3** IPv4 only; `internet` never paired with a private tier.
- **Q4** No `*` wildcard: it grows silently when tiers are added.
- **Q5** Redundancy is an error (it breaks deletion); no deny rules
  (nothing broad to trim; AWS SGs can't deny).
- **Q6** Least-privilege egress (ADR 0007); `internet` as destination
  only from a public tier (proxy pattern).
- **Q7** Structured YAML, not a string DSL; `proto` required (rev 4;
  was default tcp);
  `{start, end}` ranges capped at 1024 ports; ICMP by type and code;
  lists on one side only.
- **Q8** Self-rules, reserved tier names, `vpn` without a `vpn:`
  section, unknown keys and degenerate values are errors.
- **Review** P-23 kept; any port-range overlap is an error; M3 split
  into Part A (#12) and Part B (#11).
- **Rev 5 (Nov 16, Part B plan review, Bruce)** settled the architect
  plan's open points: A1 `errors.py` (keeps "policy does not import
  ipam" true; one `describe`; unblocks the loader dedupe); A2 `TierRef`;
  A3/A4 policy gating and `has_vpn` (§4.3 step 5); A5 `policy:` null is
  P-02, `[]` is valid; A6 check order (§5.1); A7 wrong types reported
  under the owning rule, booleans rejected, `code: null` an error
  (fails closed); A8 `internet -> internet` is P-20; A9 paths (§5
  P-14, P-15, P-40); A10 repeated conflicts (§5.1); A11 P-10/P-11
  sketches fixed; A12 `model` calls only `compile_policy`.
