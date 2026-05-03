"""Common type aliases for readability."""

from __future__ import annotations

from typing import Any, TypeAlias

JSON: TypeAlias = dict[str, Any]
JSONList: TypeAlias = list[dict[str, Any]]

PostId: TypeAlias = int
GroupId: TypeAlias = int

ConfigValue: TypeAlias = str | int | bool | None
