"""Error type and message helpers shared by every module.

Lives on its own so that `policy.py` can raise `ConfigError` without
importing `ipam` (ADR 0006), and so file loading can later be shared
without a circular import. `ipam.ConfigError` still works (re-export).
"""

from __future__ import annotations


class ConfigError(ValueError):
    """Every problem found in a config; str() gives one per line."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))

    def __str__(self) -> str:
        return "\n".join(self.errors)


def describe(x: object) -> str:
    """Name a YAML value's kind in the user's words, for error messages."""
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
