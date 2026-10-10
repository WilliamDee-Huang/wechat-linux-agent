# Managed process scope regression tests

Run `python3 tests/test_process_scope.py` from the repository root (Python 3 standard library and `/usr/bin/bash` only).

The seven tests cover unrelated same-user WeChat instances, repeated startup, an active custom-launcher service, service MainPID reporting, missing/invalid PID values, failed unit lookups, and shutdown with no managed client. The unmodified launcher fails six test methods (nine failures including subtests); the patched launcher passes all seven.

`up` now uses the state of `wx-wechat`, `status` reports that service's MainPID (which may be a custom launcher), and `down` leaves termination to `systemctl stop wx-wechat` and its service cgroup. No process-name match or direct PID signal is used. Launchers that deliberately leave the service cgroup cannot be managed by this mechanism.

Every external command is supplied by a fixture-only PATH. Services, display readiness, process IDs, and signals are synthetic JSON state; Bash's `kill` builtin is explicitly shadowed with an absolute mock command, including when testing the old code. No actual services, WeChat, login, network, IME, mount changes, or process signals are invoked. This checks shell orchestration, not real GUI/systemd, cgroup behavior, AT-SPI, input methods, clipboard, transport, or timing. The fixture is not an OS security sandbox.

For a baseline regression check, `WECHAT_TEST_SCRIPT=/path/to/original/bin/wechat-iso python3 tests/test_process_scope.py` runs the same tests on another inspected launcher source.
