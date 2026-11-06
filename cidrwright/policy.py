"""Policy endpoint words and (from Part B) the policy compiler.

Part A (this file today): `RESERVED_ENDPOINTS` and `check_tier_names`,
the reserved-word check that `model.py` applies to tier names (rule P-01).

Part B adds the validation of the `policy:` section and the compiler that
turns it into the cloud-neutral rule list (the IR).

This module does not import `ipam`; it gets what it needs as plain values.
"""

from __future__ import annotations

from collections.abc import Iterable

RESERVED_ENDPOINTS: tuple[str, ...] = ("internet", "vpn", "*")


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
