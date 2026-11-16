import ast
import copy
import dataclasses
from pathlib import Path

import pytest

from cidrwright import policy
from cidrwright.errors import ConfigError
from cidrwright.policy import (
    ICMP_MAX,
    MAX_PORT_SPAN,
    PORT_MAX,
    PORT_MIN,
    IcmpMatch,
    Internet,
    PortRange,
    Rule,
    TierRef,
    Vpn,
    compile_policy,
    validate_policy,
)

# Not alphabetical; proxy is a public tier not named web.
TIERS = {"db": False, "app": False, "web": True, "proxy": True}
KNOWN = "db, app, web, proxy, internet"


def entry(src: object = "app", dst: object = "db", **extra: object) -> dict[str, object]:
    e: dict[str, object] = {"action": "allow", "from": src, "to": dst, "proto": "tcp", "ports": [5432]}
    e.update(extra)
    return e


def without(e, *keys):
    return {k: v for k, v in e.items() if k not in keys}


def icmp_entry(items: object, src: object = "vpn", dst: object = "app") -> dict[str, object]:
    return without(entry(src, dst, proto="icmp", icmp=items), "ports")


def rng(start: object, end: object) -> dict[str, object]:
    return {"start": start, "end": end}


def errs(pol, tiers=TIERS, has_vpn=True):
    return validate_policy(pol, tiers, has_vpn)


def one(pol, **kw):
    e = errs(pol, **kw)
    assert len(e) == 1, e
    return e[0]


def check(msg, path, *content):
    assert msg.startswith(path + ": "), msg
    for c in content:
        assert c in msg, msg


VALID = [
    entry("internet", "web", ports=[443]),
    entry("internet", "proxy"),
    entry("proxy", "internet"),
    entry("web", "internet"),
    entry("vpn", ["web", "db", "app"]),
    entry(["web", "app"], "db"),
    entry("app", "vpn"),
    entry("db", "app"),
]


# ------------------------------------------------------------------ IR


def test_ir_values():
    r = Rule(TierRef("web"), Internet(), "tcp", PortRange(443, 443), 0)
    assert r == Rule(TierRef("web"), Internet(), "tcp", PortRange(443, 443), entry=0)
    assert r != Rule(TierRef("app"), Internet(), "tcp", PortRange(443, 443), 0)
    assert [f.name for f in dataclasses.fields(Rule)] == ["src", "dst", "proto", "match", "entry"]
    assert TierRef("vpn") != Vpn()
    assert len({Internet(), Internet(), Vpn(), Vpn()}) == 2
    assert IcmpMatch(3, None) != IcmpMatch(3, 4)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(r, "entry", 1)


def test_max_port_span():
    assert MAX_PORT_SPAN == 1024


def test_no_tier_name_in_policy():
    assert not hasattr(policy, "Tier")


def test_policy_does_not_import_ipam():
    assert policy.__file__ is not None
    tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported |= {f"{node.module}.{a.name}" for a in node.names}
    assert "cidrwright.errors" in imported
    assert not any("ipam" in m for m in imported)


# ------------------------------------------------------------------ P-02


def test_empty_policy_is_valid():
    assert errs([]) == []


@pytest.mark.parametrize(
    "value, got",
    [
        (None, "nothing (null)"),
        (5, "number 5"),
        ("web", "string 'web'"),
        ({}, "a mapping"),
        (True, "boolean True"),
    ],
)
def test_policy_not_a_list(value, got):
    check(one(value), "policy", "must be a list of entries", got)


# ------------------------------------------------------------ valid side


def test_valid_entries_accepted():
    assert errs(VALID) == []


def test_valid_without_vpn():
    assert errs([entry("internet", "web"), entry(["web", "app"], "db")], has_vpn=False) == []


# ------------------------------------------- P-10 to P-23, one message each

ENTRY_ERRORS = [
    # P-10
    pytest.param("web", "policy[1]", ("must be a mapping like {action: allow", "string 'web'"), id="P10-str"),
    pytest.param([], "policy[1]", ("must be a mapping like", "a list"), id="P10-list"),
    pytest.param(None, "policy[1]", ("must be a mapping like", "nothing (null)"), id="P10-null"),
    pytest.param(8080, "policy[1]", ("must be a mapping like", "number 8080"), id="P10-num"),
    # P-11 (port typo: exactly one message, no "missing ports" cascade)
    pytest.param({**without(entry(), "ports"), "port": [5432]}, "policy[1]",
                 ("unknown key 'port'", "did you mean 'ports'?"), id="P11-port"),
    pytest.param({**without(entry(), "from"), "form": "app"}, "policy[1]",
                 ("unknown key 'form'", "did you mean 'from'?"), id="P11-before-P13"),
    pytest.param({**entry(), 1: "x"}, "policy[1]", ("unknown key 1",), id="P11-nonstr"),
    pytest.param(entry("app", "app", colour=1), "policy[1]", ("unknown key 'colour'",), id="P11-before-P20"),
    # P-12
    pytest.param(without(entry(), "action"), "policy[1]", ("missing 'action'", "only 'allow'"), id="P12-missing"),
    pytest.param(entry(action="deny"), "policy[1].action", ("only 'allow' is supported", "string 'deny'"), id="P12-deny"),
    pytest.param(entry(action="Allow"), "policy[1].action", ("string 'Allow'",), id="P12-case"),
    pytest.param(entry(action=True), "policy[1].action", ("boolean True",), id="P12-bool"),
    pytest.param(entry(action=None), "policy[1].action", ("nothing (null)",), id="P12-null"),
    # P-13 and missing proto (§5.1 step 2 order: action, from, to, proto)
    pytest.param(without(entry(), "from"), "policy[1]", ("missing 'from'",), id="P13-from"),
    pytest.param(without(entry(), "to"), "policy[1]", ("missing 'to'",), id="P13-to"),
    pytest.param(without(entry(), "from", "to"), "policy[1]", ("missing 'from'",), id="P13-both"),
    pytest.param(without(entry(), "proto"), "policy[1]", ("missing 'proto'", "tcp, udp, icmp"), id="P30-missing"),
    pytest.param(without(entry(), "action", "to"), "policy[1]", ("missing 'action'",), id="missing-order"),
    # P-14
    pytest.param(entry(dst="*"), "policy[1].to", ("'*' is not allowed", "[db, app, web, proxy]"), id="P14-to"),
    pytest.param(entry(dst=["web", "*"]), "policy[1].to[1]", ("'*' is not allowed",), id="P14-list"),
    pytest.param(entry(src="*"), "policy[1].from", ("'*' is not allowed",), id="P14-from"),
    # P-15 and wrong types
    pytest.param(entry(dst=["web", "ap"]), "policy[1].to[1]", ("unknown endpoint 'ap'",), id="P15-list"),
    pytest.param(entry(src="Web"), "policy[1].from", ("unknown endpoint 'Web'",), id="P15-case"),
    pytest.param(entry(src=5), "policy[1].from", ("must be an endpoint name", "number 5"), id="P15-num"),
    pytest.param(entry(src=True), "policy[1].from", ("boolean True",), id="P15-bool"),
    pytest.param(entry(src=None), "policy[1].from", ("nothing (null)",), id="P15-null"),
    pytest.param(entry(dst={"a": 1}), "policy[1].to", ("a mapping",), id="P15-map"),
    pytest.param(entry(dst=["web", 3]), "policy[1].to[1]", ("number 3",), id="P15-item-num"),
    pytest.param(entry(src=["web", ["app"]]), "policy[1].from[1]", ("a list",), id="P15-item-list"),
    # P-17 (before P-18)
    pytest.param(entry(["web", "app"], ["db"]), "policy[1]", ("from and to are both lists",), id="P17"),
    pytest.param(entry(["web"], []), "policy[1]", ("both lists",), id="P17-before-P18"),
    # P-18
    pytest.param(entry([], "db"), "policy[1].from", ("empty list",), id="P18-from"),
    pytest.param(entry("app", []), "policy[1].to", ("empty list",), id="P18-to"),
    # P-19
    pytest.param(entry("app", ["web", "db", "web"]), "policy[1].to[2]",
                 ("'web' is listed twice", "first at policy[1].to[0]"), id="P19-to"),
    pytest.param(entry(["db", "web", "db"], "app"), "policy[1].from[2]", ("'db' is listed twice",), id="P19-from"),
    # P-20
    pytest.param(entry("app", "app"), "policy[1]", ("app -> app", "traffic within a tier is not allowed"), id="P20"),
    pytest.param(entry(["db", "app"], "app"), "policy[1]", ("app -> app", "within a tier"), id="P20-list"),
    pytest.param(entry("internet", "internet"), "policy[1]",
                 ("internet -> internet", "an endpoint can't be paired with itself"), id="P20-inet"),
    pytest.param(entry("vpn", "vpn"), "policy[1]",
                 ("vpn -> vpn", "an endpoint can't be paired with itself"), id="P20-vpn"),
    # P-21
    pytest.param(entry("internet", "app"), "policy[1]", ("internet -> app", "tier 'app' is not public"), id="P21"),
    pytest.param(entry("internet", ["proxy", "db"]), "policy[1]", ("internet -> db", "tier 'db' is not public"), id="P21-list"),
    # P-22
    pytest.param(entry("db", "internet"), "policy[1]",
                 ("db -> internet", "tier 'db' is not public", "route outbound"), id="P22"),
    pytest.param(entry(["proxy", "app"], "internet"), "policy[1]", ("app -> internet", "tier 'app' is not public"), id="P22-list"),
    # P-23
    pytest.param(entry("internet", "vpn"), "policy[1]",
                 ("internet -> vpn", "internet can only be paired with a public tier"), id="P23"),
    pytest.param(entry("vpn", "internet"), "policy[1]", ("vpn -> internet", "only be paired"), id="P23-rev"),
    pytest.param(entry("internet", ["web", "vpn"]), "policy[1]", ("internet -> vpn", "only be paired"), id="P23-list"),
    # §5.1 order within step 3
    pytest.param(entry(["a"], ["b"], action="deny"), "policy[1].action", ("string 'deny'",), id="action-before-sides"),
    pytest.param(entry(["ap"], ["*"]), "policy[1]", ("both lists",), id="sides-before-items"),
    pytest.param(entry("ap", "*"), "policy[1].from", ("unknown endpoint 'ap'",), id="from-before-to"),
    pytest.param(entry(["xx", "*"], "db"), "policy[1].from[0]", ("unknown endpoint 'xx'",), id="list-order"),
    pytest.param(entry("app", ["internet", "ap"]), "policy[1].to[1]", ("unknown endpoint 'ap'",), id="items-before-pairs"),
    pytest.param(entry(["internet", "app"], "app"), "policy[1]", ("internet -> app", "not public"), id="pairs-in-list-order"),
]


@pytest.mark.parametrize("bad, path, contents", ENTRY_ERRORS)
def test_entry_error(bad, path, contents):
    check(one([VALID[0], bad]), path, *contents)


def test_unknown_key_without_close_match_has_no_hint():
    for bad in (entry(colour="red"), {**entry(), 1: "x"}):
        assert "did you mean" not in one([bad])


@pytest.mark.parametrize("has_vpn, tail", [(True, f"known: {KNOWN}, vpn"), (False, f"known: {KNOWN}")])
def test_unknown_endpoint_known_list(has_vpn, tail):
    msg = one([entry("ap", "db")], has_vpn=has_vpn)
    check(msg, "policy[0].from", "unknown endpoint 'ap'")
    assert msg.endswith(tail)


@pytest.mark.parametrize(
    "bad, path",
    [(entry("vpn", "web"), "policy[0].from"), (entry("app", ["db", "vpn"]), "policy[0].to[1]")],
)
def test_vpn_without_section(bad, path):
    check(one([bad], has_vpn=False), path, "'vpn' is used but no vpn: section is defined")
    assert errs([bad], has_vpn=True) == []


def test_star_lists_tiers_in_given_order():
    msg = one([entry("zeta", "*")], tiers={"zeta": True, "alpha": False})
    check(msg, "policy[0].to", "[zeta, alpha]")


def test_public_flag_decides_not_name():
    tiers = {"web": False, "edge": True}
    check(one([entry("internet", "web")], tiers=tiers), "policy[0]",
          "tier 'web' is not public", "e.g. internet -> edge, edge -> web)")
    check(one([entry("web", "internet")], tiers=tiers), "policy[0]",
          "tier 'web' is not public", "e.g. web -> edge, edge -> internet")
    assert errs([entry("internet", "edge"), entry("edge", "internet")], tiers=tiers) == []


@pytest.mark.parametrize(
    "src, dst, own, other",
    [
        ("app", "app", "traffic within a tier is not allowed", "paired with itself"),
        ("internet", "internet", "an endpoint can't be paired with itself", "within a tier"),
        ("vpn", "vpn", "an endpoint can't be paired with itself", "within a tier"),
    ],
)
def test_self_rule_wording(src, dst, own, other):
    msg = one([entry(src, dst)])
    check(msg, "policy[0]", f"{src} -> {dst}", own)
    assert other not in msg


# First tier private; first public is gate, not alphabetical-first edge; no web/proxy.
HINT_TIERS = {"zeta": False, "gate": True, "edge": True}


def test_hints_name_first_public_tier():
    inbound = one([entry("internet", "zeta")], tiers=HINT_TIERS)
    check(inbound, "policy[0]", "tier 'zeta' is not public",
          "e.g. internet -> gate, gate -> zeta)")
    outbound = one([entry("zeta", "internet")], tiers=HINT_TIERS)
    check(outbound, "policy[0]", "tier 'zeta' is not public",
          "e.g. zeta -> gate, gate -> internet")
    for msg in (inbound, outbound):
        assert "web" not in msg and "proxy" not in msg and "edge" not in msg


def test_hints_default_tiers():
    check(one([entry("internet", "app")]), "policy[0]", "e.g. internet -> web, web -> app)")
    check(one([entry("db", "internet")]), "policy[0]", "e.g. db -> web, web -> internet")


def test_hints_without_public_tier():
    tiers = {"zeta": False, "alpha": False}
    check(one([entry("internet", "zeta")], tiers=tiers), "policy[0]",
          "tier 'zeta' is not public",
          "e.g. internet -> a public tier, a public tier -> zeta)")
    check(one([entry("zeta", "internet")], tiers=tiers), "policy[0]",
          "tier 'zeta' is not public",
          "e.g. zeta -> a public tier, a public tier -> internet")


# ------------------------------------------------------------ noise guards


def test_two_bad_entries_in_entry_order():
    e = errs([entry(action="deny"), VALID[0], entry(dst="ap")])
    assert len(e) == 2
    check(e[0], "policy[0].action", "string 'deny'")
    check(e[1], "policy[2].to", "unknown endpoint 'ap'")


def test_every_entry_checked():
    e = errs(["x", entry(src="*"), without(entry(), "to"), entry("db", "internet")])
    assert len(e) == 4
    check(e[0], "policy[0]", "must be a mapping like")
    check(e[1], "policy[1].from", "'*' is not allowed")
    check(e[2], "policy[2]", "missing 'to'")
    check(e[3], "policy[3]", "db -> internet")


def test_deterministic():
    pol = [entry(action="deny"), entry(dst=["web", "ap"]), entry("app", "app")]
    assert errs(pol) == errs(copy.deepcopy(pol))


def test_input_not_mutated():
    pol = [entry(action="deny"), *VALID]
    tiers = dict(TIERS)
    before = copy.deepcopy((pol, tiers))
    errs(pol, tiers=tiers)
    assert (pol, tiers) == before


# --------------------------------------------- proto, ports, icmp: valid


def test_constants():
    assert (PORT_MIN, PORT_MAX, ICMP_MAX) == (1, 65535, 255)


VALID_MATCH = [
    pytest.param(entry(ports=[1]), id="port-1"),
    pytest.param(entry(ports=[65535]), id="port-65535"),
    pytest.param(entry(proto="udp", ports=[53]), id="udp"),
    pytest.param(entry(ports=[rng(1, 1024)]), id="span-1024-low"),
    pytest.param(entry(ports=[rng(64512, 65535)]), id="span-1024-high"),
    pytest.param(entry(ports=[rng(5, 5)]), id="range-one-port"),
    pytest.param(entry(ports=[rng(8000, 8049), rng(8050, 8150)]), id="adjacent"),
    pytest.param(entry(ports=[rng(8050, 8150), rng(8000, 8049)]), id="adjacent-reversed"),
    pytest.param(entry(ports=[8080, 22, rng(9000, 9010), 443]), id="mixed-unsorted"),
    pytest.param(icmp_entry([{"type": 0}]), id="icmp-type-0"),
    pytest.param(icmp_entry([{"type": 255}]), id="icmp-type-255"),
    pytest.param(icmp_entry([{"type": 0, "code": 0}]), id="icmp-code-0"),
    pytest.param(icmp_entry([{"type": 255, "code": 255}]), id="icmp-code-255"),
    pytest.param(icmp_entry([{"type": 8}, {"type": 3, "code": 4}]), id="icmp-spec"),
    pytest.param(icmp_entry([{"type": 3, "code": 4}, {"type": 3, "code": 3}]), id="icmp-same-type-other-code"),
    pytest.param(icmp_entry([{"type": 4}, {"type": 3}]), id="icmp-two-types"),
]


@pytest.mark.parametrize("good", VALID_MATCH)
def test_match_valid(good):
    assert errs([VALID[0], good]) == []


MATCH_ERRORS = [
    # P-30
    pytest.param(entry(proto="tpc"), "policy[1].proto", ("'tpc' is not one of tcp, udp, icmp",), id="P30-typo"),
    pytest.param(entry(proto="TCP"), "policy[1].proto", ("'TCP' is not one of",), id="P30-case"),
    pytest.param(entry(proto=6), "policy[1].proto", ("must be one of tcp, udp, icmp", "number 6"), id="P30-num"),
    pytest.param(entry(proto=True), "policy[1].proto", ("boolean True",), id="P30-bool"),
    pytest.param(entry(proto=None), "policy[1].proto", ("nothing (null)",), id="P30-null"),
    # P-31
    pytest.param(without(entry(), "ports"), "policy[1]", ("missing 'ports'", "required for tcp"), id="P31-tcp"),
    pytest.param(without(entry(proto="udp"), "ports"), "policy[1]", ("required for udp",), id="P31-udp"),
    pytest.param(entry(ports=[]), "policy[1].ports", ("empty list",), id="P31-empty"),
    pytest.param(entry(ports=443), "policy[1].ports", ("must be a list of ports", "number 443"), id="P31-num"),
    pytest.param(entry(ports=None), "policy[1].ports", ("nothing (null)",), id="P31-null"),
    # P-32
    pytest.param(entry(icmp=[{"type": 8}]), "policy[1].icmp", ("only allowed with proto: icmp",), id="P32"),
    pytest.param(without(entry(icmp=[{"type": 8}]), "ports"), "policy[1].icmp", ("only allowed with proto: icmp",), id="P32-before-P31"),    
    # P-33
    pytest.param(entry(proto="icmp", icmp=[{"type": 8}]), "policy[1].ports",
                 ("not allowed with proto: icmp", "ICMP has no ports"), id="P33"),
    pytest.param(entry(proto="icmp"), "policy[1].ports", ("not allowed with proto: icmp",), id="P33-before-P34"),
    # P-34
    pytest.param(without(entry(proto="icmp"), "ports"), "policy[1]", ("missing 'icmp'", "[{type: 8}]"), id="P34-missing"),
    pytest.param(icmp_entry([]), "policy[1].icmp", ("empty list",), id="P34-empty"),
    pytest.param(icmp_entry({"type": 8}), "policy[1].icmp", ("must be a list", "a mapping"), id="P34-map"),
    # P-40
    pytest.param(entry(ports=[0]), "policy[1].ports[0]", ("0 is outside 1-65535",), id="P40-0"),
    pytest.param(entry(ports=[65536]), "policy[1].ports[0]", ("65536 is outside 1-65535",), id="P40-65536"),
    pytest.param(entry(ports=[-1]), "policy[1].ports[0]", ("-1 is outside",), id="P40-neg"),
    pytest.param(entry(ports=[22, 70000]), "policy[1].ports[1]", ("70000 is outside 1-65535",), id="P40-second"),
    pytest.param(entry(ports=["443"]), "policy[1].ports[0]", ("must be a port number", "string '443'"), id="P40-str"),
    pytest.param(entry(ports=[443.0]), "policy[1].ports[0]", ("number 443.0",), id="P40-float"),
    pytest.param(entry(ports=[True]), "policy[1].ports[0]", ("boolean True",), id="P40-bool"),
    pytest.param(entry(ports=[None]), "policy[1].ports[0]", ("nothing (null)",), id="P40-null"),
    pytest.param(entry(ports=[rng(0, 10)]), "policy[1].ports[0].start", ("0 is outside 1-65535",), id="P40-start-0"),
    pytest.param(entry(ports=[rng(65000, 65536)]), "policy[1].ports[0].end", ("65536 is outside",), id="P40-end-65536"),
    pytest.param(entry(ports=[rng("1", 10)]), "policy[1].ports[0].start", ("string '1'",), id="P40-start-str"),
    pytest.param(entry(ports=[rng(1, True)]), "policy[1].ports[0].end", ("boolean True",), id="P40-end-bool"),
    # P-41
    pytest.param(entry(ports=[rng(8099, 8000)]), "policy[1].ports[0]", ("start 8099 is greater than end 8000",), id="P41-reversed"),
    pytest.param(entry(ports=[{"start": 8000}]), "policy[1].ports[0]", ("missing 'end'",), id="P41-no-end"),
    pytest.param(entry(ports=[{"end": 8000}]), "policy[1].ports[0]", ("missing 'start'",), id="P41-no-start"),
    pytest.param(entry(ports=[{}]), "policy[1].ports[0]", ("missing 'start'",), id="P41-empty"),
    pytest.param(entry(ports=[{**rng(1, 2), "step": 1}]), "policy[1].ports[0]", ("unknown key 'step'",), id="P41-unknown"),
    # P-42
    pytest.param(entry(ports=[rng(1, 1025)]), "policy[1].ports[0]",
                 ("range 1-1025 covers 1025 ports", "the limit is 1024"), id="P42-1025"),
    pytest.param(entry(ports=[rng(1, 65535)]), "policy[1].ports[0]", ("covers 65535 ports",), id="P42-all"),
    # P-43
    pytest.param(entry(ports=[rng(8000, 8099), rng(8050, 8150)]), "policy[1].ports[1]",
                 ("8050-8150 overlaps ports[0] (8000-8099) on 8050-8099",), id="P43-partial"),
    pytest.param(entry(ports=[rng(8050, 8150), rng(8000, 8099)]), "policy[1].ports[1]",
                 ("8000-8099 overlaps ports[0] (8050-8150) on 8050-8099",), id="P43-partial-reversed"),
    pytest.param(entry(ports=[rng(8000, 8050), rng(8050, 8150)]), "policy[1].ports[1]", ("on 8050;",), id="P43-one-port"),
    pytest.param(entry(ports=[rng(8000, 8099), 8080]), "policy[1].ports[1]",
                 ("8080 overlaps ports[0] (8000-8099) on 8080",), id="P43-contained"),
    pytest.param(entry(ports=[8080, rng(8000, 8099)]), "policy[1].ports[1]",
                 ("8000-8099 overlaps ports[0] (8080) on 8080",), id="P43-contains"),
    pytest.param(entry(ports=[22, 443, 22]), "policy[1].ports[2]", ("22 overlaps ports[0] (22)",), id="P43-dup"),
    pytest.param(entry(ports=[rng(8000, 8009), rng(8020, 8029), rng(8005, 8025)]), "policy[1].ports[2]",
                 ("overlaps ports[0] (8000-8009) on 8005-8009",), id="P43-earliest"),
    pytest.param(entry(ports=[22, 22, 0]), "policy[1].ports[2]", ("0 is outside",), id="items-before-P43"),
    # P-44
    pytest.param(icmp_entry(["8"]), "policy[1].icmp[0]", ("must be a mapping like {type: 8}", "string '8'"), id="P44-str"),
    pytest.param(icmp_entry([8]), "policy[1].icmp[0]", ("number 8",), id="P44-num"),
    pytest.param(icmp_entry([{"code": 4}]), "policy[1].icmp[0]", ("missing 'type'",), id="P44-no-type"),
    pytest.param(icmp_entry([{"type": 8, "kode": 0}]), "policy[1].icmp[0]", ("unknown key 'kode'",), id="P44-unknown"),
    pytest.param(icmp_entry([{"type": 256}]), "policy[1].icmp[0].type", ("256 is outside 0-255",), id="P44-type-256"),
    pytest.param(icmp_entry([{"type": -1}]), "policy[1].icmp[0].type", ("-1 is outside 0-255",), id="P44-type-neg"),
    pytest.param(icmp_entry([{"type": 3, "code": 256}]), "policy[1].icmp[0].code", ("256 is outside 0-255",), id="P44-code-256"),
    pytest.param(icmp_entry([{"type": 3, "code": -1}]), "policy[1].icmp[0].code", ("-1 is outside",), id="P44-code-neg"),
    pytest.param(icmp_entry([{"type": True}]), "policy[1].icmp[0].type", ("boolean True",), id="P44-type-bool"),
    pytest.param(icmp_entry([{"type": "8"}]), "policy[1].icmp[0].type", ("string '8'",), id="P44-type-str"),
    pytest.param(icmp_entry([{"type": None}]), "policy[1].icmp[0].type", ("nothing (null)",), id="P44-type-null"),
    pytest.param(icmp_entry([{"type": 3, "code": None}]), "policy[1].icmp[0].code",
                 ("must be a number 0-255, got nothing (null)", "omit code to allow all codes"), id="P44-code-null"),
    pytest.param(icmp_entry([{"type": 8}, {"type": 300}]), "policy[1].icmp[1].type", ("300 is outside",), id="P44-second"),
    # P-45
    pytest.param(icmp_entry([{"type": 8}, {"type": 8}]), "policy[1].icmp[1]",
                 ("type 8, all codes is already covered by icmp[0] (type 8, all codes)",), id="P45-dup-type"),
    pytest.param(icmp_entry([{"type": 3, "code": 4}, {"type": 3, "code": 4}]), "policy[1].icmp[1]",
                 ("already covered by icmp[0] (type 3 code 4)",), id="P45-dup-code"),
    pytest.param(icmp_entry([{"type": 3}, {"type": 3, "code": 4}]), "policy[1].icmp[1]",
                 ("type 3 code 4 is already covered by icmp[0] (type 3, all codes)",), id="P45-covered"),
    pytest.param(icmp_entry([{"type": 3, "code": 4}, {"type": 3}]), "policy[1].icmp[1]",
                 ("type 3, all codes also covers icmp[0] (type 3 code 4)",), id="P45-covers"),
    pytest.param(icmp_entry([{"type": 3, "code": 4}, {"type": 3, "code": 5}, {"type": 3}]), "policy[1].icmp[2]",
                 ("icmp[0] (type 3 code 4)",), id="P45-earliest"),
    pytest.param(icmp_entry([{"type": 8}, {"type": 8}, {"type": 256}]), "policy[1].icmp[2].type",
                 ("256 is outside",), id="items-before-P45"),
    # §5.1 order: pairs, then proto, then presence
    pytest.param(entry("app", "app", proto="tpc"), "policy[1]", ("within a tier",), id="pairs-before-proto"),
    pytest.param(entry(proto="tpc", ports=[0]), "policy[1].proto", ("'tpc'",), id="proto-before-ports"),
    pytest.param(entry(proto="tpc", icmp=[{"type": 8}]), "policy[1].proto", ("'tpc'",), id="proto-before-presence"),
]


@pytest.mark.parametrize("bad, path, contents", MATCH_ERRORS)
def test_match_error(bad, path, contents):
    check(one([VALID[0], bad]), path, *contents)


def test_spec_sketch_wording():
    assert one([entry(ports=[22, rng(8000, 8099), rng(8050, 8150)])]) == (
        "policy[0].ports[2]: 8050-8150 overlaps ports[1] (8000-8099) on 8050-8099; "
        "split so each port appears once"
    )
    assert one([icmp_entry([{"type": 3}, {"type": 3, "code": 4}])]) == (
        "policy[0].icmp[1]: type 3 code 4 is already covered by icmp[0] "
        "(type 3, all codes); list each ICMP type and code once"
    )


def test_ports_without_proto_one_message():
    bad = without(entry(ports=[0, rng(9, 1)]), "proto")
    msg = one([bad])
    check(msg, "policy[0]", "missing 'proto'")
    assert "ports" not in msg


def test_match_errors_in_entry_order():
    e = errs([entry(ports=[0]), VALID[0], icmp_entry([{"type": 3, "code": None}])])
    assert len(e) == 2
    check(e[0], "policy[0].ports[0]", "0 is outside")
    check(e[1], "policy[2].icmp[0].code", "omit code")


# ------------------------------------------------------------ compile


def test_compile_empty():
    assert compile_policy([], TIERS, True) == ()


def test_compile_order_and_whole_rules():
    # to-list with 2 items x 2 ports (list outer); from-list in another entry;
    # proxy is public and not named web.
    pol = [
        entry("vpn", ["web", "db"], ports=[22, rng(8000, 8001)]),
        entry(["app", "web"], "proxy", proto="udp", ports=[53, 3128]),
        entry("proxy", "internet", ports=[443]),
        icmp_entry([{"type": 8}, {"type": 3, "code": 4}]),
    ]
    assert compile_policy(pol, TIERS, True) == (
        Rule(Vpn(), TierRef("web"), "tcp", PortRange(22, 22), 0),
        Rule(Vpn(), TierRef("web"), "tcp", PortRange(8000, 8001), 0),
        Rule(Vpn(), TierRef("db"), "tcp", PortRange(22, 22), 0),
        Rule(Vpn(), TierRef("db"), "tcp", PortRange(8000, 8001), 0),
        Rule(TierRef("app"), TierRef("proxy"), "udp", PortRange(53, 53), 1),
        Rule(TierRef("app"), TierRef("proxy"), "udp", PortRange(3128, 3128), 1),
        Rule(TierRef("web"), TierRef("proxy"), "udp", PortRange(53, 53), 1),
        Rule(TierRef("web"), TierRef("proxy"), "udp", PortRange(3128, 3128), 1),
        Rule(TierRef("proxy"), Internet(), "tcp", PortRange(443, 443), 2),
        Rule(Vpn(), TierRef("app"), "icmp", IcmpMatch(8, None), 3),
        Rule(Vpn(), TierRef("app"), "icmp", IcmpMatch(3, 4), 3),
    )


SPEC_TIERS = {"web": True, "app": False, "db": False, "proxy": True}
SPEC_POLICY = [
    entry("internet", "web", ports=[443]),
    entry("web", "app", ports=[8080]),
    entry("app", "db", ports=[5432]),
    entry("vpn", ["web", "app", "db"], ports=[22]),
    entry("app", "proxy", ports=[53, 3128]),
    entry("app", "proxy", proto="udp", ports=[53]),
    entry("proxy", "internet", ports=[53, 443]),
    entry("proxy", "internet", proto="udp", ports=[53]),
    icmp_entry([{"type": 8}, {"type": 3, "code": 4}]),
]


def test_compile_spec_section_7():
    assert compile_policy(SPEC_POLICY, SPEC_TIERS, True) == (
        Rule(Internet(), TierRef("web"), "tcp", PortRange(443, 443), 0),
        Rule(TierRef("web"), TierRef("app"), "tcp", PortRange(8080, 8080), 1),
        Rule(TierRef("app"), TierRef("db"), "tcp", PortRange(5432, 5432), 2),
        Rule(Vpn(), TierRef("web"), "tcp", PortRange(22, 22), 3),
        Rule(Vpn(), TierRef("app"), "tcp", PortRange(22, 22), 3),
        Rule(Vpn(), TierRef("db"), "tcp", PortRange(22, 22), 3),
        Rule(TierRef("app"), TierRef("proxy"), "tcp", PortRange(53, 53), 4),
        Rule(TierRef("app"), TierRef("proxy"), "tcp", PortRange(3128, 3128), 4),
        Rule(TierRef("app"), TierRef("proxy"), "udp", PortRange(53, 53), 5),
        Rule(TierRef("proxy"), Internet(), "tcp", PortRange(53, 53), 6),
        Rule(TierRef("proxy"), Internet(), "tcp", PortRange(443, 443), 6),
        Rule(TierRef("proxy"), Internet(), "udp", PortRange(53, 53), 7),
        Rule(Vpn(), TierRef("app"), "icmp", IcmpMatch(8, None), 8),
        Rule(Vpn(), TierRef("app"), "icmp", IcmpMatch(3, 4), 8),
    )


def test_compile_deterministic_and_not_mutating():
    pol = copy.deepcopy(SPEC_POLICY)
    first = compile_policy(pol, SPEC_TIERS, True)
    assert pol == SPEC_POLICY
    assert compile_policy(pol, SPEC_TIERS, True) == first


@pytest.mark.parametrize(
    "pol",
    [
        pytest.param(None, id="P02"),
        pytest.param([entry(action="deny"), entry(dst="ap")], id="entry-errors"),
        pytest.param([entry(ports=[22]), entry(ports=[22])], id="P50"),
    ],
)
def test_compile_raises_with_validate_errors(pol):
    expected = validate_policy(pol, TIERS, True)
    assert expected
    with pytest.raises(ConfigError) as info:
        compile_policy(pol, TIERS, True)
    assert info.value.errors == expected


# ------------------------------------------------------- P-50 / P-51


CROSS_VALID = [
    pytest.param([entry("app", "db"), entry("db", "app")], id="reversed-pair"),
    pytest.param([entry(ports=[53]), entry(proto="udp", ports=[53])], id="other-proto"),
    pytest.param([entry(ports=[rng(8000, 8049)]), entry(ports=[rng(8050, 8150)])], id="adjacent"),
    pytest.param([entry(ports=[rng(8050, 8150)]), entry(ports=[rng(8000, 8049)])], id="adjacent-reversed"),
    pytest.param([entry("vpn", "web", ports=[22]), entry("vpn", "db", ports=[22])], id="other-dst"),
    pytest.param([icmp_entry([{"type": 3, "code": 4}]), icmp_entry([{"type": 3, "code": 3}])], id="icmp-other-code"),
    pytest.param([icmp_entry([{"type": 3}]), icmp_entry([{"type": 4, "code": 0}])], id="icmp-other-type"),
]


@pytest.mark.parametrize("pol", CROSS_VALID)
def test_cross_entry_valid(pol):
    assert errs(pol) == []
    assert len(compile_policy(pol, TIERS, True)) == 2


CROSS_ERRORS = [
    pytest.param(
        [entry("vpn", "web", ports=[22]), entry("app", "db"), entry("vpn", ["app", "web"], ports=[22])],
        "policy[2]: vpn -> web (tcp 22) duplicates policy[0]", id="P50-via-list"),
    pytest.param(
        [icmp_entry([{"type": 8}]), icmp_entry([{"type": 8}])],
        "policy[1]: vpn -> app (icmp type 8, all codes) duplicates policy[0]", id="P50-icmp"),
    pytest.param(
        [entry("vpn", "web", ports=[rng(8000, 8099)]), entry("app", "db"), entry("vpn", "web", ports=[rng(8050, 8150)])],
        "policy[2]: vpn -> web (tcp 8050-8150) overlaps policy[0] (tcp 8000-8099) on 8050-8099; "
        "split so each port is granted once", id="P51-partial"),
    pytest.param(
        [entry(ports=[rng(8050, 8150)]), entry(ports=[rng(8000, 8099)])],
        "policy[1]: app -> db (tcp 8000-8099) overlaps policy[0] (tcp 8050-8150) on 8050-8099; "
        "split so each port is granted once", id="P51-partial-reversed"),
    pytest.param(
        [entry(ports=[rng(8000, 8050)]), entry(ports=[rng(8050, 8150)])],
        "policy[1]: app -> db (tcp 8050-8150) overlaps policy[0] (tcp 8000-8050) on 8050; "
        "split so each port is granted once", id="P51-one-port"),
    pytest.param(
        [entry(ports=[8080]), entry(ports=[rng(8000, 8099)])],
        "policy[1]: app -> db (tcp 8000-8099) overlaps policy[0] (tcp 8080) on 8080; "
        "split so each port is granted once", id="P51-contains"),
    pytest.param(
        [icmp_entry([{"type": 3}]), icmp_entry([{"type": 3, "code": 4}])],
        "policy[1]: vpn -> app (icmp type 3 code 4) is already covered by policy[0] "
        "(icmp type 3, all codes); grant each ICMP type and code once", id="P51-icmp-covered"),
    pytest.param(
        [icmp_entry([{"type": 3, "code": 4}]), icmp_entry([{"type": 3}])],
        "policy[1]: vpn -> app (icmp type 3, all codes) also covers policy[0] "
        "(icmp type 3 code 4); grant each ICMP type and code once", id="P51-icmp-covers"),
    # earliest *entry* wins over the later entry's first rule (443 clashes with policy[1])
    pytest.param(
        [entry(ports=[22]), entry(ports=[443]), entry(ports=[443, 22])],
        "policy[2]: app -> db (tcp 22) duplicates policy[0]", id="earliest-entry"),
]


@pytest.mark.parametrize("pol, msg", CROSS_ERRORS)
def test_cross_entry_error(pol, msg):
    assert errs(pol) == [msg]


def test_cross_entry_one_message_per_later_entry():
    e = errs([entry(ports=[22]), entry(ports=[22]), VALID[0], entry(ports=[22])])
    assert e == [
        "policy[1]: app -> db (tcp 22) duplicates policy[0]",
        "policy[3]: app -> db (tcp 22) duplicates policy[0]",
    ]


def test_malformed_entry_suppresses_cross_entry():
    e = errs([entry(ports=[22]), entry(ports=[22]), entry(action="deny")])
    assert len(e) == 1
    check(e[0], "policy[2].action", "string 'deny'")
    assert not any("duplicates" in m or "overlaps" in m for m in e)


def test_valid_list_compiles():
    assert len(compile_policy(VALID, TIERS, True)) == 11
