import ipaddress

import pytest

from cidrwright.ipam import Config, ConfigError, Tier, allocate, load_config, validate


def base():
    return {
        "vpc": {"cidr": "10.0.0.0/16", "azs": ["a", "b", "c"]},
        "tiers": [
            {"name": "public", "prefix": 24},
            {"name": "private", "hosts": 400},
            {"name": "database", "prefix": 26},
        ],
    }


def errors_of(data):
    with pytest.raises(ConfigError) as info:
        validate(data)
    return info.value.errors


def one_tier(tier, cidr="10.0.0.0/16", azs=("a",)):
    return {"vpc": {"cidr": cidr, "azs": list(azs)}, "tiers": [tier]}


EXAMPLE_YAML = """\
vpc:
  cidr: 10.0.0.0/16
  azs: [a, b, c]
tiers:
  - {name: public,   prefix: 24}
  - {name: private,  hosts: 400}
  - {name: database, prefix: 26}
"""

EXAMPLE_CONFIG = Config(
    ipaddress.IPv4Network("10.0.0.0/16"),
    ("a", "b", "c"),
    (Tier("public", 24), Tier("private", 23), Tier("database", 26)),
)


def write(tmp_path, text):
    path = tmp_path / "net.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def placed(result):
    """(tier, az, cidr) for each allocation, in the dict's order."""
    return [(a.tier, a.az, str(a.network)) for a in result.values()]


def test_example_validates():
    assert validate(base()) == EXAMPLE_CONFIG


def test_load_config_example(tmp_path):
    path = write(tmp_path, EXAMPLE_YAML)
    assert load_config(path) == EXAMPLE_CONFIG


@pytest.mark.parametrize(
    "hosts, prefix", [(400, 23), (1, 28), (11, 28), (12, 27), (5000, 19)]
)
def test_hosts_resolution(hosts, prefix):
    config = validate(one_tier({"name": "web", "hosts": hosts}))
    assert config.tiers[0].prefix == prefix


@pytest.mark.parametrize("cidr, prefix", [("10.0.0.0/16", 16), ("10.0.0.0/28", 28)])
def test_vpc_prefix_edges_accepted(cidr, prefix):
    config = validate(one_tier({"name": "web", "prefix": 28}, cidr=cidr))
    assert config.vpc == ipaddress.IPv4Network(cidr)
    assert config.vpc.prefixlen == prefix
    assert config.tiers == (Tier("web", 28),)


@pytest.mark.parametrize(
    "cidr, prefix",
    [("10.0.0.0/16", 16), ("10.0.0.0/16", 28), ("10.0.0.0/20", 20)],
)
def test_tier_prefix_edges_accepted(cidr, prefix):
    config = validate(one_tier({"name": "web", "prefix": prefix}, cidr=cidr))
    assert config.vpc == ipaddress.IPv4Network(cidr)
    assert config.tiers == (Tier("web", prefix),)


@pytest.mark.parametrize(
    "name, az",
    [("web-1_a2", "az-1_b2"), ("a" * 32, "a" * 64), ("a", "a")],
)
def test_name_and_az_patterns_accepted(name, az):
    config = validate(one_tier({"name": name, "prefix": 24}, azs=(az,)))
    assert config.tiers[0].name == name
    assert config.azs == (az,)


def test_hosts_too_big_for_vpc():
    data = {
        "vpc": {"cidr": "10.0.0.0/20", "azs": ["a"]},
        "tiers": [
            {"name": "public", "prefix": 24},
            {"name": "private", "hosts": 5000},
        ],
    }
    errs = errors_of(data)
    assert len(errs) == 1
    assert "tiers[1] (private)" in errs[0]
    assert "/19" in errs[0]
    assert "/20" in errs[0]


def test_many_mistakes_reported_together():
    data = {
        "vpc": {"cidr": "10.0.0.1/16", "azs": ["a", False, "a"]},
        "tiers": [
            {"name": "public", "prefx": 24},
            {"name": "Private", "hosts": 0},
            {"name": "db", "prefix": True},
        ],
        "extra": 1,
    }
    with pytest.raises(ConfigError) as info:
        validate(data)
    exc = info.value
    errs = exc.errors
    expected = [
        ("config", "unknown key 'extra'"),
        ("vpc.cidr", "use 10.0.0.0/16"),
        ("vpc.azs[1]", "put it in quotes"),
        ("vpc.azs[2]", "duplicate AZ 'a'"),
        ("tiers[0] (public)", "did you mean 'prefix'?"),
        ("tiers[0] (public)", "needs 'prefix' or 'hosts'"),
        ("tiers[1]", "name 'Private' must start with a lowercase letter"),
        ("tiers[1]", "hosts must be a whole number of at least 1"),
        ("tiers[2] (db)", "got boolean True"),
    ]
    assert len(errs) == len(expected)
    for err, (location, content) in zip(errs, expected):
        assert err.startswith(location + ": ")
        assert content in err
    assert len(str(exc).splitlines()) == len(errs)


def test_capacity_exactly_full_ok():
    data = one_tier(
        {"name": "db", "prefix": 26}, cidr="10.0.0.0/24", azs=("a", "b", "c", "d")
    )
    config = validate(data)
    assert config.vpc == ipaddress.IPv4Network("10.0.0.0/24")
    assert config.azs == ("a", "b", "c", "d")
    assert config.tiers == (Tier("db", 26),)


def test_capacity_exceeded():
    data = one_tier(
        {"name": "db", "prefix": 26}, cidr="10.0.0.0/24", azs=("a", "b", "c", "d")
    )
    data["tiers"].append({"name": "tiny", "prefix": 28})
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "capacity" in errs[0]
    assert "320" in errs[0]
    assert "256" in errs[0]


def test_bool_prefix_rejected():
    errs = errors_of(one_tier({"name": "web", "prefix": True}))
    assert len(errs) == 1
    assert "tiers[0] (web)" in errs[0]
    assert "prefix" in errs[0]
    assert "boolean" in errs[0]


def test_prefix_typo_hint():
    errs = errors_of(one_tier({"name": "web", "prefx": 24}))
    assert len(errs) == 2
    assert errs[0].startswith("tiers[0] (web): ")
    assert "unknown key 'prefx'" in errs[0]
    assert "did you mean 'prefix'?" in errs[0]


def test_unknown_key_without_close_match_has_no_hint():
    top = base()
    top["colour"] = "red"
    tier = one_tier({"name": "web", "prefix": 24, "colour": "red"})
    for data, location in ((top, "config"), (tier, "tiers[0] (web)")):
        errs = errors_of(data)
        assert len(errs) == 1
        assert errs[0].startswith(f"{location}: ")
        assert "unknown key 'colour'" in errs[0]
        assert "did you mean" not in errs[0]


def test_host_bits_suggests_network():
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, cidr="10.0.0.1/16"))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr")
    assert "10.0.0.0/16" in errs[0]


@pytest.mark.parametrize(
    "cidr, expected",
    [
        pytest.param("10.0.0.0/255.255.0.0", "write it as 10.0.0.0/16", id="netmask"),
        pytest.param("10.0.0.0/0.0.255.255", "write it as 10.0.0.0/16", id="hostmask"),
        pytest.param(
            "10.0.0.0", "add a prefix length, e.g. 10.0.0.0/16", id="bare-address"
        ),
        pytest.param(
            "10.0.0.0/16\n",
            "write it as a.b.c.d/nn, e.g. 10.0.0.0/16",
            id="trailing-newline",
        ),
    ],
)
def test_cidr_forms_rejected(cidr, expected):
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, cidr=cidr))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr: ")
    assert expected in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [
        (167772160, "number 167772160"),
        (["10.0.0.0/16"], "a list"),
        (True, "boolean True"),
        (None, "nothing (null)"),
    ],
)
def test_cidr_not_a_string(value, got):
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, cidr=value))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr: ")
    assert "must be a string" in errs[0]
    assert got in errs[0]


@pytest.mark.parametrize(
    "cidr, prefix",
    [("10.0.0.0/15", 15), ("10.0.0.0/12", 12), ("10.0.0.0/29", 29)],
)
def test_vpc_prefix_out_of_range(cidr, prefix):
    errs = errors_of(one_tier({"name": "web", "prefix": 28}, cidr=cidr))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr: ")
    assert f"prefix /{prefix} is outside the AWS VPC range /16 to /28" in errs[0]


@pytest.mark.parametrize(
    "cidr, excluded, why",
    [
        ("0.0.0.0/16", "0.0.0.0/8", "'this network'"),
        ("127.0.0.0/16", "127.0.0.0/8", "loopback"),
        ("169.254.0.0/16", "169.254.0.0/16", "link-local"),
        ("224.0.0.0/16", "224.0.0.0/4", "multicast"),
        ("240.0.0.0/16", "240.0.0.0/4", "reserved"),
    ],
)
def test_excluded_ranges(cidr, excluded, why):
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, cidr=cidr))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr: ")
    assert f"overlaps {excluded} ({why})" in errs[0]


def test_public_range_allowed():
    validate(one_tier({"name": "web", "prefix": 24}, cidr="8.8.0.0/16"))


@pytest.mark.parametrize("prefix", [18, 19])
def test_tier_prefix_vs_vpc(prefix):
    errs = errors_of(one_tier({"name": "web", "prefix": prefix}, cidr="10.0.0.0/20"))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert f"prefix /{prefix} is larger than the VPC /20" in errs[0]


def test_prefix_vs_vpc_skipped_when_vpc_invalid():
    errs = errors_of(one_tier({"name": "web", "prefix": 20}, cidr="10.0.0.0/29"))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.cidr: ")
    assert "prefix /29 is outside the AWS VPC range" in errs[0]


@pytest.mark.parametrize("prefix", [15, 29])
def test_tier_prefix_out_of_range(prefix):
    errs = errors_of(one_tier({"name": "web", "prefix": prefix}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert f"prefix /{prefix} is outside the AWS subnet range" in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [("24", "string '24'"), (24.0, "number 24.0"), (None, "nothing (null)")],
)
def test_tier_prefix_wrong_type(value, got):
    errs = errors_of(one_tier({"name": "web", "prefix": value}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert "prefix must be an integer" in errs[0]
    assert got in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [
        (True, "boolean True"),
        ("10", "string '10'"),
        (10.5, "number 10.5"),
        (-5, "number -5"),
        (0, "number 0"),
    ],
)
def test_bad_hosts_rejected(value, got):
    errs = errors_of(one_tier({"name": "web", "hosts": value}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert "hosts must be a whole number of at least 1" in errs[0]
    assert got in errs[0]


def test_prefix_and_hosts_both():
    errs = errors_of(one_tier({"name": "web", "prefix": 24, "hosts": 100}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert "not both" in errs[0]


def test_prefix_and_hosts_neither():
    errs = errors_of(one_tier({"name": "web"}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0] (web): ")
    assert "needs 'prefix' or 'hosts'" in errs[0]


def test_duplicate_az_and_tier_name():
    errs = errors_of(
        one_tier({"name": "web", "prefix": 24}, azs=("a", "b", "a"))
    )
    assert len(errs) == 1
    assert errs[0].startswith("vpc.azs[2]")

    data = one_tier({"name": "web", "prefix": 24})
    data["tiers"].append({"name": "web", "prefix": 24})
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("tiers[1]")
    assert "duplicate" in errs[0]


@pytest.mark.parametrize("name", ["Web", "web tier", "1web", "web\n", "a" * 33])
def test_bad_name_pattern(name):
    errs = errors_of(one_tier({"name": name, "prefix": 24}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0]: name")


BOOL_HINT = "YAML 1.1 reads unquoted words"
NUM_HINT = "YAML reads unquoted numbers as numbers, so put it in quotes"


@pytest.mark.parametrize("value, hint", [(True, BOOL_HINT), (123, NUM_HINT)])
def test_unquoted_name_quote_hint(value, hint):
    errs = errors_of(one_tier({"name": value, "prefix": 24}))
    assert len(errs) == 1
    assert errs[0].startswith("tiers[0]: name must be a string")
    assert hint in errs[0]


@pytest.mark.parametrize(
    "value, hint", [(False, BOOL_HINT), (True, BOOL_HINT), (1, NUM_HINT)]
)
def test_unquoted_az_quote_hint(value, hint):
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, azs=("a", value)))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.azs[1]: ")
    assert "must be a string" in errs[0]
    assert hint in errs[0]


@pytest.mark.parametrize("az", ["A", "1a", "a.b", "a b", "a" * 65])
def test_bad_az_pattern(az):
    errs = errors_of(one_tier({"name": "web", "prefix": 24}, azs=(az,)))
    assert len(errs) == 1
    assert errs[0].startswith("vpc.azs[0]: ")
    assert "must start with a lowercase letter" in errs[0]


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


def test_empty_mapping_reports_both_missing_keys():
    errs = errors_of({})
    assert len(errs) == 2
    for err, key in zip(errs, ("vpc", "tiers")):
        assert err.startswith("config: ")
        assert f"'{key}'" in err
        assert "missing" in err


@pytest.mark.parametrize("key", ["vpc", "tiers"])
def test_one_top_level_key_missing(key):
    data = base()
    del data[key]
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert f"missing required key '{key}'" in errs[0]


@pytest.mark.parametrize("key", ["cidr", "azs"])
def test_vpc_key_missing(key):
    data = base()
    del data["vpc"][key]
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("vpc: ")
    assert f"missing required key '{key}'" in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [
        ("10.0.0.0/16", "string '10.0.0.0/16'"),
        (["a"], "a list"),
        (None, "nothing (null)"),
    ],
)
def test_vpc_not_a_mapping(value, got):
    data = base()
    data["vpc"] = value
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("vpc: ")
    assert "must be a mapping" in errs[0]
    assert got in errs[0]


def test_vpc_unknown_key():
    data = base()
    data["vpc"]["region"] = "eu"
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("vpc: ")
    assert "unknown key 'region'" in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [
        ("abc", "string 'abc'"),
        (5, "number 5"),
        ({"a": 1}, "a mapping"),
        (None, "nothing (null)"),
    ],
)
def test_azs_not_a_list(value, got):
    data = base()
    data["vpc"]["azs"] = value
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("vpc.azs: ")
    assert "must be a list" in errs[0]
    assert got in errs[0]


@pytest.mark.parametrize(
    "value, got",
    [
        ("web", "string 'web'"),
        ({"name": "web"}, "a mapping"),
        (None, "nothing (null)"),
    ],
)
def test_tiers_not_a_list(value, got):
    data = base()
    data["tiers"] = value
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("tiers: ")
    assert "must be a list of tiers" in errs[0]
    assert got in errs[0]


@pytest.mark.parametrize(
    "item, got",
    [
        ("web", "string 'web'"),
        (24, "number 24"),
        (["web"], "a list"),
        (None, "nothing (null)"),
    ],
)
def test_tier_not_a_mapping(item, got):
    data = base()
    data["tiers"][1] = item
    errs = errors_of(data)
    assert len(errs) == 1
    assert errs[0].startswith("tiers[1]: ")
    assert "must be a mapping" in errs[0]
    assert got in errs[0]


def test_empty_azs_and_tiers():
    errs = errors_of({"vpc": {"cidr": "10.0.0.0/16", "azs": []}, "tiers": []})
    assert len(errs) == 2
    assert errs[0].startswith("vpc.azs: ")
    assert "at least one AZ" in errs[0]
    assert errs[1].startswith("tiers: ")
    assert "at least one tier" in errs[1]


def test_config_error_is_value_error():
    assert issubclass(ConfigError, ValueError)
    exc = ConfigError(["x", "y"])
    assert exc.errors == ["x", "y"]
    assert str(exc) == "x\ny"


@pytest.mark.parametrize(
    "text, line, key",
    [
        pytest.param(
            "vpc:\n"
            "  cidr: 10.0.0.0/16\n"
            "  azs: [a]\n"
            "tiers:\n"
            "  - {name: web, prefix: 24}\n"
            "tiers: []\n",
            6,
            "tiers",
            id="top-level",
        ),
        pytest.param(
            "vpc:\n"
            "  cidr: 10.0.0.0/16\n"
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
            "  cidr: 10.0.0.0/16\n"
            "  azs: [a]\n"
            "tiers:\n"
            "  - name: web\n"
            "    prefix: 24\n"
            "    prefix: 25\n",
            7,
            "prefix",
            id="tier",
        ),
    ],
)
def test_load_duplicate_keys(tmp_path, text, line, key):
    path = write(tmp_path, text)
    with pytest.raises(ConfigError) as info:
        load_config(path)
    message = str(info.value)
    assert f"{path}:{line}:" in message
    assert f"duplicate key '{key}'" in message


def test_load_unquoted_no_az(tmp_path):
    path = write(
        tmp_path,
        "vpc:\n"
        "  cidr: 10.0.0.0/16\n"
        "  azs: [a, no]\n"
        "tiers:\n"
        "  - {name: web, prefix: 24}\n",
    )
    with pytest.raises(ConfigError) as info:
        load_config(path)
    errs = info.value.errors
    assert len(errs) == 1
    assert errs[0].startswith("vpc.azs[1]: ")
    assert "put it in quotes" in errs[0]


def test_load_empty_file(tmp_path):
    path = write(tmp_path, "")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    errs = info.value.errors
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "the file is empty" in errs[0]


def test_load_syntax_error(tmp_path):
    path = write(tmp_path, "vpc:\n  cidr: 10.0.0.0/16\n  azs: a: b\n")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    message = str(info.value)
    assert f"{path}:3:" in message
    assert "invalid YAML" in message
    assert "mapping values are not allowed here" in message


def test_load_rejects_python_tag(tmp_path):
    path = write(tmp_path, "vpc: !!python/name:builtins.len\ntiers: []\n")
    with pytest.raises(ConfigError) as info:
        load_config(path)
    message = str(info.value)
    assert f"{path}:1:" in message
    assert "invalid YAML" in message
    assert "could not determine a constructor" in message


def test_load_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


# ------------------------------------------------------------ allocation


def test_allocate_example_table():
    result = allocate(validate(base()))
    expected = [
        ("private", "a", "10.0.0.0/23", 507),
        ("private", "b", "10.0.2.0/23", 507),
        ("private", "c", "10.0.4.0/23", 507),
        ("public", "a", "10.0.6.0/24", 251),
        ("public", "b", "10.0.7.0/24", 251),
        ("public", "c", "10.0.8.0/24", 251),
        ("database", "a", "10.0.9.0/26", 59),
        ("database", "b", "10.0.9.64/26", 59),
        ("database", "c", "10.0.9.128/26", 59),
    ]
    assert list(result) == [(tier, az) for tier, az, _, _ in expected]
    got = [(a.tier, a.az, str(a.network), a.usable_hosts) for a in result.values()]
    assert got == expected


def test_allocate_m1_regression():
    data = {
        "vpc": {"cidr": "10.0.0.0/16", "azs": ["a", "b", "c", "d", "e"]},
        "tiers": [
            {"name": "public", "prefix": 24},
            {"name": "private", "prefix": 24},
            {"name": "database", "prefix": 24},
        ],
    }
    result = allocate(validate(data))
    # Same size: YAML tier order (public, private, database), not alphabetical.
    expected = [
        ("public", "a", "10.0.0.0/24"),
        ("public", "b", "10.0.1.0/24"),
        ("public", "c", "10.0.2.0/24"),
        ("public", "d", "10.0.3.0/24"),
        ("public", "e", "10.0.4.0/24"),
        ("private", "a", "10.0.5.0/24"),
        ("private", "b", "10.0.6.0/24"),
        ("private", "c", "10.0.7.0/24"),
        ("private", "d", "10.0.8.0/24"),
        ("private", "e", "10.0.9.0/24"),
        ("database", "a", "10.0.10.0/24"),
        ("database", "b", "10.0.11.0/24"),
        ("database", "c", "10.0.12.0/24"),
        ("database", "d", "10.0.13.0/24"),
        ("database", "e", "10.0.14.0/24"),
    ]
    assert placed(result) == expected
    assert list(result) == [(t, az) for t, az, _ in expected]
    networks = [a.network for a in result.values()]
    assert len(set(networks)) == 15
    assert networks.count(ipaddress.IPv4Network("10.0.4.0/24")) == 1


def test_allocate_az_yaml_order_not_alphabetical():
    data = {
        "vpc": {"cidr": "10.0.0.0/16", "azs": ["c", "a", "b"]},
        "tiers": [
            {"name": "web", "prefix": 24},
            {"name": "db", "prefix": 26},
        ],
    }
    result = allocate(validate(data))
    assert placed(result) == [
        ("web", "c", "10.0.0.0/24"),
        ("web", "a", "10.0.1.0/24"),
        ("web", "b", "10.0.2.0/24"),
        ("db", "c", "10.0.3.0/26"),
        ("db", "a", "10.0.3.64/26"),
        ("db", "b", "10.0.3.128/26"),
    ]


def test_allocate_mixed_sizes_aligned():
    vpc = ipaddress.IPv4Network("10.0.16.0/20")  # does not start at 10.0.0.0
    data = {
        "vpc": {"cidr": str(vpc), "azs": ["a", "b", "c"]},
        "tiers": [  # YAML order: smallest first
            {"name": "db", "prefix": 26},
            {"name": "web", "prefix": 24},
            {"name": "app", "prefix": 23},
        ],
    }
    result = allocate(validate(data))
    assert placed(result) == [
        ("app", "a", "10.0.16.0/23"),
        ("app", "b", "10.0.18.0/23"),
        ("app", "c", "10.0.20.0/23"),
        ("web", "a", "10.0.22.0/24"),
        ("web", "b", "10.0.23.0/24"),
        ("web", "c", "10.0.24.0/24"),
        ("db", "a", "10.0.25.0/26"),
        ("db", "b", "10.0.25.64/26"),
        ("db", "c", "10.0.25.128/26"),
    ]
    for alloc in result.values():
        assert int(alloc.network.network_address) % alloc.network.num_addresses == 0
        assert alloc.network.subnet_of(vpc)


def test_allocate_hosts_400_usable_hosts():
    result = allocate(validate(one_tier({"name": "private", "hosts": 400})))
    alloc = result[("private", "a")]
    assert alloc.network == ipaddress.IPv4Network("10.0.0.0/23")
    assert alloc.usable_hosts == 507


def test_allocate_exactly_full():
    data = one_tier(
        {"name": "db", "prefix": 26}, cidr="10.0.0.0/24", azs=("a", "b", "c", "d")
    )
    result = allocate(validate(data))
    assert placed(result) == [
        ("db", "a", "10.0.0.0/26"),
        ("db", "b", "10.0.0.64/26"),
        ("db", "c", "10.0.0.128/26"),
        ("db", "d", "10.0.0.192/26"),
    ]


def test_allocate_rechecks_capacity():
    config = Config(
        ipaddress.IPv4Network("10.0.0.0/24"),
        ("a", "b", "c", "d"),
        (Tier("db", 26), Tier("tiny", 28)),
    )
    with pytest.raises(ConfigError) as info:
        allocate(config)
    errs = info.value.errors
    assert len(errs) == 1
    assert errs[0].startswith("config: ")
    assert "capacity exceeded" in errs[0]
    assert "need 320 addresses" in errs[0]
    assert "has 256" in errs[0]


def test_allocate_rechecks_tier_prefix_vs_vpc():
    config = Config(
        ipaddress.IPv4Network("10.0.0.0/20"),
        ("a",),
        (Tier("web", 24), Tier("big", 19)),
    )
    with pytest.raises(ConfigError) as info:
        allocate(config)
    errs = info.value.errors
    assert len(errs) == 1  # capacity check skipped, though it would also fail
    assert errs[0].startswith("tiers[1] (big): ")
    assert "prefix /19 is larger than the VPC /20" in errs[0]
