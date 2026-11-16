"""Policy endpoint words, the policy IR, and policy validation.

- `RESERVED_ENDPOINTS` / `check_tier_names`: tier-name check used by
  `model.py` (P-01).
- IR dataclasses (spec §4.1): `TierRef`, `Internet`, `Vpn`, `PortRange`,
  `IcmpMatch`, `Rule`.
- `validate_policy`: checks the `policy:` section (P-02, P-10 and up),
  reporting at most one error per entry (spec §6 guard 1), in the check
  order of spec §5.1.

This module does not import `ipam` (ADR 0006); it gets tier names and
`public` flags as plain values.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Union

from cidrwright.errors import describe

RESERVED_ENDPOINTS: tuple[str, ...] = ("internet", "vpn", "*")

MAX_PORT_SPAN = 1024

_ENTRY_KEYS = ("action", "from", "to", "proto", "ports", "icmp")
# Required keys in §5.1 step-2 order, with the hint for "missing".
_REQUIRED = (
    ("action", " (only 'allow' is supported)"),
    ("from", ""),
    ("to", ""),
    ("proto", " (one of tcp, udp, icmp)"),
)
_ENTRY_SHAPE = "{action: allow, from: web, to: app, proto: tcp, ports: [8080]}"


@dataclass(frozen=True)
class TierRef:
    """Reference to a tier by name (not ipam.Tier, which defines one)."""
    name: str


@dataclass(frozen=True)
class Internet:
    """Any IPv4 address (0.0.0.0/0); never ::/0."""


@dataclass(frozen=True)
class Vpn:
    """The VPN clients defined in the vpn: section."""


Endpoint = Union[TierRef, Internet, Vpn]


@dataclass(frozen=True)
class PortRange:
    start: int  # 1..65535
    end: int  # start..65535; end - start + 1 <= MAX_PORT_SPAN


@dataclass(frozen=True)
class IcmpMatch:
    type: int  # 0..255
    code: int | None  # 0..255, or None = all codes of this type


@dataclass(frozen=True)
class Rule:
    src: Endpoint
    dst: Endpoint
    proto: str  # "tcp" | "udp" | "icmp"
    match: PortRange | IcmpMatch
    entry: int  # index into policy: (traceability)


def check_tier_names(names: Iterable[tuple[int, str]]) -> list[str]:
    """Return one error per (index, name) whose name is a reserved endpoint.

    Errors come in input order and start with the tier's path, like M2's
    messages.
    """
    return [
        f"tiers[{i}] ({name}): {name!r} is a reserved policy endpoint; "
        "rename the tier (e.g. 'edge')"
        for i, name in names
        if name in RESERVED_ENDPOINTS
    ]


def validate_policy(
    raw_policy: object, tiers: Mapping[str, bool], has_vpn: bool
) -> list[str]:
    """Return every policy error, at most one per entry, in entry order.

    `tiers` maps tier name -> public, in YAML order. Call this only when
    the file has a `policy` key: `None` here means `policy:` with no
    value, which is an error (P-02). `[]` is valid.
    """
    if not isinstance(raw_policy, list):
        return [f"policy: must be a list of entries, got {describe(raw_policy)}"]
    errors: list[str] = []
    for i, raw in enumerate(raw_policy):
        err = _check_entry(i, raw, tiers, has_vpn)
        if err is not None:
            errors.append(err)
    # Stage 2 adds proto/ports/icmp checks to _check_entry. Stage 3 adds
    # the cross-entry checks (P-50, P-51), run only if `errors` is empty.
    return errors


def _check_entry(
    i: int, raw: object, tiers: Mapping[str, bool], has_vpn: bool
) -> str | None:
    """First error in one entry, following spec §5.1 (guard 1), or None."""
    where = f"policy[{i}]"
    if not isinstance(raw, dict):  # P-10
        return f"{where}: must be a mapping like {_ENTRY_SHAPE}, got {describe(raw)}"
    err = (
        _check_keys(where, raw)
        or _check_action(where, raw["action"])
        or _check_sides(where, raw["from"], raw["to"])
    )
    if err:
        return err
    srcs = _check_side(f"{where}.from", raw["from"], tiers, has_vpn)
    if isinstance(srcs, str):
        return srcs
    dsts = _check_side(f"{where}.to", raw["to"], tiers, has_vpn)
    if isinstance(dsts, str):
        return dsts
    return _check_pairs(where, srcs, dsts, tiers)


def _check_keys(where: str, entry: dict) -> str | None:
    """P-11 unknown key; then missing action/from/to/proto (P-12, P-13, P-30)."""
    for key in entry:
        if key not in _ENTRY_KEYS:
            msg = f"{where}: unknown key {key!r} (allowed: {', '.join(_ENTRY_KEYS)})"
            if isinstance(key, str):
                close = difflib.get_close_matches(key, _ENTRY_KEYS, n=1)
                if close:
                    msg += f"; did you mean {close[0]!r}?"
            return msg
    for key, hint in _REQUIRED:
        if key not in entry:
            return f"{where}: missing {key!r}{hint}"
    return None


def _check_action(where: str, value: object) -> str | None:
    """P-12 (value)."""
    if isinstance(value, str) and value == "allow":
        return None
    return f"{where}.action: only 'allow' is supported, got {describe(value)}"


def _check_sides(where: str, src: object, dst: object) -> str | None:
    """P-17, then P-18 (from before to)."""
    if isinstance(src, list) and isinstance(dst, list):
        return f"{where}: from and to are both lists; split into separate entries"
    for side, value in (("from", src), ("to", dst)):
        if isinstance(value, list) and not value:
            return f"{where}.{side}: empty list"
    return None


def _check_side(
    path: str, value: object, tiers: Mapping[str, bool], has_vpn: bool
) -> list[str] | str:
    """Endpoint names of one side, or the first error (P-14/15/16/19, item order)."""
    is_list = isinstance(value, list)
    items = value if isinstance(value, list) else [value]
    seen: dict[str, int] = {}
    names: list[str] = []
    for j, item in enumerate(items):
        loc = f"{path}[{j}]" if is_list else path
        if not isinstance(item, str):  # wrong type: P-15 family
            return (
                f"{loc}: must be an endpoint name (a tier, internet or vpn), "
                f"got {describe(item)}"
            )
        err = _check_endpoint(loc, item, tiers, has_vpn)
        if err:
            return err
        if item in seen:  # P-19
            return f"{loc}: {item!r} is listed twice (first at {path}[{seen[item]}])"
        seen[item] = j
        names.append(item)
    return names


def _check_endpoint(
    loc: str, name: str, tiers: Mapping[str, bool], has_vpn: bool
) -> str | None:
    """P-14, P-16, P-15 for one endpoint name."""
    if name == "*":
        return f"{loc}: '*' is not allowed; list tiers explicitly: [{', '.join(tiers)}]"
    if name == "vpn":
        return None if has_vpn else f"{loc}: 'vpn' is used but no vpn: section is defined"
    if name == "internet" or name in tiers:
        return None
    known = [*tiers, "internet", *(["vpn"] if has_vpn else [])]
    return f"{loc}: unknown endpoint {name!r}; known: {', '.join(known)}"


def _check_pairs(
    where: str, srcs: list[str], dsts: list[str], tiers: Mapping[str, bool]
) -> str | None:
    """First bad (src, dst) pair, in list order (only one side is a list)."""
    for s in srcs:
        for d in dsts:
            err = _check_pair(where, s, d, tiers)
            if err:
                return err
    return None


def _check_pair(where: str, s: str, d: str, tiers: Mapping[str, bool]) -> str | None:
    """P-20, then P-21, P-22, P-23 for one pair."""
    pair = f"{where}: {s} -> {d}"
    if s == d:
        return (
            f"{pair}: traffic within a tier is not allowed; model the roles as "
            "separate tiers (e.g. db-primary -> db-replica)"
        )
    if s == "internet" and d in tiers and not tiers[d]:
        return (
            f"{pair}: tier {d!r} is not public (add public: true to the tier, or "
            f"route through a public tier, e.g. internet -> web, web -> {d})"
        )
    if d == "internet" and s in tiers and not tiers[s]:
        return (
            f"{pair}: tier {s!r} is not public; route outbound traffic through a "
            f"public tier, e.g. {s} -> proxy, proxy -> internet"
        )
    if {s, d} == {"internet", "vpn"}:
        return (
            f"{pair}: internet can only be paired with a public tier (VPN access "
            "goes through the WireGuard host, configured in vpn:)"
        )
    return None
