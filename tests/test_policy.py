import ast
import copy
import dataclasses
from pathlib import Path

import pytest

from cidrwright import policy
from cidrwright.policy import (
    MAX_PORT_SPAN,
    IcmpMatch,
    Internet,
    PortRange,
    Rule,
    TierRef,
    Vpn,
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
    pytest.param(entry("internet", "internet"), "policy[1]", ("internet -> internet", "within a tier"), id="P20-inet"),
    pytest.param(entry("vpn", "vpn"), "policy[1]", ("vpn -> vpn", "within a tier"), id="P20-vpn"),
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
    check(one([entry("internet", "web")], tiers=tiers), "policy[0]", "tier 'web' is not public")
    check(one([entry("web", "internet")], tiers=tiers), "policy[0]", "tier 'web' is not public")
    assert errs([entry("internet", "edge"), entry("edge", "internet")], tiers=tiers) == []


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
