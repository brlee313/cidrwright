"""Property tests for policy.compile_policy (M3 Part B, Stage 5; spec §9).

Inputs are valid by construction (no assume/filter):
- (src, dst) pairs come from `legal`, written from spec §5 (P-20 to P-23);
  a list side is built around one pivot, so every pair in from x to is legal.
- Ports: one cursor ("deck") per (src, dst, proto). Blocks are dealt after
  the highest cursor of every deck the entry covers (fan-out), with gap >= 0
  and length 1..1024. 64512-65535 is a reserved tail, used at most once per
  deck, so blocks can touch 65535 without exhausting the deck.
- ICMP: per deck, the bare types and (type, code) cards used; a new card
  is the next free one at or after a drawn start (wrapping).
- Items and entries are permuted after dealing, so ports are not ascending.

Expected values are computed from the raw input by definition. Constants
are the spec's literals (ports 1-65535, span 1024, ICMP 0-255), not
imported, so a mutated constant can't move the test with it.
"""

from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any

from hypothesis import example, given
from hypothesis import strategies as st

from cidrwright.policy import (
    IcmpMatch,
    Internet,
    PortRange,
    TierRef,
    Vpn,
    compile_policy,
    validate_policy,
)

Case = tuple[list[dict[str, Any]], dict[str, bool], bool]
Key = tuple[str, str, str]

# Near-misses of reserved words, short names; never a reserved word.
NAME_POOL = (
    "web", "app", "db", "proxy", "cache", "api",
    "edge", "internets", "vpn2", "a", "z9", "t-1",
)
TAIL_START = 64512  # 65536 - 1024
ICMP_TYPES = (0, 3, 8, 255)
ICMP_CODES = (0, 4, 255)


def legal(s: str, d: str, tiers: dict[str, bool]) -> bool:
    """Spec §5: no self-pair; internet only with a public tier; never internet<->vpn."""
    if s == d:
        return False
    if {s, d} == {"internet", "vpn"}:
        return False
    if s == "internet":
        return tiers.get(d, False)
    if d == "internet":
        return tiers.get(s, False)
    return True


def side(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def items_of(entry: dict[str, Any]) -> list[Any]:
    return entry["icmp"] if entry["proto"] == "icmp" else entry["ports"]


def endpoint(name: str) -> Any:
    if name == "internet":
        return Internet()
    if name == "vpn":
        return Vpn()
    return TierRef(name)


def match_of(proto: str, item: Any) -> Any:
    """The IR match an item means, from spec §3/§4.1 (not policy._to_match)."""
    if proto == "icmp":
        return IcmpMatch(item["type"], item.get("code"))
    if isinstance(item, int):
        return PortRange(item, item)
    return PortRange(item["start"], item["end"])


def cells(match: Any) -> set[tuple[Any, int]]:
    """Every port, or every (type, code), a match grants."""
    if isinstance(match, PortRange):
        return {("port", p) for p in range(match.start, match.end + 1)}
    if match.code is None:
        return {(match.type, c) for c in range(256)}
    return {(match.type, match.code)}


def deal_port(
    draw: st.DrawFn, keys: list[Key], cursor: dict[Key, int], tail_used: set[Key]
) -> Any:
    length = draw(st.one_of(st.just(1), st.just(1024), st.integers(1, 1024)))
    if draw(st.integers(0, 3)) == 0 and not any(k in tail_used for k in keys):
        start = 65536 - length  # touches 65535
        tail_used.update(keys)
    else:
        gap = draw(st.one_of(st.just(0), st.integers(0, 1500)))
        start = max(cursor[k] for k in keys) + gap
        for k in keys:
            cursor[k] = start + length
        assert start + length - 1 < TAIL_START  # budget invariant, not a filter
    end = start + length - 1
    if length == 1 and draw(st.booleans()):
        return start
    return {"start": start, "end": end}


def deal_icmp(
    draw: st.DrawFn,
    keys: list[Key],
    bare: dict[Key, set[int]],
    coded: dict[Key, set[tuple[int, int]]],
) -> dict[str, int]:
    t0 = draw(st.one_of(st.sampled_from(ICMP_TYPES), st.integers(0, 255)))
    if draw(st.booleans()):  # {type: t}: all codes
        for off in range(256):
            t = (t0 + off) % 256
            if all(t not in bare[k] and all(tc[0] != t for tc in coded[k]) for k in keys):
                for k in keys:
                    bare[k].add(t)
                return {"type": t}
    else:  # {type: t, code: c}
        c0 = draw(st.one_of(st.sampled_from(ICMP_CODES), st.integers(0, 255)))
        for off in range(256 * 256):
            t, c = divmod((t0 * 256 + c0 + off) % 65536, 256)
            if all(t not in bare[k] and (t, c) not in coded[k] for k in keys):
                for k in keys:
                    coded[k].add((t, c))
                return {"type": t, "code": c}
    raise AssertionError("ICMP deck exhausted")  # can't happen: <= 24 cards


@st.composite
def policies(draw: st.DrawFn) -> Case:
    names = draw(st.lists(st.sampled_from(NAME_POOL), min_size=2, max_size=6, unique=True))
    tiers = {n: draw(st.booleans()) for n in names}
    has_vpn = draw(st.booleans())
    endpoints = [*names, "internet", *(["vpn"] if has_vpn else [])]
    pairs = [(s, d) for s in endpoints for d in endpoints if legal(s, d, tiers)]
    srcs = [e for e in endpoints if any(s == e for s, _ in pairs)]
    dsts = [e for e in endpoints if any(d == e for _, d in pairs)]

    cursor: dict[Key, int] = defaultdict(lambda: 1)
    tail_used: set[Key] = set()
    bare: dict[Key, set[int]] = defaultdict(set)
    coded: dict[Key, set[tuple[int, int]]] = defaultdict(set)
    entries: list[dict[str, Any]] = []
    for _ in range(draw(st.integers(0, 6))):
        shape = draw(st.sampled_from(("one-one", "list-to", "list-from")))
        src_v: Any
        dst_v: Any
        if shape == "one-one":
            src_v, dst_v = draw(st.sampled_from(pairs))
        elif shape == "list-to":
            src_v = draw(st.sampled_from(srcs))
            partners = [d for s, d in pairs if s == src_v]
            dst_v = draw(st.lists(st.sampled_from(partners), min_size=1,
                                  max_size=len(partners), unique=True))
        else:
            dst_v = draw(st.sampled_from(dsts))
            partners = [s for s, d in pairs if d == dst_v]
            src_v = draw(st.lists(st.sampled_from(partners), min_size=1,
                                  max_size=len(partners), unique=True))
        proto = draw(st.sampled_from(("tcp", "udp", "icmp")))
        keys = [(s, d, proto) for s in side(src_v) for d in side(dst_v)]
        n = draw(st.integers(1, 4))
        if proto == "icmp":
            items: list[Any] = [deal_icmp(draw, keys, bare, coded) for _ in range(n)]
        else:
            items = [deal_port(draw, keys, cursor, tail_used) for _ in range(n)]
        items = draw(st.permutations(items))
        entries.append({
            "action": "allow", "from": src_v, "to": dst_v, "proto": proto,
            ("icmp" if proto == "icmp" else "ports"): items,
        })
    return draw(st.permutations(entries)), tiers, has_vpn


def _allow(src: Any, dst: Any, proto: str, **match: Any) -> dict[str, Any]:
    return {"action": "allow", "from": src, "to": dst, "proto": proto, **match}


_EDGE_PORTS = [65535, {"start": 8050, "end": 8150}, {"start": 8000, "end": 8049}, 1]
EXAMPLES: list[Case] = [
    (  # port edges, descending/adjacent items, same ports on tcp/udp and reversed pair
        [
            _allow("app", "db", "tcp", ports=_EDGE_PORTS),
            _allow("app", "db", "udp", ports=copy.deepcopy(_EDGE_PORTS)),
            _allow("db", "app", "tcp", ports=[{"start": 64512, "end": 65535}]),
            _allow("internet", "web", "tcp", ports=[443]),
            _allow(["web", "app"], "db", "tcp", ports=[5432]),
        ],
        {"db": False, "app": False, "web": True},
        False,
    ),
    (  # ICMP type 255, with and without code, list side, same type on another pair
        [
            _allow("vpn", ["app", "db"], "icmp",
                   icmp=[{"type": 255}, {"type": 3, "code": 4}, {"type": 3, "code": 0}]),
            _allow("app", "db", "icmp", icmp=[{"type": 3}]),
        ],
        {"db": False, "app": False},
        True,
    ),
    ([], {"web": True, "app": False}, False),
]


def pinned(test: Any) -> Any:
    for case in EXAMPLES:
        test = example(case)(test)
    return test


# ------------------------------------------------------------ properties


@given(policies())
@pinned
def test_prop_valid_input_accepted(case: Case) -> None:
    """P0: valid-by-construction input gives no errors and compiles."""
    raw, tiers, has_vpn = case
    assert validate_policy(raw, tiers, has_vpn) == []
    compile_policy(raw, tiers, has_vpn)


@given(policies())
@pinned
def test_prop_rule_traces_to_entry(case: Case) -> None:
    """P1 (§2.2): each rule's endpoints, proto and match come from its entry."""
    raw, tiers, has_vpn = case
    for r in compile_policy(raw, tiers, has_vpn):
        assert 0 <= r.entry < len(raw), r
        e = raw[r.entry]
        assert r.src in [endpoint(n) for n in side(e["from"])], r
        assert r.dst in [endpoint(n) for n in side(e["to"])], r
        assert r.proto == e["proto"], r
        assert r.match in [match_of(e["proto"], it) for it in items_of(e)], r
        if r.proto == "icmp":
            assert isinstance(r.match, IcmpMatch), r
            assert 0 <= r.match.type <= 255, r
            assert r.match.code is None or 0 <= r.match.code <= 255, r
        else:
            assert isinstance(r.match, PortRange), r
            assert 1 <= r.match.start <= r.match.end <= 65535, r
            assert r.match.end - r.match.start + 1 <= 1024, r


@given(policies())
@pinned
def test_prop_no_shared_port_or_code(case: Case) -> None:
    """P2 (§2.3): same (src, dst, proto) never grants a port/ICMP code twice."""
    raw, tiers, has_vpn = case
    granted: dict[tuple[Any, Any, str], set[tuple[Any, int]]] = defaultdict(set)
    for r in compile_policy(raw, tiers, has_vpn):
        key = (r.src, r.dst, r.proto)
        new = cells(r.match)
        assert not new & granted[key], (r, sorted(new & granted[key])[:5])
        granted[key] |= new


@given(policies())
@pinned
def test_prop_rule_count(case: Case) -> None:
    """P3: count = sum over entries of |from| x |to| x |items|."""
    raw, tiers, has_vpn = case
    expected = sum(len(side(e["from"])) * len(side(e["to"])) * len(items_of(e)) for e in raw)
    assert len(compile_policy(raw, tiers, has_vpn)) == expected


@given(policies())
@pinned
def test_prop_no_forbidden_pairs(case: Case) -> None:
    """P4: no Internet() with a private tier or Vpn(); no src == dst."""
    raw, tiers, has_vpn = case
    for r in compile_policy(raw, tiers, has_vpn):
        assert r.src != r.dst, r
        for a, b in ((r.src, r.dst), (r.dst, r.src)):
            if isinstance(a, Internet):
                assert not isinstance(b, Vpn), r
                assert isinstance(b, TierRef) and tiers.get(b.name) is True, r


@given(policies())
@pinned
def test_prop_deterministic_and_pure(case: Case) -> None:
    """P5: compiling twice gives equal tuples; the input is not changed."""
    raw, tiers, has_vpn = case
    snapshot = copy.deepcopy(raw)
    first = compile_policy(raw, tiers, has_vpn)
    assert raw == snapshot
    assert compile_policy(copy.deepcopy(snapshot), tiers, has_vpn) == first


@given(policies())
@pinned
def test_prop_rule_order(case: Case) -> None:
    """P6 (§4.1): entry index, then the list side's order, then item order."""
    raw, tiers, has_vpn = case
    expected = [
        (endpoint(s), endpoint(d), e["proto"], match_of(e["proto"], it), i)
        for i, e in enumerate(raw)
        for s in side(e["from"])
        for d in side(e["to"])
        for it in items_of(e)
    ]
    got = [(r.src, r.dst, r.proto, r.match, r.entry)
           for r in compile_policy(raw, tiers, has_vpn)]
    assert got == expected
