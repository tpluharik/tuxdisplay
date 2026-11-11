#!/usr/bin/python3
"""Tests for automatic lid-close and sleep disconnection."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock

from gi_stub import ensure_gi


ensure_gi()

MODULE_PATH = Path(__file__).parents[1] / "packaging" / "usr" / "lib" / "tuxdisplay" / "sleep_monitor.py"
SPEC = importlib.util.spec_from_file_location("sleep_monitor", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SleepMonitorTests(unittest.TestCase):
    def test_lid_state_parser_accepts_kernel_format(self) -> None:
        self.assertIs(MODULE.parse_lid_state("state:      closed\n"), True)
        self.assertIs(MODULE.parse_lid_state("state:      open\n"), False)
        self.assertIsNone(MODULE.parse_lid_state("state: unknown\n"))

    def test_proc_reader_prefers_any_closed_lid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "LID0"
            second = Path(directory) / "LID1"
            first.write_text("state: open\n", encoding="utf-8")
            second.write_text("state: closed\n", encoding="utf-8")
            self.assertIs(MODULE.proc_lid_closed((str(first), str(second))), True)

    def test_logind_and_upower_signals_request_disconnect(self) -> None:
        watcher = MODULE.SleepSignals()
        watcher._prepare_for_sleep(
            None,
            "",
            "",
            "",
            "",
            MODULE.GLib.Variant("(b)", (True,)),
        )
        self.assertEqual(watcher.reason, "system sleep requested")

        lid_watcher = MODULE.SleepSignals()
        lid_watcher._upower_properties_changed(
            None,
            "",
            "",
            "",
            "",
            MODULE.GLib.Variant(
                "(sa{sv}as)",
                (
                    MODULE.UPOWER_INTERFACE,
                    {"LidIsClosed": MODULE.GLib.Variant("b", True)},
                    [],
                ),
            ),
        )
        self.assertEqual(lid_watcher.reason, "laptop lid closed")

    def test_run_stops_child_cleanly_when_lid_closes(self) -> None:
        class FakeWatcher:
            def __init__(self) -> None:
                self.reason = None
                self.closed = False

            def connect(self) -> None:
                pass

            def dispatch(self) -> None:
                pass

            def request_disconnect(self, reason: str) -> None:
                if self.reason is None:
                    self.reason = reason

            def close(self) -> None:
                self.closed = True

        class FakeChild:
            def __init__(self) -> None:
                self.returncode = None
                self.signals: list[int] = []

            def poll(self) -> int | None:
                return self.returncode

            def send_signal(self, signum: int) -> None:
                self.signals.append(signum)
                self.returncode = 0

            def wait(self, timeout: float) -> int:
                assert timeout > 0
                return int(self.returncode or 0)

        watcher = FakeWatcher()
        child = FakeChild()
        lid_states = iter((False, True))
        with mock.patch.object(MODULE, "SleepSignals", return_value=watcher), mock.patch.object(
            MODULE.subprocess, "Popen", return_value=child
        ), mock.patch.object(MODULE.time, "sleep"):
            result = MODULE.run(["display-service"], lid_reader=lambda: next(lid_states))

        self.assertEqual(result, 0)
        self.assertEqual(child.signals, [signal.SIGINT])
        self.assertTrue(watcher.closed)

    def test_run_does_not_start_backend_when_lid_is_already_closed(self) -> None:
        watcher = mock.Mock()
        watcher.reason = None

        def request_disconnect(reason: str) -> None:
            watcher.reason = reason

        watcher.request_disconnect.side_effect = request_disconnect
        with mock.patch.object(MODULE, "SleepSignals", return_value=watcher), mock.patch.object(
            MODULE.subprocess, "Popen"
        ) as popen:
            result = MODULE.run(["display-service"], lid_reader=lambda: True)

        self.assertEqual(result, 0)
        popen.assert_not_called()
        watcher.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
