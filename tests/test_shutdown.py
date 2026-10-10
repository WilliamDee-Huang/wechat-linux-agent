#!/usr/bin/env python3
"""Offline shutdown contracts. Review any alternate launcher before running.

All external launcher commands are fixture-only; this is not an OS sandbox.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(os.environ.get(
    "WECHAT_SHUTDOWN_TEST_SCRIPT", Path(__file__).resolve().parents[1] / "bin/wechat-iso"
)).resolve()
UNITS = ["wx-attach", "wx-wechat", "wx-ibus", "wx-ime", "wx-xpra", "wx-xvfb"]
STOP_UNITS = UNITS[1:]  # xpra detach has already stopped the managed attach client.

STUB = r'''
import json
import os
from pathlib import Path
import sys

name, args = Path(sys.argv[0]).name, sys.argv[1:]
state_path = Path(os.environ["FIXTURE_STATE"])
state = json.loads(state_path.read_text())
with open(os.environ["FIXTURE_LOG"], "a") as log:
    log.write(json.dumps({"command": name, "args": args}) + "\n")

def finish(code=0, output=None, changed=False):
    # Read-only pipeline commands must not overwrite a concurrent state change.
    if changed:
        temporary = state_path.with_name(f"{state_path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(state))
        os.replace(temporary, state_path)
    if output is not None:
        print(output)
    sys.exit(code)

if name == "readlink": finish(output=str(Path(args[-1]).resolve()))
if name == "dirname": finish(output=str(Path(args[-1]).parent))
if name == "id": finish(output="4242")
if name == "cat": finish(output="synthetic-machine-id")
if name == "seq": finish(output="\n".join(map(str, range(int(args[0]), int(args[1]) + 1))))
if name == "sleep": finish()
if name == "xpra" and args == ["detach", ":100"]:
    if state.get("detach_error"): finish(1)
    if not state.get("detach_stuck") and "wx-attach" in state["units"]:
        state["units"]["wx-attach"] = "inactive"
    finish(changed=True)
if name == "systemctl":
    options = [arg for arg in args if arg != "--user"]
    operation, unit = options[0], options[-1]
    active_state = state["units"].get(unit, "inactive")
    if operation == "is-active":
        if unit in state.get("query_error_units", []): finish(1)
        active = active_state in ("active", "reloading", "refreshing")
        finish(0 if active else 3, None if "--quiet" in options else active_state)
    if operation == "cat": finish(0 if unit in state["units"] else 1)
    if operation == "show":
        if unit in state.get("query_error_units", []): finish(1)
        prop = options[options.index("-p") + 1]
        if prop == "ActiveState": finish(output=active_state)
        if prop == "LoadState":
            finish(output="loaded" if unit in state["units"] else "not-found")
        if prop == "MainPID": finish(output="770002" if active_state == "active" else "0")
    if operation == "stop":
        if unit in state.get("collect_on_stop", []):
            state["units"].pop(unit, None)
            finish(5, changed=True)  # Collected between the query and stop.
        if unit not in state["units"]: finish(5)
        if unit in state.get("stop_error_units", []): finish(1)
        state["units"][unit] = state.get("after_stop", {}).get(unit, "inactive")
        if unit in state.get("query_error_after_stop", []):
            state.setdefault("query_error_units", []).append(unit)
        if unit == "wx-xvfb" and state.get("restart_before_cleanup"):
            state["units"][state["restart_before_cleanup"]] = "active"
        finish(changed=True)
if name == "mount" and not args:
    finish(1 if state.get("mount_error") else 0,
           "tmpfs on /tmp/.X11-unix type tmpfs (rw,relatime)" if state.get("overlay") else "")
if name == "grep" and args == ["-q", "tmpfs on /tmp/.X11-unix type tmpfs (rw"]:
    finish(0 if args[-1] in sys.stdin.read() else 1)
if name == "sudo" and args == ["umount", "/tmp/.X11-unix"]:
    state["unmounts"] = state.get("unmounts", 0) + 1
    if state.get("unmount_error"): finish(1, changed=True)
    state["overlay"] = False
    finish(changed=True)
if name == "rm" and args[0] == "-f":
    finish(1 if state.get("remove_error") else 0)
state.setdefault("unexpected", []).append([name, args])
finish(90, changed=True)
'''

NAMES = """readlink dirname id cat seq sleep systemctl systemd-run xpra mount
grep sudo umount rm kill pkill pgrep timeout python3 xdpyinfo Xvfb ibus
ibus-daemon fcitx5 xdotool xprop head ln basename journalctl""".split()


def scenario(state=None, actions=("down",), alias=False):
    with tempfile.TemporaryDirectory(prefix="wechat-shutdown-test-") as directory:
        root = Path(directory)
        mock_bin, home = root / "bin", root / "home"
        mock_bin.mkdir()
        home.mkdir()
        config = root / "config/wechat-iso"
        config.mkdir(parents=True)
        (root / "run").mkdir()
        (config / "config.sh").write_text(
            "WX_IME=none\nWX_X11_OVERLAY=1\nWX_IBUS_WAYLAND_ALIAS=0\n"
            'WX_CMD=/synthetic/wechat\nWX_ARGS=""\nWX_DISPLAY=:100\n'
        )
        if alias:
            bus = home / ".config/ibus/bus"
            bus.mkdir(parents=True)
            (bus / "synthetic-machine-id-unix-wayland-0").symlink_to("synthetic-machine-id-unix-100")
        stub = mock_bin / "stub"
        stub.write_text("#!" + sys.executable + " -S\n" + STUB)
        stub.chmod(0o755)
        for name in NAMES:
            (mock_bin / name).symlink_to(stub)
        state_path, log_path = root / "state.json", root / "calls.jsonl"
        state_path.write_text(json.dumps(state if state is not None else {
            "units": {unit: "active" for unit in UNITS}, "overlay": True,
        }))
        log_path.write_text("")
        environment = {
            "PATH": str(mock_bin), "HOME": str(home),
            "XDG_CONFIG_HOME": str(root / "config"), "XDG_RUNTIME_DIR": str(root / "run"),
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(root / "never-connected-bus"),
            "LANG": "C.UTF-8", "FIXTURE_STATE": str(state_path),
            "FIXTURE_LOG": str(log_path), "FIXTURE_BIN": str(mock_bin),
        }
        runs = []
        for action in actions:
            runs.append(subprocess.run([
                "/usr/bin/bash", "--noprofile", "--norc", "-c",
                'enable -n kill; kill() { "$FIXTURE_BIN/kill" "$@"; }; source "$0" "$1"',
                str(SCRIPT), action,
            ], env=environment, cwd=root, capture_output=True, text=True, timeout=60))
        return runs, [json.loads(line) for line in log_path.read_text().splitlines()], json.loads(state_path.read_text())


def stop_requests(calls):
    return [call["args"][-1] for call in calls
            if call["command"] == "systemctl" and "stop" in call["args"]]


class ShutdownTests(unittest.TestCase):
    def active(self, **extra):
        return {"units": {unit: "active" for unit in UNITS}, "overlay": True, **extra}

    def assert_safe(self, calls, state):
        self.assertFalse(state.get("unexpected"), state.get("unexpected"))
        self.assertFalse(any(call["command"] in ("kill", "pkill", "pgrep", "systemd-run") for call in calls))
        self.assertTrue(all(unit in UNITS for unit in stop_requests(calls)))

    def assert_failed(self, result, unit=None):
        runs, calls, state = result
        self.assertNotEqual(runs[0].returncode, 0, runs[0].stdout)
        self.assertEqual(runs[0].stdout, "")
        if unit:
            self.assertIn(unit, runs[0].stderr)
        self.assert_safe(calls, state)

    def test_success_and_repeated_down(self):
        runs, calls, state = scenario(actions=("down", "down"))
        self.assertEqual([run.returncode for run in runs], [0, 0])
        self.assertEqual(stop_requests(calls), STOP_UNITS)
        self.assertEqual(state["unmounts"], 1)
        self.assertTrue(all(value == "inactive" for value in state["units"].values()))
        self.assert_safe(calls, state)

    def test_missing_units_and_no_xpra_server_are_already_down(self):
        runs, calls, state = scenario({"units": {}, "detach_error": True})
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(stop_requests(calls), [])
        self.assert_safe(calls, state)

    def test_detach_failure_does_not_force_stop_or_cleanup(self):
        for key in ("detach_error", "detach_stuck"):
            with self.subTest(key=key):
                result = scenario(self.active(**{key: True}))
                self.assert_failed(result, "wx-attach")
                self.assertEqual(stop_requests(result[1]), [])
                self.assertNotIn("unmounts", result[2])
                self.assertTrue(all(value == "active" for value in result[2]["units"].values()))

    def test_detach_lookup_error_is_not_inactive(self):
        result = scenario(self.active(query_error_units=["wx-attach"]))
        self.assert_failed(result, "wx-attach")
        self.assertEqual(stop_requests(result[1]), [])
        self.assertNotIn("unmounts", result[2])

    def test_stop_failure_preserves_remaining_dependencies(self):
        for index, unit in enumerate(STOP_UNITS):
            with self.subTest(unit=unit):
                result = scenario(self.active(stop_error_units=[unit]))
                self.assert_failed(result, unit)
                self.assertEqual(stop_requests(result[1]), STOP_UNITS[:index + 1])
                self.assertNotIn("unmounts", result[2])
                self.assertTrue(all(result[2]["units"][later] == "active" for later in STOP_UNITS[index:]))

    def test_query_errors_preserve_dependencies(self):
        for key in ("query_error_units", "query_error_after_stop"):
            with self.subTest(key=key):
                result = scenario(self.active(**{key: ["wx-wechat"]}))
                self.assert_failed(result, "wx-wechat")
                self.assertNotIn("wx-xpra", stop_requests(result[1]))
                self.assertNotIn("unmounts", result[2])

    def test_successful_stop_must_leave_a_confirmed_stopped_unit(self):
        for state in ("active", "activating", "deactivating", "reloading", "refreshing", "", "unknown"):
            with self.subTest(state=state):
                result = scenario(self.active(after_stop={"wx-wechat": state}))
                self.assert_failed(result, "wx-wechat")
                self.assertEqual(stop_requests(result[1]), ["wx-wechat"])
                self.assertNotIn("unmounts", result[2])

    def test_collected_unit_during_stop_is_already_down(self):
        runs, calls, state = scenario(self.active(collect_on_stop=STOP_UNITS))
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(state["unmounts"], 1)
        self.assert_safe(calls, state)

    def test_final_state_recheck_prevents_unmount(self):
        result = scenario(self.active(restart_before_cleanup="wx-wechat"))
        self.assert_failed(result, "wx-wechat")
        self.assertNotIn("unmounts", result[2])

    def test_mount_query_error_is_not_an_absent_overlay(self):
        result = scenario(self.active(mount_error=True))
        self.assert_failed(result)
        self.assertNotIn("unmounts", result[2])

    def test_unmount_failure_is_not_hidden_by_status(self):
        result = scenario(self.active(unmount_error=True))
        self.assert_failed(result)
        self.assertEqual(result[2]["unmounts"], 1)

    def test_alias_cleanup_failure_is_not_hidden_by_status(self):
        result = scenario(self.active(remove_error=True), alias=True)
        self.assert_failed(result)
        self.assertNotIn("unmounts", result[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
