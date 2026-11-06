"""Network model: loads `network.yaml` and owns its top-level keys.

`model.py` owns the top-level keys (`vpc`, `tiers`, `vpn`, `policy`) and
the tier attribute `public`. It strips `public` from the tiers, hands
`vpc` and `tiers` to `ipam.validate`, and merges `ipam`'s errors with its
own into one `ConfigError`, in document order.

Part A: `policy` is kept raw and unchecked (`Network.policy_raw`).
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping
from dataclasses import dataclass

import yaml

from cidrwright import ipam, policy
from cidrwright.ipam import ConfigError
from cidrwright.yamlio import UniqueKeyLoader

_TOP_KEYS = ("vpc", "tiers", "vpn", "policy")
_LEAD_RE = re.compile(r"(?P<head>vpc|tiers|config)(?:\[(?P<idx>\d+)\])?(?=[:. (])")


@dataclass(frozen=True)
class Network:
    config: ipam.Config
    public: frozenset[str]
    vpn: Mapping[str, object] | None
    policy_raw: object  # None if absent; unchecked in Part A


# ---------------------------------------------------------------- helpers


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


def _unknown_key_errors(data: dict) -> list[str]:
    errs = []
    for key in data:
        if key not in _TOP_KEYS:
            msg = f"config: unknown key {key!r} (allowed: {', '.join(_TOP_KEYS)})"
            if isinstance(key, str):
                close = difflib.get_close_matches(key, _TOP_KEYS, n=1)
                if close:
                    msg += f"; did you mean {close[0]!r}?"
            errs.append(msg)
    return errs


def _strip_public(tiers: object) -> object:
    """Copy of `tiers` with every `public` key removed; input not mutated.

    The list keeps its length and order, so ipam's `tiers[i]` labels still
    point at the right YAML entry.
    """
    if not isinstance(tiers, list):
        return tiers
    return [
        {k: v for k, v in t.items() if k != "public"} if isinstance(t, dict) else t
        for t in tiers
    ]


def _tier_errors(tiers: object) -> dict[int, list[str]]:
    """Errors owned by model.py, per tier index: P-01, then M-02."""
    if not isinstance(tiers, list):
        return {}
    result: dict[int, list[str]] = {}
    for i, t in enumerate(tiers):
        if not isinstance(t, dict):
            continue
        name = t.get("name")
        label = f"tiers[{i}] ({name})" if isinstance(name, str) else f"tiers[{i}]"
        errs: list[str] = []
        if isinstance(name, str):
            errs.extend(policy.check_tier_names([(i, name)]))
        if "public" in t and not isinstance(t["public"], bool):
            errs.append(f"{label}: public must be true or false, got {_describe(t['public'])}")
        if errs:
            result[i] = errs
    return result


def _bucket(err: str) -> tuple[str, int | None]:
    m = _LEAD_RE.match(err)
    if m is None or (m["head"] != "tiers" and m["idx"] is not None):
        return ("config", None)
    if m["head"] == "tiers":
        return ("tiers", int(m["idx"]) if m["idx"] is not None else None)
    return (m["head"], None)


def _assemble(
    data: dict,
    unknown: list[str],
    ipam_errors: list[str],
    tier_errors: dict[int, list[str]],
    vpn_errors: list[str],
) -> list[str]:
    """Merge model.py's and ipam's errors in document order.

    ipam errors are bucketed by their leading path token only (`vpc`,
    `tiers`, `tiers[N]`, `config`), never by message content. Any error
    matching no bucket goes into the trailing `config` bucket, so none is
    lost. The `config` bucket leads if `vpc` or `tiers` is absent from
    `data` (missing-key errors). Otherwise it trails (the capacity error).
    This relies on M2's convention that ipam messages start with their
    path. The M2 tests pin that convention.

    Within one tier: ipam's errors first, then the reserved name (P-01),
    then `public` (M-02).
    """
    buckets: dict[tuple[str, int | None], list[str]] = {}
    for e in ipam_errors:
        buckets.setdefault(_bucket(e), []).append(e)
    config_errs = buckets.pop(("config", None), [])
    missing = "vpc" not in data or "tiers" not in data
    out = list(unknown)
    if missing:
        out += config_errs
    for key in data:  # file order
        if key == "vpc":
            out += buckets.pop(("vpc", None), [])
        elif key == "tiers":
            out += buckets.pop(("tiers", None), [])
            idxs = sorted({i for (h, i) in buckets if h == "tiers" and i is not None} | set(tier_errors))
            for i in idxs:
                out += buckets.pop(("tiers", i), [])  # ipam first
                out += tier_errors.get(i, [])  # then P-01, M-02
        elif key == "vpn":
            out += vpn_errors
    if not missing:
        out += config_errs
    for rest in buckets.values():  # safety net: never lose an error
        out += rest
    return out


# ---------------------------------------------------------------- public


def validate_network(data: object) -> Network:
    """Check a parsed network file; raise ConfigError listing every problem."""
    if not isinstance(data, dict):
        ipam.validate(data)  # always raises for None and non-mappings
        raise AssertionError("unreachable")
    unknown = _unknown_key_errors(data)

    translated: dict = {}
    for key in data:
        if key == "vpc":
            translated["vpc"] = data["vpc"]
        elif key == "tiers":
            translated["tiers"] = _strip_public(data["tiers"])

    config: ipam.Config | None
    try:
        config = ipam.validate(translated)
        ipam_errors: list[str] = []
    except ConfigError as exc:
        config = None
        ipam_errors = exc.errors

    tier_errors = _tier_errors(data.get("tiers"))
    vpn_errors = (
        [f"vpn: must be a mapping, got {_describe(data['vpn'])}"]
        if "vpn" in data and not isinstance(data["vpn"], dict)
        else []
    )
    errors = _assemble(data, unknown, ipam_errors, tier_errors, vpn_errors)
    if errors:
        raise ConfigError(errors)
    assert config is not None
    return Network(
        config=config,
        public=frozenset(t["name"] for t in data["tiers"] if t.get("public") is True),
        vpn=data.get("vpn"),
        policy_raw=data.get("policy"),
    )


def load_network(path) -> Network:  # type: ignore[no-untyped-def]
    """Read a YAML file and validate it as a network. OSError propagates unchanged."""
    # Duplicates ipam.load_config file reading; dedupe after M3 (circular import via ConfigError).
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ConfigError([f"{path}: not valid UTF-8 text"]) from None
    loader = None
    try:
        # The constructor itself can raise (e.g. unprintable characters).
        loader = UniqueKeyLoader(text)
        data = loader.get_single_data()
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f"{path}:{mark.line + 1}" if mark is not None else f"{path}"
        problem = getattr(exc, "problem", None) or str(exc)
        raise ConfigError([f"{where}: invalid YAML: {problem}"]) from None
    finally:
        if loader is not None:
            loader.dispose()
    return validate_network(data)
