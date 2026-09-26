#!/usr/bin/python3
"""Pure helpers for choosing and controlling a mirrored Mutter monitor."""

from __future__ import annotations

from typing import Any


VIRTUAL_CONNECTOR = "Meta-0"


def _unpack(value: Any) -> Any:
    while hasattr(value, "unpack"):
        value = value.unpack()
    return value


def primary_monitor_connector(logical_monitors: list[Any] | tuple[Any, ...]) -> str | None:
    """Return the primary physical connector, with a stable active fallback."""
    fallback = None
    for logical in logical_monitors:
        if len(logical) < 6:
            continue
        connectors = []
        for monitor_spec in logical[5]:
            if not monitor_spec:
                continue
            connector = str(_unpack(monitor_spec[0]))
            if connector and connector != VIRTUAL_CONNECTOR:
                connectors.append(connector)
        if not connectors:
            continue
        if fallback is None:
            fallback = connectors[0]
        if bool(_unpack(logical[4])):
            return connectors[0]
    return fallback


def stream_size(parameters: dict[str, Any], fallback: tuple[int, int]) -> tuple[int, int]:
    """Read a positive compositor-coordinate size from stream parameters."""
    try:
        width, height = _unpack(parameters.get("size", fallback))
        width, height = int(width), int(height)
    except (TypeError, ValueError):
        return fallback
    if width <= 0 or height <= 0:
        return fallback
    return width, height


def map_letterboxed_point(
    x: float,
    y: float,
    output_size: tuple[int, int],
    source_size: tuple[int, int],
) -> tuple[float, float]:
    """Map a point in the encoded raster onto a letterboxed source monitor."""
    output_width, output_height = output_size
    source_width, source_height = source_size
    if min(output_width, output_height, source_width, source_height) <= 0:
        return 0.0, 0.0

    scale = min(output_width / source_width, output_height / source_height)
    content_width = source_width * scale
    content_height = source_height * scale
    offset_x = (output_width - content_width) / 2.0
    offset_y = (output_height - content_height) / 2.0
    mapped_x = (float(x) - offset_x) / scale
    mapped_y = (float(y) - offset_y) / scale
    return (
        min(float(source_width), max(0.0, mapped_x)),
        min(float(source_height), max(0.0, mapped_y)),
    )
