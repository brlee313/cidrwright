"""Subnet allocator for cidrwright.

Reads a YAML network description, validates all of it, and returns one
IPv4 CIDR per (tier, AZ), packed with no overlap and no gaps.

Subnets are laid out by size, largest first, not in YAML order: a tier
listed later in the YAML can come first in the address space.

AWS reserves 5 addresses in every subnet (network, +1 router, +2 DNS,
+3 reserved, broadcast), so usable hosts = 2**(32 - prefix) - 5.
"""

from __future__ import annotations

import difflib
import ipaddress
import re
from dataclasses import dataclass

import yaml

MIN_PREFIX = 16
MAX_PREFIX = 28
AWS_RESERVED = 5

_AZ_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_NAME_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_CIDR_FORM_RE = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}/[0-9]{1,2}")

_EXCLUDED = tuple(
    (ipaddress.IPv4Network(net), why)
    for net, why in (
        ("0.0.0.0/8", "'this network'"),
        ("127.0.0.0/8", "loopback"),
        ("169.254.0.0/16", "link-local"),
        ("224.0.0.0/4", "multicast"),
        ("240.0.0.0/4", "reserved"),
    )
)

_QUOTE_BOOL = (
    "; YAML 1.1 reads unquoted words such as no, yes, on and off as "
    'booleans, so put it in quotes (e.g. "no")'
)
_QUOTE_NUM = "; YAML reads unquoted numbers as numbers, so put it in quotes"


class ConfigError(ValueError):
    """Every problem found in a config; str() gives one per line."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))

    def __str__(self) -> str:
        return "\n".join(self.errors)


@dataclass(frozen=True)
class Tier:
    """One subnet tier. `prefix` is the prefix length (24 means a /24)."""

    name: str
    prefix: int  # prefix length, resolved even if given as hosts


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


# ---------------------------------------------------------------- helpers


def _is_int(x: object) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


def _describe(x: object) -> str:
    if x is None:
        return "nothing (null)"
    if isinstance(x, bool):
        return f"boolean {x}"
    if isinstance(x, (int, float)):
        return f"number {x!r}"
    if isinstance(x, str):
        return f"string {x!r}"
    if isinstance(x, list):
        return "a list"
    if isinstance(x, dict):
        return "a mapping"
    return type(x).__name__


def _quote_hint(x: object) -> str:
    if isinstance(x, bool):
        return _QUOTE_BOOL
    if isinstance(x, (int, float)):
        return _QUOTE_NUM
    return ""


def _key_errors(
    mapping: dict, allowed: tuple[str, ...], required: tuple[str, ...], where: str
) -> list[str]:
    errs = []
    for key in mapping:
        if key not in allowed:
            msg = f"{where}: unknown key {key!r} (allowed: {', '.join(allowed)})"
            if isinstance(key, str):
                close = difflib.get_close_matches(key, allowed, n=1)
                if close:
                    msg += f"; did you mean {close[0]!r}?"
            errs.append(msg)
    for key in required:
        if key not in mapping:
            errs.append(f"{where}: missing required key {key!r}")
    return errs


def _hosts_to_prefix(hosts: int) -> int:
    """Largest p with 2**(32 - p) - 5 >= hosts, clamped to MAX_PREFIX."""
    return min(32 - (hosts + 4).bit_length(), MAX_PREFIX)


def _prefix_vs_vpc_error(label: str, prefix: int, vpc_prefix: int) -> str:
    return (
        f"{label}: prefix /{prefix} is larger than the VPC /{vpc_prefix}; "
        f"use /{vpc_prefix} to /{MAX_PREFIX}"
    )


def _capacity_error(
    vpc: ipaddress.IPv4Network, azs: tuple[str, ...], tiers: tuple[Tier, ...] | list[Tier]
) -> str | None:
    needed = len(azs) * sum(2 ** (32 - t.prefix) for t in tiers)
    available = vpc.num_addresses
    if needed <= available:
        return None
    return (
        f"config: capacity exceeded: {len(tiers)} tier(s) in {len(azs)} AZ(s) "
        f"need {needed} addresses, but the VPC {vpc} has {available}; "
        "use a larger VPC, fewer AZs or smaller tiers"
    )


# -------------------------------------------------------------- vpc rules


def _parse_vpc_cidr(value: object, errors: list[str]) -> ipaddress.IPv4Network | None:
    where = "vpc.cidr"
    if not isinstance(value, str):
        errors.append(f"{where}: must be a string like '10.0.0.0/16', got {_describe(value)}")
        return None
    if not _CIDR_FORM_RE.fullmatch(value):
        try:
            loose = ipaddress.IPv4Network(value, strict=False)
        except ValueError:
            loose = None
        if loose is not None and "/" in value:
            hint = f"write it as {loose.network_address}/{loose.prefixlen}"
        elif loose is not None:
            hint = f"add a prefix length, e.g. {value}/16"
        else:
            hint = "write it as a.b.c.d/nn, e.g. 10.0.0.0/16"
        errors.append(f"{where}: {value!r} is not in a.b.c.d/nn form; {hint}")
        return None
    try:
        net = ipaddress.IPv4Network(value)
    except ValueError:
        try:
            loose = ipaddress.IPv4Network(value, strict=False)
        except ValueError:
            errors.append(
                f"{where}: {value!r} is not a valid IPv4 network "
                "(each number must be 0-255, without leading zeros, and the prefix 0-32)"
            )
            return None
        errors.append(f"{where}: {value!r} has host bits set; use {loose}")
        return None
    ok = True
    if not MIN_PREFIX <= net.prefixlen <= MAX_PREFIX:
        errors.append(
            f"{where}: prefix /{net.prefixlen} is outside the AWS VPC range "
            f"/{MIN_PREFIX} to /{MAX_PREFIX}"
        )
        ok = False
    for excl, why in _EXCLUDED:
        if net.overlaps(excl):
            errors.append(
                f"{where}: {net} overlaps {excl} ({why}), which can never be a VPC; "
                "pick a private range such as 10.0.0.0/16"
            )
            ok = False
    return net if ok else None


def _validate_azs(value: object, errors: list[str]) -> tuple[str, ...] | None:
    where = "vpc.azs"
    if not isinstance(value, list):
        errors.append(f"{where}: must be a list of AZ keys like [a, b, c], got {_describe(value)}")
        return None
    if not value:
        errors.append(f"{where}: must list at least one AZ")
        return None
    seen: dict[str, int] = {}
    ok = True
    for i, az in enumerate(value):
        loc = f"{where}[{i}]"
        if not isinstance(az, str):
            errors.append(f"{loc}: must be a string, got {_describe(az)}{_quote_hint(az)}")
            ok = False
        elif not _AZ_RE.fullmatch(az):
            errors.append(
                f"{loc}: {az!r} must start with a lowercase letter and contain only "
                "a-z, 0-9, '_' or '-' (at most 64 characters)"
            )
            ok = False
        elif az in seen:
            errors.append(f"{loc}: duplicate AZ {az!r} (first at {where}[{seen[az]}])")
            ok = False
        else:
            seen[az] = i
    return tuple(value) if ok else None


def _validate_vpc(
    value: object, errors: list[str]
) -> tuple[ipaddress.IPv4Network | None, tuple[str, ...] | None]:
    if not isinstance(value, dict):
        errors.append(f"vpc: must be a mapping with 'cidr' and 'azs', got {_describe(value)}")
        return None, None
    errors.extend(_key_errors(value, ("cidr", "azs"), ("cidr", "azs"), "vpc"))
    by_key: dict[str, list[str]] = {"cidr": [], "azs": []}
    net = _parse_vpc_cidr(value["cidr"], by_key["cidr"]) if "cidr" in value else None
    azs = _validate_azs(value["azs"], by_key["azs"]) if "azs" in value else None
    for key in value:
        errors.extend(by_key.get(key, ()))
    return net, azs


# ------------------------------------------------------------- tier rules


def _check_prefix(value: object, vpc_prefix: int | None, label: str) -> tuple[int | None, list[str]]:
    if not _is_int(value):
        return None, [
            f"{label}: prefix must be an integer from {MIN_PREFIX} to {MAX_PREFIX}, "
            f"got {_describe(value)}"
        ]
    assert isinstance(value, int)
    if not MIN_PREFIX <= value <= MAX_PREFIX:
        return None, [
            f"{label}: prefix /{value} is outside the AWS subnet range "
            f"/{MIN_PREFIX} to /{MAX_PREFIX}"
        ]
    if vpc_prefix is not None and value < vpc_prefix:
        return None, [_prefix_vs_vpc_error(label, value, vpc_prefix)]
    return value, []


def _check_hosts(value: object, vpc_prefix: int | None, label: str) -> tuple[int | None, list[str]]:
    if not _is_int(value) or value < 1:  # type: ignore[operator]
        return None, [f"{label}: hosts must be a whole number of at least 1, got {_describe(value)}"]
    assert isinstance(value, int)
    p = _hosts_to_prefix(value)
    needs = f"a /{p}" if p >= 0 else "more addresses than IPv4 has"
    if vpc_prefix is not None and p < vpc_prefix:
        return None, [f"{label}: hosts {value} needs {needs}, larger than the VPC /{vpc_prefix}"]
    if p < MIN_PREFIX:
        return None, [
            f"{label}: hosts {value} needs {needs}, larger than the AWS maximum "
            f"subnet /{MIN_PREFIX} ({2 ** (32 - MIN_PREFIX) - AWS_RESERVED} usable hosts)"
        ]
    return p, []


def _validate_tier(
    i: int, raw: object, vpc_prefix: int | None, seen: dict[str, int], errors: list[str]
) -> Tier | None:
    label = f"tiers[{i}]"
    if not isinstance(raw, dict):
        errors.append(f"{label}: must be a mapping like {{name: web, prefix: 24}}, got {_describe(raw)}")
        return None
    by_key: dict[str, list[str]] = {"name": [], "prefix": [], "hosts": []}
    name: str | None = None
    if "name" in raw:
        value = raw["name"]
        if not isinstance(value, str):
            by_key["name"].append(f"{label}: name must be a string, got {_describe(value)}{_quote_hint(value)}")
        elif not _NAME_RE.fullmatch(value):
            by_key["name"].append(
                f"{label}: name {value!r} must start with a lowercase letter and contain "
                "only a-z, 0-9, '_' or '-' (at most 32 characters)"
            )
        elif value in seen:
            by_key["name"].append(f"{label}: duplicate tier name {value!r} (first at tiers[{seen[value]}])")
        else:
            seen[value] = i
            name = value
            label = f"{label} ({value})"
    errors.extend(_key_errors(raw, ("name", "prefix", "hosts"), ("name",), label))
    has_prefix, has_hosts = "prefix" in raw, "hosts" in raw
    if has_prefix and has_hosts:
        errors.append(f"{label}: give either 'prefix' or 'hosts', not both")
    elif not has_prefix and not has_hosts:
        errors.append(f"{label}: needs 'prefix' or 'hosts'")
    prefix: int | None = None
    if has_prefix:
        prefix, by_key["prefix"] = _check_prefix(raw["prefix"], vpc_prefix, label)
    if has_hosts:
        hosts_prefix, by_key["hosts"] = _check_hosts(raw["hosts"], vpc_prefix, label)
        if not has_prefix:
            prefix = hosts_prefix
    for key in raw:
        errors.extend(by_key.get(key, ()))
    if name is None or prefix is None or (has_prefix and has_hosts):
        return None
    return Tier(name=name, prefix=prefix)


def _validate_tiers(value: object, vpc_prefix: int | None, errors: list[str]) -> list[Tier] | None:
    if not isinstance(value, list):
        errors.append(f"tiers: must be a list of tiers, got {_describe(value)}")
        return None
    if not value:
        errors.append("tiers: must list at least one tier")
        return None
    seen: dict[str, int] = {}
    tiers: list[Tier] = []
    ok = True
    for i, raw in enumerate(value):
        tier = _validate_tier(i, raw, vpc_prefix, seen, errors)
        if tier is None:
            ok = False
        else:
            tiers.append(tier)
    return tiers if ok else None


# ---------------------------------------------------------------- public


def validate(data: object) -> Config:
    """Check a parsed config; raise ConfigError listing every problem."""
    if data is None:
        raise ConfigError(["config: the file is empty; it needs 'vpc' and 'tiers' sections"])
    if not isinstance(data, dict):
        raise ConfigError([f"config: must be a mapping with 'vpc' and 'tiers', got {_describe(data)}"])
    errors = _key_errors(data, ("vpc", "tiers"), ("vpc", "tiers"), "config")
    by_key: dict[str, list[str]] = {"vpc": [], "tiers": []}
    vpc, azs = _validate_vpc(data["vpc"], by_key["vpc"]) if "vpc" in data else (None, None)
    tiers = (
        _validate_tiers(data["tiers"], vpc.prefixlen if vpc is not None else None, by_key["tiers"])
        if "tiers" in data
        else None
    )
    for key in data:
        errors.extend(by_key.get(key, ()))
    if vpc is not None and azs is not None and tiers is not None:
        cap = _capacity_error(vpc, azs, tiers)
        if cap:
            errors.append(cap)
    if errors:
        raise ConfigError(errors)
    assert vpc is not None and azs is not None and tiers is not None
    return Config(vpc=vpc, azs=azs, tiers=tuple(tiers))


def allocate(config: Config) -> dict[tuple[str, str], Allocation]:
    """Return one Allocation per (tier name, AZ), keyed by (tier, az).

    Each tier's `prefix` is a prefix length (24 means a /24). Requests are
    placed end to end from the VPC network address, sorted by prefix
    length ascending (largest subnet first), then by the tier's position,
    then by the AZ's position. The dict's insertion order is address order.

    Re-checks that every tier prefix length is at least the VPC's and that
    everything fits, because a Config can be built without validate().
    Raises ConfigError if either check fails.
    """
    vpc = config.vpc
    errors = [
        _prefix_vs_vpc_error(f"tiers[{i}] ({tier.name})", tier.prefix, vpc.prefixlen)
        for i, tier in enumerate(config.tiers)
        if tier.prefix < vpc.prefixlen
    ]
    if not errors:  # as in validate(): skip capacity when a tier is invalid
        cap = _capacity_error(vpc, config.azs, config.tiers)
        if cap:
            errors.append(cap)
    if errors:
        raise ConfigError(errors)

    requests = sorted(
        (tier.prefix, ti, ai, tier.name, az)
        for ti, tier in enumerate(config.tiers)
        for ai, az in enumerate(config.azs)
    )
    result: dict[tuple[str, str], Allocation] = {}
    addr = int(vpc.network_address)
    for prefix, _, _, name, az in requests:
        net = ipaddress.IPv4Network((addr, prefix))
        result[(name, az)] = Allocation(
            tier=name, az=az, network=net, usable_hosts=net.num_addresses - AWS_RESERVED
        )
        addr += net.num_addresses
    return result


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys."""

    def construct_mapping(self, node, deep=False):  # type: ignore[no-untyped-def]
        if isinstance(node, yaml.MappingNode):
            seen = set()
            for key_node, _ in node.value:
                if key_node.tag == "tag:yaml.org,2002:merge":
                    continue
                key = self.construct_object(key_node, deep=deep)
                try:
                    hash(key)
                except TypeError:
                    continue  # SafeLoader reports unhashable keys itself
                if key in seen:
                    raise yaml.constructor.ConstructorError(
                        "while constructing a mapping",
                        node.start_mark,
                        f"duplicate key {key!r}",
                        key_node.start_mark,
                    )
                seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_config(path) -> Config:  # type: ignore[no-untyped-def]
    """Read a YAML file and validate it. OSError propagates unchanged."""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError([f"{path}: not valid UTF-8 text"]) from None
    loader = None
    try:
        # The constructor itself can raise (e.g. unprintable characters).
        loader = _UniqueKeyLoader(text)
        data = loader.get_single_data()
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{path}:{mark.line + 1}" if mark is not None else f"{path}"
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError([f"{where}: invalid YAML: {problem}"]) from None
    finally:
        if loader is not None:
            loader.dispose()
    return validate(data)
