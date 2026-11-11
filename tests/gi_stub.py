"""Minimal PyGObject substitute for unit tests on non-GNOME CI runners."""

from __future__ import annotations

import sys
import types


def ensure_gi() -> None:
    """Install only the GI symbols exercised while importing unit-test targets."""
    try:
        import gi  # noqa: F401

        return
    except ModuleNotFoundError:
        pass

    gi = types.ModuleType("gi")
    repository = types.ModuleType("gi.repository")

    class Variant:
        def __init__(self, _signature: str, value: object) -> None:
            self.value = value

        def unpack(self) -> object:
            return self.value

    glib = types.SimpleNamespace(SOURCE_CONTINUE=True, Variant=Variant, Error=Exception)
    gio = types.SimpleNamespace()
    gst = types.SimpleNamespace()
    gst_video = types.SimpleNamespace()

    gi.require_version = lambda *_args: None  # type: ignore[attr-defined]
    repository.Gio = gio  # type: ignore[attr-defined]
    repository.GLib = glib  # type: ignore[attr-defined]
    repository.Gst = gst  # type: ignore[attr-defined]
    repository.GstVideo = gst_video  # type: ignore[attr-defined]
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository
