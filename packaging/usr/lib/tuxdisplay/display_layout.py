#!/usr/bin/python3
"""Pure helpers for remembering a Mutter virtual-monitor arrangement.

Mutter assigns a new serial number to every virtual monitor.  Its own saved
monitor configuration therefore cannot associate a newly created ``Meta-0``
with the virtual monitor from the previous TuxDisplay session.  These helpers
store the virtual monitor relative to a stable physical monitor instead.
"""

from __future__ import annotations

from typing import Any


VIRTUAL_CONNECTOR = "Meta-0"


def _unpack(value: Any) -> Any:
    while hasattr(value, "unpack"):
        value = value.unpack()
    return value


def _flag(properties: dict[str, Any], name: str) -> bool:
    return bool(_unpack(properties.get(name, False)))


def _spec(value: Any) -> tuple[str, str, str, str]:
    items = tuple(str(_unpack(item)) for item in value)
    if len(items) != 4:
        raise ValueError("invalid Mutter monitor identity")
    return items  # type: ignore[return-value]


def current_modes(monitors: list[Any] | tuple[Any, ...]) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    """Return the active mode and logical pixel size for every monitor."""
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for monitor in monitors:
        monitor_spec, modes, _properties = monitor
        identity = _spec(monitor_spec)
        selected = None
        preferred = None
        for mode in modes:
            mode_id, width, height, _refresh, _preferred_scale, _scales, properties = mode
            candidate = {
                "id": str(mode_id),
                "width": int(width),
                "height": int(height),
                "scales": [float(_unpack(value)) for value in _scales],
            }
            if _flag(properties, "is-current"):
                selected = candidate
                break
            if _flag(properties, "is-preferred"):
                preferred = candidate
        if selected is not None:
            result[identity] = selected
        elif preferred is not None:
            result[identity] = preferred
    return result


def current_mode_id(monitors: list[Any] | tuple[Any, ...], monitor_spec: Any) -> str | None:
    mode = current_modes(monitors).get(_spec(monitor_spec))
    return str(mode["id"]) if mode is not None else None


def _logical_spec(logical: Any) -> tuple[str, str, str, str] | None:
    monitor_specs = logical[5]
    if len(monitor_specs) != 1:
        return None
    return _spec(monitor_specs[0])


def _logical_geometry(logical: Any, modes: dict[tuple[str, str, str, str], dict[str, Any]]) -> tuple[int, int, int, int] | None:
    identity = _logical_spec(logical)
    mode = modes.get(identity) if identity is not None else None
    if mode is None:
        return None
    scale = float(logical[2])
    if scale <= 0:
        return None
    width = max(1, round(int(mode["width"]) / scale))
    height = max(1, round(int(mode["height"]) / scale))
    if int(logical[3]) in {1, 3, 5, 7}:
        width, height = height, width
    return int(logical[0]), int(logical[1]), width, height


def _rect_distance(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> int:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    horizontal = max(bx - (ax + aw), ax - (bx + bw), 0)
    vertical = max(by - (ay + ah), ay - (by + bh), 0)
    return horizontal * horizontal + vertical * vertical


def capture_placement(monitors: list[Any] | tuple[Any, ...], logical_monitors: list[Any] | tuple[Any, ...]) -> dict[str, Any] | None:
    """Describe ``Meta-0`` relative to its nearest physical monitor."""
    modes = current_modes(monitors)
    virtual = None
    physical: list[tuple[Any, tuple[str, str, str, str], tuple[int, int, int, int]]] = []
    for logical in logical_monitors:
        identity = _logical_spec(logical)
        geometry = _logical_geometry(logical, modes)
        if identity is None or geometry is None:
            continue
        if identity[0] == VIRTUAL_CONNECTOR:
            virtual = (logical, identity, geometry)
        else:
            physical.append((logical, identity, geometry))
    if virtual is None or not physical:
        return None

    _virtual_logical, _virtual_identity, virtual_geometry = virtual
    anchor_logical, anchor_identity, anchor_geometry = min(
        physical,
        key=lambda item: (
            _rect_distance(virtual_geometry, item[2]),
            0 if bool(item[0][4]) else 1,
        ),
    )
    vx, vy, vw, vh = virtual_geometry
    ax, ay, aw, ah = anchor_geometry
    horizontal_delta = (vx + vw / 2) - (ax + aw / 2)
    vertical_delta = (vy + vh / 2) - (ay + ah / 2)
    if abs(horizontal_delta) >= abs(vertical_delta):
        side = "right" if horizontal_delta >= 0 else "left"
        offset = vy - ay
    else:
        side = "below" if vertical_delta >= 0 else "above"
        offset = vx - ax

    return {
        "version": 1,
        "anchor": list(anchor_identity),
        "side": side,
        "offset": int(offset),
    }


def capture_layout(monitors: list[Any] | tuple[Any, ...], logical_monitors: list[Any] | tuple[Any, ...]) -> dict[str, Any] | None:
    """Capture the complete extended layout using stable monitor identities."""
    placement = capture_placement(monitors, logical_monitors)
    if placement is None:
        return None
    saved_logicals = []
    for logical in logical_monitors:
        identity = _logical_spec(logical)
        if identity is None:
            # Mirrored groups require additional policy and are deliberately
            # left to Mutter instead of risking an invalid configuration.
            return None
        saved_logicals.append(
            {
                "monitor": list(identity),
                "x": int(logical[0]),
                "y": int(logical[1]),
                "scale": float(logical[2]),
                "transform": int(logical[3]),
                "primary": bool(logical[4]),
            }
        )
    return {
        "version": 2,
        "logical_monitors": saved_logicals,
        "virtual_placement": placement,
    }


def layout_signature(layout: dict[str, Any]) -> tuple[Any, ...] | None:
    """Return a stable, comparable signature for a captured layout.

    Mutter changes the serial component of ``Meta-0`` whenever the virtual
    monitor is recreated.  That must not make an otherwise identical layout
    look new.  Small floating-point representation differences in scale are
    normalized for the same reason.
    """
    logical_monitors = layout.get("logical_monitors")
    if layout.get("version") != 2 or not isinstance(logical_monitors, list):
        return None
    signature = []
    try:
        for logical in logical_monitors:
            if not isinstance(logical, dict):
                return None
            identity = _spec(logical["monitor"])
            stable_identity: tuple[str, ...]
            if identity[0] == VIRTUAL_CONNECTOR:
                stable_identity = (identity[0], identity[1], identity[2])
            else:
                stable_identity = identity
            signature.append(
                (
                    stable_identity,
                    int(logical["x"]),
                    int(logical["y"]),
                    round(float(logical["scale"]), 4),
                    int(logical["transform"]),
                    bool(logical["primary"]),
                )
            )
    except (KeyError, TypeError, ValueError):
        return None
    return tuple(sorted(signature))


def _anchor_match_score(identity: tuple[str, str, str, str], saved: tuple[str, str, str, str]) -> int:
    if identity == saved:
        return 3
    # Connector names can change across docks; vendor/product/serial is the
    # more stable fallback.  Some monitors expose an empty serial, in which
    # case connector matching is safer than matching every identical panel.
    if saved[3] and identity[1:] == saved[1:]:
        return 2
    return 1 if identity[0] == saved[0] else 0


def restore_placement(
    monitors: list[Any] | tuple[Any, ...],
    logical_monitors: list[Any] | tuple[Any, ...],
    placement: dict[str, Any],
) -> list[Any] | None:
    """Return a complete logical layout with the saved ``Meta-0`` position."""
    try:
        anchor_saved = _spec(placement["anchor"])
        side = str(placement["side"])
        offset = int(placement["offset"])
    except (KeyError, TypeError, ValueError):
        return None
    if placement.get("version") != 1 or side not in {"left", "right", "above", "below"}:
        return None
    if abs(offset) > 100_000:
        return None

    modes = current_modes(monitors)
    virtual_index = -1
    virtual_geometry = None
    anchor_index = -1
    anchor_geometry = None
    anchor_match_score = 0
    for index, logical in enumerate(logical_monitors):
        identity = _logical_spec(logical)
        geometry = _logical_geometry(logical, modes)
        if identity is None or geometry is None:
            continue
        if identity[0] == VIRTUAL_CONNECTOR:
            virtual_index = index
            virtual_geometry = geometry
        else:
            score = _anchor_match_score(identity, anchor_saved)
            if score <= anchor_match_score:
                continue
            anchor_match_score = score
            anchor_index = index
            anchor_geometry = geometry
    if virtual_index < 0 or anchor_index < 0 or virtual_geometry is None or anchor_geometry is None:
        return None

    _vx, _vy, vw, vh = virtual_geometry
    ax, ay, aw, ah = anchor_geometry
    if side == "left":
        new_x, new_y = ax - vw, ay + offset
    elif side == "right":
        new_x, new_y = ax + aw, ay + offset
    elif side == "above":
        new_x, new_y = ax + offset, ay - vh
    else:
        new_x, new_y = ax + offset, ay + ah

    updated = list(logical_monitors)
    logical = list(updated[virtual_index])
    logical[0], logical[1] = int(new_x), int(new_y)
    updated[virtual_index] = tuple(logical)

    # Mutter requires a non-negative logical coordinate space.  Moving the
    # virtual monitor left or above therefore shifts the whole current layout
    # while preserving the user's physical-monitor arrangement.
    minimum_x = min(int(item[0]) for item in updated)
    minimum_y = min(int(item[1]) for item in updated)
    if minimum_x < 0 or minimum_y < 0:
        shifted: list[Any] = []
        for item in updated:
            values = list(item)
            values[0] = int(values[0]) - min(0, minimum_x)
            values[1] = int(values[1]) - min(0, minimum_y)
            shifted.append(tuple(values))
        updated = shifted

    if all(int(before[0]) == int(after[0]) and int(before[1]) == int(after[1]) for before, after in zip(logical_monitors, updated)):
        return None
    return updated


def _restore_complete_layout(
    monitors: list[Any] | tuple[Any, ...],
    logical_monitors: list[Any] | tuple[Any, ...],
    saved_layout: dict[str, Any],
) -> tuple[bool, list[Any] | None]:
    saved_logicals = saved_layout.get("logical_monitors")
    if not isinstance(saved_logicals, list) or len(saved_logicals) != len(logical_monitors):
        return False, None

    modes = current_modes(monitors)
    current: list[tuple[int, Any, tuple[str, str, str, str]]] = []
    for index, logical in enumerate(logical_monitors):
        identity = _logical_spec(logical)
        if identity is None or identity not in modes:
            return False, None
        current.append((index, logical, identity))

    used: set[int] = set()
    updated = list(logical_monitors)
    try:
        for saved in saved_logicals:
            if not isinstance(saved, dict):
                return False, None
            saved_identity = _spec(saved["monitor"])
            candidates = [
                (score, index, logical, identity)
                for index, logical, identity in current
                if index not in used
                if (score := _anchor_match_score(identity, saved_identity)) > 0
            ]
            if not candidates:
                return False, None
            _score, index, logical, identity = max(candidates, key=lambda item: item[0])
            scale = float(saved["scale"])
            supported_scales = modes[identity].get("scales", [])
            if scale <= 0 or not any(abs(scale - candidate) < 0.001 for candidate in supported_scales):
                return False, None
            x = int(saved["x"])
            y = int(saved["y"])
            transform = int(saved["transform"])
            if x < 0 or y < 0 or x > 100_000 or y > 100_000 or transform not in range(8):
                return False, None
            values = list(logical)
            values[0] = x
            values[1] = y
            values[2] = scale
            values[3] = transform
            values[4] = bool(saved["primary"])
            updated[index] = tuple(values)
            used.add(index)
    except (KeyError, TypeError, ValueError):
        return False, None

    if len(used) != len(current) or sum(bool(item[4]) for item in updated) != 1:
        return False, None

    rectangles = []
    for logical in updated:
        geometry = _logical_geometry(logical, modes)
        if geometry is None:
            return False, None
        rectangles.append(geometry)
    for index, first in enumerate(rectangles):
        ax, ay, aw, ah = first
        for bx, by, bw, bh in rectangles[index + 1 :]:
            if min(ax + aw, bx + bw) > max(ax, bx) and min(ay + ah, by + bh) > max(ay, by):
                return False, None

    unchanged = all(
        tuple(before[:5]) == tuple(after[:5])
        for before, after in zip(logical_monitors, updated)
    )
    return True, None if unchanged else updated


def restore_layout(
    monitors: list[Any] | tuple[Any, ...],
    logical_monitors: list[Any] | tuple[Any, ...],
    saved_layout: dict[str, Any],
) -> list[Any] | None:
    """Restore a full stable-identity layout, with v1 placement fallback."""
    if saved_layout.get("version") == 2:
        matched, restored = _restore_complete_layout(monitors, logical_monitors, saved_layout)
        if matched:
            return restored
        fallback = saved_layout.get("virtual_placement")
        if isinstance(fallback, dict):
            return restore_placement(monitors, logical_monitors, fallback)
        return None
    return restore_placement(monitors, logical_monitors, saved_layout)
