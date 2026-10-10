# Shutdown error regression tests

Run from the repository root with Python's standard library and Bash:

```sh
python3 tests/test_shutdown.py
python3 tests/test_process_scope.py
python3 tests/test_startup.py
bash -n bin/wechat-iso
```

To compare an inspected original launcher, set
`WECHAT_SHUTDOWN_TEST_SCRIPT=/path/to/original/bin/wechat-iso` when running the
shutdown suite. Never use this fixture to execute unreviewed shell code.

## Shutdown contract

- `down` first detaches the projection. If the client remains active, or its
  state cannot be read, shutdown stops without force-stopping it. A failed
  `xpra detach` command is harmless only when the managed client is confirmed
  inactive or failed, including when the session is already absent.
- Each managed service is stopped in dependency order. Confirmed inactive,
  failed, or collected units are already down and do not need a stop request.
  A failed stop request is ignored only if a subsequent successful query
  confirms `LoadState=not-found` and a stopped `ActiveState`.
- Stop failures and uncertain or still-running states return nonzero and
  preserve the remaining dependencies and overlay. There is no fallback to
  process-name matching, direct signals, restart, or forced unmount.
- All six managed states are rechecked before shared-resource cleanup. Errors
  removing the existing alias, reading the mount table, or unmounting the
  overlay also return nonzero. `status` cannot hide these errors.
- Repeated shutdown and never-started optional IME services remain successful.

`systemctl is-active` nonzero is not proof that shutdown completed: it can also
mean a transitional state or a failed lookup. The implementation instead reads
`ActiveState`, accepts only `inactive`/`failed`, and separately checks query
success. See the upstream [systemctl manual](https://github.com/systemd/systemd/blob/main/man/systemctl.xml)
and [systemd v255 property-query implementation](https://github.com/systemd/systemd/blob/v255/src/systemctl/systemctl-show.c#L1964-L2001).
The latter explicitly handles missing units as `LoadState=not-found` and
`ActiveState=inactive`: property queries print the properties and return zero,
while `status` and `help` report a missing-unit error. A failed D-Bus/property
lookup is a separate error and must never be treated as an absent unit.

## Coverage and safety

The fixture covers repeated/empty shutdown, failed and stuck detach, lookup
errors, rejected stop requests at every dependent-service stage, a unit
collected during stop, successful requests that leave active/transitional or
unknown states, reactivation before cleanup, and mount/cleanup failures.

All commands invoked by the launcher use a fixture-only PATH. The fixture
executables use an absolute Python interpreter, and the launching Bash path is
absolute. HOME, XDG config/runtime paths, cwd, D-Bus address, and process IDs are
synthetic. Bash's `kill` builtin is disabled and shadowed by an absolute fixture
command. No real service manager, signals, GUI, network, installs, IME, or mount
operations run. Overlay changes are JSON state; alias files stay inside a
temporary directory. Unexpected commands fail closed and are asserted absent.

This tests command orchestration, not real systemd or GUI integration. State
checks are snapshots, not a lock against a concurrent `up` or external service
restart. Custom launchers escaping their service cgroup and ownership of the
pre-existing overlay/Wayland alias are outside this change.
