import copy
import ipaddress

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cidrwright import ipam
from cidrwright.ipam import Config, ConfigError, Tier, allocate
from cidrwright.model import Network, load_network, validate_network
from cidrwright.policy import RESERVED_ENDPOINTS, check_tier_names


def base():
    return {
        # base != 10.0.0.0, AZs not alphabetical
        "vpc": {"cidr": "10.20.0.0/16", "azs": ["b", "a"]},
        "tiers": [
            {"name": "db", "prefix": 26},  # 0, no flag
            {"name": "app", "prefix": 23, "public": False},  # 1
            {"name": "web", "prefix": 24, "public": True},  # 2, public after private
            {"name": "proxy", "prefix": 28, "public": True},  # 3
        ],
        "vpn": {"type": "wireguard"},
        "policy": [],
    }


BASE_CONFIG = Config(
    ipaddress.IPv4Network("10.20.0.0/16"),
    ("b", "a"),
    (Tier("db", 26), Tier("app", 23), Tier("web", 24), Tier("proxy", 28)),
)


def errors_of(data):
    with pytest.raises(ConfigError) as info:
        validate_network(data)
    return info.value.errors


def write(tmp_path, text):
    path = tmp_path / "net.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def placed(result):
    """(tier, az, cidr) for each allocation, in the dict's order."""
    return [(a.tier, a.az, str(a.network)) for a in result.values()]


SPEC_YAML = """\
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
"""


# ------------------------------------------------------------------ M-01


def test_unknown_top_level_key():
    data = base()
    data["polcy"] = []
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "unknown key 'polcy'" in errs[0]
    assert "did you mean 'policy'?" in errs[0]


def test_unknown_key_no_hint():
    data = base()
    data["colour"] = "red"
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "unknown key 'colour'" in errs[0]
    assert "did you mean" not in errs[0]


def test_non_string_unknown_key():
    data = {**base(), 1: "x"}   # non-str key on purpose (YAML allows '1: x')
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "unknown key 1" in errs[0]
    assert "did you mean" not in errs[0]


def test_vpn_and_policy_keys_accepted():
    assert validate_network(base()) == Network(
        BASE_CONFIG, frozenset({"web", "proxy"}), {"type": "wireguard"}, []
    )


@pytest.mark.parametrize(
    "data, got",
    [
        ("just text", "string 'just text'"),
        ([], "a list"),
        (42, "number 42"),
        (True, "boolean True"),
    ],
)
def test_top_level_not_a_mapping(data, got):
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "must be a mapping" in errs[0]
    assert got in errs[0]


def test_none_is_empty_file():
    errs = errors_of(None)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "the file is empty" in errs[0]


@pytest.mark.parametrize("key", ["vpc", "tiers"])
def test_missing_key_reported_once(key):
    data = base()
    del data[key]
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert f"missing required key '{key}'" in errs[0]


def test_empty_mapping_two_missing():
    errs = errors_of({})
    assert len(errs) == 2
    for err, key in zip(errs, ("vpc", "tiers")):
        assert err.startswith("config: ")
        assert f"missing required key '{key}'" in err


def test_unknown_before_missing():
    errs = errors_of({"zzz": 1, "tiers": base()["tiers"]})
    assert len(errs) == 2
    assert errs[0].startswith("config: ")
    assert "unknown key 'zzz'" in errs[0]
    assert errs[1].startswith("config: ")
    assert "missing required key 'vpc'" in errs[1]


# ------------------------------------------------------------------ M-02


def test_public_flags_resolved():
    net = validate_network(base())
    assert net.public == frozenset({"web", "proxy"})
    assert net.config == BASE_CONFIG


def test_public_defaults_false():
    data = base()
    for tier in data["tiers"]:
        tier.pop("public", None)
    net = validate_network(data)
    assert net.public == frozenset()
    assert net.config == BASE_CONFIG


@pytest.mark.parametrize(
    "value, got",
    [
        # quoted string "yes"; unquoted YAML yes is the boolean True, which is accepted
        ("yes", "string 'yes'"),
        ("true", "string 'true'"),
        (1, "number 1"),
        (0, "number 0"),
        (None, "nothing (null)"),
        ([], "a list"),
        ({}, "a mapping"),
    ],
)
def test_public_invalid_value(value, got):
    data = base()
    data["tiers"][1]["public"] = value
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("tiers[1] (app): ")
    assert "public must be true or false" in errs[0]
    assert got in errs[0]


def test_public_stripped_before_ipam():
    assert isinstance(validate_network(base()), Network)
    data = base()
    data["tiers"][2]["public"] = "x"
    errs = errors_of(data)
    assert len(errs) == 1
    assert not any("unknown key 'public'" in e for e in errs)


def test_public_invalid_plus_ipam_error_same_file():
    data = base()
    data["tiers"][0]["prefix"] = 15
    data["tiers"][2]["public"] = "x"
    errs = errors_of(data)
    assert len(errs) == 2
    assert errs[0].startswith("tiers[0] (db): ")
    assert "outside the AWS subnet range" in errs[0]
    assert errs[1].startswith("tiers[2] (web): ")
    assert "public must be true or false" in errs[1]


def test_non_mapping_tier_keeps_index():
    data = base()
    data["tiers"] = [
        "db",
        {"name": "app", "prefix": 23},
        {"name": "x", "prefix": 24, "public": "no"},
    ]
    errs = errors_of(data)
    assert len(errs) == 2
    assert errs[0].startswith("tiers[0]: ")
    assert "must be a mapping" in errs[0]
    assert errs[1].startswith("tiers[2] (x): ")
    assert "public must be true or false" in errs[1]


def test_input_not_mutated():
    d = base()
    d["tiers"][1]["public"] = "x"
    before = copy.deepcopy(d)
    with pytest.raises(ConfigError):
        validate_network(d)
    assert d == before

    ok = base()
    before_ok = copy.deepcopy(ok)
    validate_network(ok)
    assert ok == before_ok


def test_public_does_not_change_allocation(tmp_path):
    net = load_network(write(tmp_path, SPEC_YAML))
    assert placed(allocate(net.config)) == [
        ("app", "a", "10.20.0.0/23"),
        ("app", "b", "10.20.2.0/23"),
        ("web", "a", "10.20.4.0/24"),
        ("web", "b", "10.20.5.0/24"),
        ("db", "a", "10.20.6.0/26"),
        ("db", "b", "10.20.6.64/26"),
        ("proxy", "a", "10.20.6.128/28"),
        ("proxy", "b", "10.20.6.144/28"),
    ]


# ------------------------------------------------------------------ M-03


def test_vpn_mapping_accepted():
    data = base()
    data["vpn"] = {"type": "wireguard", "peers": ["x"]}
    assert validate_network(data).vpn == {"type": "wireguard", "peers": ["x"]}


def test_vpn_contents_not_validated():
    data = base()
    data["vpn"] = {"anything": [1, None]}
    assert validate_network(data).vpn == {"anything": [1, None]}


def test_vpn_absent_is_none():
    data = base()
    del data["vpn"]
    assert validate_network(data).vpn is None


@pytest.mark.parametrize(
    "value, got",
    [
        ([], "a list"),
        ("wg", "string 'wg'"),
        (None, "nothing (null)"),
        (5, "number 5"),
        (True, "boolean True"),
    ],
)
def test_vpn_not_a_mapping(value, got):
    data = base()
    data["vpn"] = value
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("vpn: ")
    assert "must be a mapping" in errs[0]
    assert got in errs[0]


# ------------------------------------------------------------------ P-01


@pytest.mark.parametrize("name", ["internet", "vpn"])
def test_reserved_tier_name(name):
    data = base()
    data["tiers"][2]["name"] = name
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith(f"tiers[2] ({name}): ")
    assert "reserved policy endpoint" in errs[0]
    assert f"'{name}'" in errs[0]


@pytest.mark.parametrize("name", ["internets", "vpn2", "my-vpn", "internet-gw"])
def test_reserved_near_misses_accepted(name):
    data = base()
    data["tiers"][2]["name"] = name
    net = validate_network(data)
    assert net.config.tiers[2].name == name


def test_both_reserved_in_index_order():
    data = base()
    data["tiers"][0]["name"] = "vpn"
    data["tiers"][3]["name"] = "internet"
    errs = errors_of(data)
    assert len(errs) == 2
    assert errs[0].startswith("tiers[0] (vpn): ")
    assert errs[1].startswith("tiers[3] (internet): ")


def test_check_tier_names_direct():
    assert check_tier_names([]) == []
    assert check_tier_names((x for x in [(0, "web")])) == []
    assert check_tier_names([(0, "internet")]) == [
        "tiers[0] (internet): 'internet' is a reserved policy endpoint; "
        "rename the tier (e.g. 'edge')"
    ]
    star = check_tier_names([(3, "*")])
    assert len(star) == 1
    assert star[0].startswith("tiers[3] (*): ")
    mixed = check_tier_names([(0, "web"), (1, "vpn")])
    assert len(mixed) == 1
    assert mixed[0].startswith("tiers[1] (vpn): ")


def test_reserved_endpoints_constant():
    assert RESERVED_ENDPOINTS == ("internet", "vpn", "*")


# ------------------------------------------------------ ordering and merge


_ORDER_ENTRIES = {
    "extra": [("config", "unknown key 'extra'")],
    "vpc": [("vpc.cidr", "use 10.20.0.0/16")],
    "tiers": [
        ("tiers[0] (db)", "outside the AWS subnet range"),
        ("tiers[1] (internet)", "reserved policy endpoint"),
        ("tiers[1] (internet)", "string 'yes'"),
        ("tiers[2] (app)", "number 1"),
    ],
    "vpn": [("vpn", "must be a mapping")],
}


@pytest.mark.parametrize(
    "order",
    [
        pytest.param(("vpc", "tiers", "vpn", "extra"), id="vpc-tiers-vpn-extra"),
        pytest.param(("vpn", "tiers", "vpc", "extra"), id="vpn-tiers-vpc-extra"),
    ],
)
def test_many_mistakes_in_document_order(order):
    data = {
        "vpc": {"cidr": "10.20.0.1/16", "azs": ["a"]},
        "tiers": [
            {"name": "db", "prefix": 15},
            {"name": "internet", "prefix": 24, "public": "yes"},
            {"name": "app", "prefix": 24, "public": 1},
        ],
        "vpn": [],
        "extra": 1,
    }
    data = {k: data[k] for k in order}
    # Unknown keys are reported first; the rest follows file order.
    expected = list(_ORDER_ENTRIES["extra"])
    for key in order:
        if key != "extra":
            expected += _ORDER_ENTRIES[key]
    with pytest.raises(ConfigError) as info:
        validate_network(data)
    exc = info.value
    errs = exc.errors
    assert len(errs) == 7
    assert len(errs) == len(expected)
    for err, (location, content) in zip(errs, expected):
        assert err.startswith(location + ": ")
        assert content in err
    assert len(str(exc).splitlines()) == len(errs)


def test_same_tier_ipam_before_model():
    data = {
        "vpc": {"cidr": "10.20.0.0/16", "azs": ["a"]},
        "tiers": [{"name": "vpn", "prefix": 29, "public": "x"}],
    }
    errs = errors_of(data)
    assert len(errs) == 3
    for err in errs:
        assert err.startswith("tiers[0] (vpn): ")
    assert "outside the AWS subnet range" in errs[0]
    assert "reserved policy endpoint" in errs[1]
    assert "public must be true or false" in errs[2]


def test_capacity_error_last():
    data = {
        "vpc": {"cidr": "10.20.0.0/24", "azs": ["a", "b", "c", "d"]},
        "tiers": [
            {"name": "db", "prefix": 26, "public": "x"},
            {"name": "tiny", "prefix": 28},
        ],
    }
    errs = errors_of(data)
    assert len(errs) == 2
    assert errs[0].startswith("tiers[0] (db): ")
    assert "public must be" in errs[0]
    assert errs[1].startswith("config: ")
    assert "capacity" in errs[1]
    assert "320" in errs[1]
    assert "256" in errs[1]


def test_ipam_errors_surface_unchanged():
    d = {
        "vpc": {"cidr": "10.20.0.1/16", "azs": ["a"]},
        "tiers": [{"name": "w", "prefx": 24}],
    }
    with pytest.raises(ConfigError) as info:
        ipam.validate(d)
    expected = info.value.errors
    assert len(expected) == 3
    assert errors_of(d) == expected


# ------------------------------------------------------ valid files, loading


def test_spec_example_network(tmp_path):
    net = load_network(write(tmp_path, SPEC_YAML))
    assert net.config == Config(
        ipaddress.IPv4Network("10.20.0.0/16"),
        ("a", "b"),
        (Tier("web", 24), Tier("app", 23), Tier("db", 26), Tier("proxy", 28)),
    )
    assert net.public == frozenset({"web", "proxy"})
    assert net.vpn == {
        "type": "wireguard",
        "client_pool": "10.99.0.0/24",
        "peers": ["bruce-laptop", "bruce-phone"],
    }
    assert isinstance(net.policy_raw, list)
    assert len(net.policy_raw) == 9
    assert net.policy_raw[0] == {
        "action": "allow",
        "from": "internet",
        "to": "web",
        "proto": "tcp",
        "ports": [443],
    }
    assert net.policy_raw[3]["to"] == ["web", "app", "db"]
    assert net.policy_raw[8]["icmp"] == [{"type": 8}, {"type": 3, "code": 4}]


def test_policy_absent_is_none():
    data = base()
    del data["policy"]
    assert validate_network(data).policy_raw is None


def test_policy_raw_not_validated_in_part_a():
    # P-02 (policy must be a list) is Part B; Part A keeps the value as is.
    data = base()
    data["policy"] = 5
    assert validate_network(data).policy_raw == 5


@pytest.mark.parametrize(
    "text, line, key",
    [
        pytest.param(
            "vpc:\n"
            "  cidr: 10.20.0.0/16\n"
            "  azs: [a]\n"
            "tiers:\n"
            "  - {name: web, prefix: 24}\n"
            "vpn: {}\n"
            "vpn: {}\n",
            7,
            "vpn",
            id="top-level",
        ),
        pytest.param(
            "vpc:\n"
            "  cidr: 10.20.0.0/16\n"
            "  azs: [a]\n"
            "  azs: [b]\n"
            "tiers:\n"
            "  - {name: web, prefix: 24}\n",
            4,
            "azs",
            id="vpc",
        ),
        pytest.param(
            "vpc:\n"
            "  cidr: 10.20.0.0/16\n"
            "  azs: [a]\n"
            "tiers:\n"
            "  - name: web\n"
            "    prefix: 24\n"
            "    public: true\n"
            "    public: false\n",
            8,
            "public",
            id="tier-public",
        ),
    ],
)
def test_load_duplicate_keys(tmp_path, text, line, key):
    path = write(tmp_path, text)
    with pytest.raises(ConfigError) as info:
        load_network(path)
    message = str(info.value)
    assert f"{path}:{line}:" in message
    assert f"duplicate key '{key}'" in message


def test_load_invalid_yaml(tmp_path):
    path = write(tmp_path, "vpc:\n  cidr: 10.20.0.0/16\n  azs: a: b\n")
    with pytest.raises(ConfigError) as info:
        load_network(path)
    message = str(info.value)
    assert f"{path}:3:" in message
    assert "invalid YAML" in message
    assert "mapping values are not allowed here" in message


def test_load_python_tag_rejected(tmp_path):
    path = write(tmp_path, "vpc: !!python/name:builtins.len\ntiers: []\n")
    with pytest.raises(ConfigError) as info:
        load_network(path)
    message = str(info.value)
    assert f"{path}:1:" in message
    assert "invalid YAML" in message
    assert "could not determine a constructor" in message


def test_load_not_utf8(tmp_path):
    path = tmp_path / "net.yaml"
    path.write_bytes(b"vpc: \xff\xfe\n")
    with pytest.raises(ConfigError) as info:
        load_network(path)
    assert info.value.errors == [f"{path}: not valid UTF-8 text"]


def test_load_empty_file(tmp_path):
    path = write(tmp_path, "")
    with pytest.raises(ConfigError) as info:
        load_network(path)
    errs = info.value.errors
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "the file is empty" in errs[0]


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_network(tmp_path / "nope.yaml")


def test_load_model_error_via_file(tmp_path):
    path = write(tmp_path, SPEC_YAML + "polcy: []\n")
    with pytest.raises(ConfigError) as info:
        load_network(path)
    errs = info.value.errors
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "did you mean 'policy'?" in errs[0]


# ------------------------------------------------------------ properties

# Drawn in arbitrary order (not sorted); reserved words excluded.
NAME = st.from_regex(r"[a-z][a-z0-9_-]{0,7}", fullmatch=True).filter(
    lambda n: n not in RESERVED_ENDPOINTS
)


@st.composite
def valid_net(draw, min_tiers=1):
    """A valid network dict: VPC 10.n.0.0/16, tiers /24 to /28, mixed flags."""
    n = draw(st.integers(0, 255))
    azs = draw(st.lists(NAME, min_size=1, max_size=2, unique=True))
    names = draw(st.lists(NAME, min_size=min_tiers, max_size=4, unique=True))
    tiers = []
    for name in names:
        tier = {"name": name, "prefix": draw(st.integers(24, 28))}
        flag = draw(st.sampled_from([None, True, False]))  # None = key absent
        if flag is not None:
            tier["public"] = flag
        tiers.append(tier)
    return {"vpc": {"cidr": f"10.{n}.0.0/16", "azs": azs}, "tiers": tiers}


@given(valid_net())
def test_prop_public_roundtrip(data):
    net = validate_network(data)
    assert net.public == frozenset(
        t["name"] for t in data["tiers"] if t.get("public") is True
    )
    assert net.config.tiers == tuple(Tier(t["name"], t["prefix"]) for t in data["tiers"])
    assert net.config.vpc == ipaddress.IPv4Network(data["vpc"]["cidr"])
    assert net.config.azs == tuple(data["vpc"]["azs"])


BAD_PUBLIC = {
    "x": ("x", "string 'x'"),
    "one": (1, "number 1"),
    "null": (None, "nothing (null)"),
}


@st.composite
def broken_net(draw):
    """(data, expected errors): a valid network with some mistakes added."""
    data = draw(valid_net(min_tiers=2))
    tiers = data["tiers"]
    idxs = list(range(len(tiers)))
    vpn_i = draw(st.one_of(st.none(), st.sampled_from(idxs)))
    inet_i = draw(st.one_of(st.none(), st.sampled_from([i for i in idxs if i != vpn_i])))
    if vpn_i is not None:
        tiers[vpn_i]["name"] = "vpn"
    if inet_i is not None:
        tiers[inet_i]["name"] = "internet"
    bad_prefix = draw(st.booleans())
    if bad_prefix:
        tiers[0]["prefix"] = 15
    bad = {}
    for i, tier in enumerate(tiers):
        choice = draw(st.sampled_from(["keep", *BAD_PUBLIC]))
        if choice != "keep":
            value, got = BAD_PUBLIC[choice]
            tier["public"] = value
            bad[i] = got
    expected = []
    for i, tier in enumerate(tiers):
        name = tier["name"]
        if i == 0 and bad_prefix:
            expected.append(
                f"tiers[0] ({name}): prefix /15 is outside the AWS subnet range /16 to /28"
            )
        if name in ("vpn", "internet"):
            expected.append(
                f"tiers[{i}] ({name}): {name!r} is a reserved policy endpoint; "
                "rename the tier (e.g. 'edge')"
            )
        if i in bad:
            expected.append(
                f"tiers[{i}] ({name}): public must be true or false, got {bad[i]}"
            )
    return data, expected


@given(broken_net())
def test_prop_no_error_lost(case):
    data, expected = case
    if expected:
        assert errors_of(data) == expected
    else:
        assert isinstance(validate_network(data), Network)


_LEAVES = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(),
    st.text(max_size=12),
    st.sampled_from(["10.20.0.0/16", "10.20.0.1/16", "a", "web", "no", "internet", "vpn"]),
)
_KEYS = st.one_of(
    st.sampled_from(
        ["vpc", "tiers", "cidr", "azs", "name", "prefix", "hosts", "vpn", "policy", "public"]
    ),
    st.text(max_size=5),
    st.integers(),
    st.booleans(),
    st.none(),
)
_NESTED = st.recursive(
    _LEAVES,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_KEYS, children, max_size=4),
    ),
    max_leaves=25,
)


@given(_NESTED)
def test_prop_fuzz_validate_network(data):
    try:
        result = validate_network(data)
    except ConfigError:
        return
    assert isinstance(result, Network)


def test_missing_vpc_reported_before_tier_errors():
    data = base()
    del data["vpc"]
    data["tiers"][1]["public"] = "x"
    errs = errors_of(data)
    assert errs[0].startswith("config: ")
    assert "missing" in errs[0] and "vpc" in errs[0]
    assert "public must be true or false" in errs[-1]


def test_missing_tiers_reported_before_vpc_errors():
    data = base()
    del data["tiers"]
    data["vpc"]["cidr"] = "10.0.0.0/33"
    errs = errors_of(data)
    assert errs[0].startswith("config: ")
    assert "missing" in errs[0] and "tiers" in errs[0]
    assert errs[1].startswith("vpc")
    