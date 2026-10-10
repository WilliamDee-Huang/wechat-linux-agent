# Startup error regression tests

Run from the repository root, using only Python's standard library and Bash:

```sh
python3 tests/test_startup.py
bash -n bin/wechat-iso
```

The suite checks successful and
repeated startup, failed launch requests for each of Xvfb/xpra/WeChat/attach,
failed executable startup, immediate service exits, display readiness retries
and exhaustion, xpra exiting during the startup wait, standalone attach, and
preservation of existing components after a later failure.

To verify the regressions against a separately saved, reviewed original script:

```sh
WECHAT_ISO_TEST_SCRIPT=/path/to/original/wechat-iso python3 tests/test_startup.py
```

## Startup contract

- A failed launch request or an immediately inactive newly launched unit returns
  nonzero. `up` does not continue to later stages or let `status` hide the error.
- New units use `Type=exec`, so a missing or otherwise unexecutable binary can
  make the start request fail. The default `simple` type can report success
  before `execve` fails. This behavior is described in the upstream
  [systemd-run documentation](https://github.com/systemd/systemd/blob/main/man/systemd-run.xml).
  `Type=exec` requires systemd 240 or later; see the upstream
  [v240 release notes](https://github.com/systemd/systemd/blob/v240/NEWS).
- Xvfb's display must respond before xpra starts. The existing 20-attempt wait
  now fails explicitly on exhaustion; each `xdpyinfo` probe uses `timeout 2`.
- xpra must still be active after the existing three-second startup wait.
- Failure deliberately leaves existing and newly started components alone.
  It prints the failed unit's journal command and explains how to retry or
  deliberately shut down with `wechat-iso down` after checking that closing
  the entire session is safe. There is no automatic rollback, signal, stop,
  restart, or detach, because components may belong to an existing session.

## Safety and limits

All service, process, display, IME, mount, and child-Python commands are local
fixture executables. `PATH`, home/config/runtime paths, D-Bus address, and PIDs
are synthetic; state and command logs live in a temporary directory. The
`kill` function calls the absolute fixture path, and Bash's real `kill` builtin
is disabled. Unexpected commands fail closed and are asserted absent. Sleeps
and display probes are simulated. No packages, real services, WeChat process,
GUI, account login, network, mount, or target-process signals are used.

This is a command-contract fixture, not a security sandbox for arbitrary shell
code. Review any launcher supplied via `WECHAT_ISO_TEST_SCRIPT` before running
it. The suite does not validate real systemd scheduling or GUI compatibility.

An active service is not proof of application readiness: no xpra client/server
handshake or WeChat GUI readiness is claimed, and a service can fail after a
successful check. `StartupTests` use `WX_IME=none`; `IbusStartupTests` use
`WX_IME=ibus` (no engine switch, no panel guard) and check that a failed
`wx-ibus` launch or a missing ibus address file stops startup before WeChat.
Additional IME readiness cases reject missing/invalid/failed MainPID lookups,
stale PID prefixes, commented PID lines, and ibus exiting after its address file
was written. A matching address file plus an active service succeeds. fcitx5
must remain active after its startup delay. These are synthetic service/address
file checks; real IME integration and the X11 overlay remain unvalidated. The
independent same-user process-selection issue and shutdown error behavior are
outside this change.
