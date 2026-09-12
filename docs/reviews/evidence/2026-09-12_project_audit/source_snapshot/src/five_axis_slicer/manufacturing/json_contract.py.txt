"""Strict JSON scalar parsing shared by manufacturing-domain loaders."""

from __future__ import annotations

from typing import Any, Mapping


_NO_DEFAULT = object()


def parse_json_bool(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: bool | object = _NO_DEFAULT,
    field_name: str | None = None,
) -> bool:
    """Read one JSON boolean without Python truthiness coercion.

    JSON booleans decode to the exact Python ``bool`` type. Strings, numbers,
    null, arrays, and objects are rejected. A missing key uses ``default`` when
    supplied; an explicit null never uses the default.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a JSON object")
    name = str(field_name or key).strip() or str(key)
    if key not in payload:
        if default is _NO_DEFAULT:
            raise TypeError(f"{name} must be a boolean")
        if type(default) is not bool:
            raise TypeError(f"{name} default must be a boolean")
        return default
    value = payload[key]
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")
    return value


def require_bool(value: Any, *, field_name: str) -> bool:
    """Validate a direct domain-constructor boolean without coercion."""

    if type(value) is not bool:
        raise TypeError(f"{field_name} must be a boolean")
    return value


__all__ = ["parse_json_bool", "require_bool"]
