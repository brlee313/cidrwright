"""Shared YAML loading.

UniqueKeyLoader is a SafeLoader that rejects duplicate mapping keys;
PyYAML otherwise keeps the last value silently. Used by ipam.load_config
(and by model.load_network from M3 on).
"""


import yaml


class UniqueKeyLoader(yaml.SafeLoader):
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
    