#!/usr/bin/env python3
"""Offline startup contracts; no real services, processes, GUI, or network.

Run: python3 tests/test_startup.py
To demonstrate regressions, set WECHAT_ISO_TEST_SCRIPT to a reviewed original
launcher. The mocks are a test fixture, not a sandbox for untrusted shell code.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(os.environ.get(
    "WECHAT_ISO_TEST_SCRIPT", Path(__file__).resolve().parents[1] / "bin/wechat-iso"
)).resolve()
UNITS = ["wx-xvfb", "wx-xpra", "wx-wechat", "wx-attach"]

STUB = r'''
import json
import os
from pathlib import Path
import sys

name = Path(sys.argv[0]).name
args = sys.argv[1:]
state_path = Path(os.environ["FIXTURE_STATE"])
state = json.loads(state_path.read_text())
with open(os.environ["FIXTURE_LOG"], "a") as log:
    log.write(json.dumps({"command": name, "args": args}) + "\n")

def finish(code=0, output=None):
    state_path.write_text(json.dumps(state))
    if output is not None:
        print(output)
    sys.exit(code)

if name == "readlink": finish(output=str(Path(args[-1]).resolve()))
if name == "dirname": finish(output=str(Path(args[-1]).parent))
if name == "id": finish(output="4242")
if name == "cat": finish(output="synthetic-machine-id")
if name == "head": finish(output=sys.stdin.readline().rstrip("\n"))
if name == "seq": finish(output="\n".join(map(str, range(int(args[0]), int(args[1]) + 1))))
if name == "sleep":
    if args == ["3"] and state.get("xpra_exits_during_startup"):
        state.setdefault("units", {})["wx-xpra"] = False
    finish()
if name == "pgrep":
    pid = state.get("wechat_pid")
    finish(0 if pid else 1, str(pid) if pid else None)
if name == "kill":
    state.setdefault("kill_requests", []).append(args)
    finish()
if name == "systemctl":
    options = [arg for arg in args if arg != "--user"]
    operation, unit = options[0], options[-1]
    if operation == "is-active":
        active = state.get("units", {}).get(unit, False)
        finish(0 if active else 3,
               None if "--quiet" in options else ("active" if active else "inactive"))
    if operation == "cat": finish(0 if unit in state.get("units", {}) else 1)
    if operation == "show" and unit == "wx-wechat":
        finish(output=str(state.get("wechat_pid", 0)
                          if state.get("units", {}).get(unit) else 0))
    # No stop/restart reaches the real service manager, even if a regression asks.
    state.setdefault("unexpected", []).append([name, args])
    finish(90)
if name == "systemd-run":
    unit = next(arg.split("=", 1)[1] for arg in args if arg.startswith("--unit="))
    if unit in state.get("fail_units", []): finish(1)
    if unit in state.get("exec_fail_units", []):
        state.setdefault("units", {})[unit] = False
        # Type=simple can return success before exec fails; Type=exec must not.
        finish(1 if "Type=exec" in args or "--property=Type=exec" in args else 0)
    active = unit not in state.get("exit_units", [])
    state.setdefault("units", {})[unit] = active
    if unit == "wx-wechat" and active: state["wechat_pid"] = 770002
    finish()
if name == "timeout" and args == ["2", "xdpyinfo"]:
    name = "xdpyinfo"  # Simulate the probe; never execute timeout or an X client.
if name == "xdpyinfo":
    state["display_checks"] = state.get("display_checks", 0) + 1
    ready = (state.get("units", {}).get("wx-xvfb", False)
             and state["display_checks"] >= state.get("display_ready_after", 1))
    finish(0 if ready else 1)
if name == "xpra":
    state.setdefault("unexpected", []).append([name, args])
    finish(91)
state.setdefault("unexpected", []).append([name, args])
finish(92)  # Fail closed for process, IME, overlay, and other unexpected commands.
'''

NAMES = """readlink dirname id cat head seq sleep pgrep kill systemctl systemd-run
xdpyinfo xpra xdotool xprop python3 ibus ibus-daemon fcitx5 Xvfb xclip pkill
timeout sudo mount umount ln rm grep journalctl""".split()


def scenario(actions=("up",), state=None):
    with tempfile.TemporaryDirectory(prefix="wechat-startup-test-") as directory:
        root = Path(directory)
        mock_bin = root / "bin"
        mock_bin.mkdir()
        home = root / "home"
        home.mkdir()
        config = root / "config/wechat-iso"
        config.mkdir(parents=True)
        (config / "config.sh").write_text(
            'WX_IME=none\nWX_X11_OVERLAY=0\nWX_IBUS_WAYLAND_ALIAS=0\n'
            'WX_CMD=/synthetic/wechat\nWX_ARGS=""\nWX_DISPLAY=:100\n'
        )
        stub = mock_bin / "stub"
        stub.write_text("#!" + sys.executable + "\n" + STUB)
        stub.chmod(0o755)
        for name in NAMES:
            (mock_bin / name).symlink_to(stub)
        state_path = root / "state.json"
        state_path.write_text(json.dumps(state if state is not None else {"units": {}}))
        log_path = root / "calls.jsonl"
        log_path.write_text("")
        environment = {
            "PATH": str(mock_bin), "HOME": str(home),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_RUNTIME_DIR": str(root / "run"),
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=" + str(root / "never-connected-bus"),
            "LANG": "C.UTF-8", "FIXTURE_STATE": str(state_path),
            "FIXTURE_LOG": str(log_path), "FIXTURE_BIN": str(mock_bin),
        }
        runs = []
        for action in actions:
            # Shadow kill using an ABSOLUTE fixture path, not `command kill`,
            # which could select Bash's real builtin. Also disable that builtin.
            command = [
                "/usr/bin/bash", "--noprofile", "--norc", "-c",
                'enable -n kill; kill() { "$FIXTURE_BIN/kill" "$@"; }; source "$0" "$1"',
                str(SCRIPT), action,
            ]
            runs.append(subprocess.run(command, env=environment, cwd=root,
                                       text=True, capture_output=True, timeout=20))
        calls = [json.loads(line) for line in log_path.read_text().splitlines()]
        return runs, calls, json.loads(state_path.read_text())


def launched(calls):
    return [next(arg.split("=", 1)[1] for arg in call["args"]
                 if arg.startswith("--unit="))
            for call in calls if call["command"] == "systemd-run"]


class StartupTests(unittest.TestCase):
    def assert_preserved(self, calls, state):
        self.assertFalse(state.get("unexpected"), state.get("unexpected"))
        self.assertFalse(state.get("kill_requests"))
        self.assertFalse(any(call["command"] in ("kill", "pkill", "sudo", "umount")
                             for call in calls))
        self.assertFalse(any(call["command"] == "systemctl"
                             and any(arg in ("stop", "restart", "kill") for arg in call["args"])
                             for call in calls))

    def assert_failed_at(self, result, unit, attempts):
        runs, calls, state = result
        self.assertNotEqual(runs[0].returncode, 0, runs[0].stdout)
        self.assertEqual(launched(calls), attempts)
        self.assertEqual(runs[0].stdout, "")  # Do not let status mask the failure.
        self.assertIn("journalctl --user -u " + unit, runs[0].stderr)
        self.assertIn("wechat-iso down", runs[0].stderr)
        self.assert_preserved(calls, state)

    def test_success_and_repeated_up(self):
        runs, calls, state = scenario(("up", "up"))
        self.assertEqual([run.returncode for run in runs], [0, 0])
        self.assertTrue(all(not run.stderr for run in runs))
        self.assertEqual(launched(calls), UNITS)
        self.assertTrue(all(state["units"].get(unit) for unit in UNITS))
        for call in calls:
            if call["command"] == "systemd-run":
                self.assertIn("Type=exec", call["args"])
        self.assert_preserved(calls, state)

    def test_launch_failure_stops_at_each_stage(self):
        for index, unit in enumerate(UNITS):
            with self.subTest(unit=unit):
                result = scenario(state={"units": {}, "fail_units": [unit]})
                self.assert_failed_at(result, unit, UNITS[:index + 1])
                self.assertTrue(all(result[2]["units"].get(previous)
                                    for previous in UNITS[:index]))

    def test_exec_failure_stops_at_each_stage(self):
        for index, unit in enumerate(UNITS):
            with self.subTest(unit=unit):
                result = scenario(state={"units": {}, "exec_fail_units": [unit]})
                self.assert_failed_at(result, unit, UNITS[:index + 1])

    def test_immediate_exit_stops_at_each_stage(self):
        for index, unit in enumerate(UNITS):
            with self.subTest(unit=unit):
                result = scenario(state={"units": {}, "exit_units": [unit]})
                self.assert_failed_at(result, unit, UNITS[:index + 1])

    def test_display_timeout_stops_before_xpra(self):
        result = scenario(state={"units": {}, "display_ready_after": 999})
        self.assert_failed_at(result, "wx-xvfb", ["wx-xvfb"])
        self.assertEqual(result[2]["display_checks"], 20)
        self.assertTrue(result[2]["units"]["wx-xvfb"])
        probes = [call for call in result[1] if call["command"] == "timeout"]
        self.assertEqual(len(probes), 20)
        self.assertTrue(all(call["args"] == ["2", "xdpyinfo"] for call in probes))

    def test_delayed_display_readiness(self):
        runs, calls, state = scenario(state={"units": {}, "display_ready_after": 3})
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(state["display_checks"], 3)
        self.assertEqual(launched(calls), UNITS)
        xpra_start = next(index for index, call in enumerate(calls)
                          if call["command"] == "systemd-run" and "--unit=wx-xpra" in call["args"])
        self.assertEqual(sum(call["command"] == "timeout" for call in calls[:xpra_start]), 3)
        self.assert_preserved(calls, state)

    def test_xpra_exit_during_startup_stops_before_wechat(self):
        result = scenario(state={"units": {}, "xpra_exits_during_startup": True})
        self.assert_failed_at(result, "wx-xpra", ["wx-xvfb", "wx-xpra"])

    def test_existing_components_survive_later_failure(self):
        initial = {"units": {unit: True for unit in UNITS[:-1]},
                   "wechat_pid": 770002, "fail_units": ["wx-attach"]}
        result = scenario(state=initial)
        self.assert_failed_at(result, "wx-attach", ["wx-attach"])
        self.assertTrue(all(result[2]["units"].get(unit) for unit in UNITS[:-1]))
        self.assertEqual(result[2]["wechat_pid"], 770002)

    def test_standalone_attach_launch_failure(self):
        result = scenario(("attach",), {"units": {}, "fail_units": ["wx-attach"]})
        self.assert_failed_at(result, "wx-attach", ["wx-attach"])

    def test_standalone_attach_immediate_exit(self):
        result = scenario(("attach",), {"units": {}, "exit_units": ["wx-attach"]})
        self.assert_failed_at(result, "wx-attach", ["wx-attach"])

    def test_existing_attach_is_not_restarted(self):
        runs, calls, state = scenario(("attach",), {"units": {"wx-attach": True}})
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(launched(calls), [])
        self.assert_preserved(calls, state)


if __name__ == "__main__":
    unittest.main(verbosity=2)
