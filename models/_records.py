"""Helpers for accepting dictionaries and upstream model objects."""

from collections.abc import Mapping


def as_record(value):
    if isinstance(value, Mapping):
        return dict(value)
    method = getattr(value, "to_dict", None)
    if callable(method):
        return dict(method())
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"Expected a mapping or record object, got {type(value)!r}")


def get_value(record, *names, default=None):
    row = as_record(record)
    for name in names:
        if name in row:
            return row[name]
        if hasattr(record, name):
            return getattr(record, name)
    return default
