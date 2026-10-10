#!/usr/bin/env python3
"""Command-contract regressions; only synthetic processes and services are used.
Run with: python3 tests/test_process_scope.py
This fixture is not an OS sandbox. It does not test GUI/systemd integration.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("WECHAT_TEST_SCRIPT", ROOT / "bin/wechat-iso")).resolve()

STUB = r'''import json, os, pathlib, sys
name=pathlib.Path(sys.argv[0]).name; args=sys.argv[1:]
p=pathlib.Path(os.environ['FIXTURE_STATE']); s=json.loads(p.read_text())
with open(os.environ['FIXTURE_LOG'],'a') as f: f.write(json.dumps({'command':name,'args':args})+'\n')
def finish(code=0, output=None):
 t=p.with_name(f'{p.name}.{os.getpid()}.tmp'); t.write_text(json.dumps(s)); os.replace(t,p)  # atomic: pipeline stubs run concurrently
 if output is not None: print(output)
 sys.exit(code)
if name=='readlink': finish(output=str(pathlib.Path(args[-1]).resolve()))
if name=='dirname': finish(output=str(pathlib.Path(args[-1]).parent))
if name=='id': finish(output='4242')
if name=='cat': finish(output='synthetic-machine-id')
if name=='head': finish(output=sys.stdin.readline().rstrip('\n'))
if name=='seq': finish(output='\n'.join(map(str,range(int(args[0]),int(args[1])+1))))
if name=='sleep': finish()
if name=='pgrep':
 pid=s.get('external_pid') or s.get('wechat_pid')
 finish(0 if pid else 1, str(pid) if pid else None)
if name=='kill': s.setdefault('kill_requests',[]).append(args[-1]); s.pop('wechat_pid',None); finish()
if name=='systemctl':
 a=[x for x in args if x!='--user']; op=a[0]; unit=a[-1]
 if op=='is-active':
  active=s.get('units',{}).get(unit,False); finish(0 if active else 3, None if '--quiet' in a else ('active' if active else 'inactive'))
 if op=='cat': finish(0 if unit in s.get('units',{}) else 1)
 if op=='stop':
  s.setdefault('units',{})[unit]=False
  if unit=='wx-wechat': s.pop('wechat_pid',None)
  finish()
 if op=='show':
  prop=a[a.index('-p')+1]
  if prop=='ActiveState': finish(s.get('show_error',0), 'active' if s.get('units',{}).get(unit) else 'inactive')
  if prop=='LoadState': finish(s.get('show_error',0), 'loaded' if unit in s.get('units',{}) else 'not-found')
  if prop=='MainPID': finish(s.get('show_error',0), s.get('main_pid',str(s.get('wechat_pid',0))))
  finish(90)
 finish(90)
if name=='systemd-run':
 unit=next(x.split('=',1)[1] for x in args if x.startswith('--unit='))
 if unit in s.get('fail_units',[]): finish(1)
 s.setdefault('units',{})[unit]=True
 if unit=='wx-wechat': s['wechat_pid']=770002
 finish()
if name=='xdpyinfo': finish(0 if s.get('units',{}).get('wx-xvfb') else 1)
# Allow the bounded display probe used by the independent startup fix.
if name=='timeout' and args==['2','xdpyinfo']:
 finish(0 if s.get('units',{}).get('wx-xvfb') else 1)
if name=='xpra':
 if args[0]=='detach':
  if s.get('detach_failure'): finish(1)
  s.setdefault('units',{})['wx-attach']=False
 finish()
if name=='xdotool': finish(output='660001')
if name=='xprop': finish(output='_NET_WM_STATE(ATOM) =')
if name=='python3': finish() # records winstate invocation; never imports GI or executes it
if name in ('ibus','ibus-daemon','fcitx5','Xvfb','xclip','pkill','timeout','sudo','mount','umount','ln','rm'):
 finish(91) # fail closed: unexpected process/system/IME/overlay operation
if name=='grep': finish(1)
finish(92)
'''

NAMES = 'readlink dirname id cat head seq sleep pgrep kill systemctl systemd-run xdpyinfo xpra xdotool xprop python3 ibus ibus-daemon fcitx5 Xvfb xclip pkill timeout sudo mount umount ln rm grep'.split()

def scenario(actions, state=None):
    with tempfile.TemporaryDirectory(prefix='wechat-process-test-') as td:
        root = Path(td)
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        home = root / 'home'
        home.mkdir()
        config = root / 'config/wechat-iso'
        config.mkdir(parents=True)
        (config / 'config.sh').write_text('WX_IME=none\nWX_X11_OVERLAY=0\nWX_IBUS_WAYLAND_ALIAS=0\nWX_CMD=/synthetic/wechat\nWX_ARGS=""\n')
        stub = bin_dir / 'stub'
        stub.write_text('#!' + sys.executable + ' -S\n' + STUB)
        stub.chmod(0o755)
        for name in NAMES:
            (bin_dir / name).symlink_to(stub)
        state_path = root / 'state.json'
        state_path.write_text(json.dumps(state or {'units': {}}))
        log = root / 'calls.jsonl'
        log.write_text('')
        env = {
            'PATH': str(bin_dir), 'HOME': str(home),
            'XDG_CONFIG_HOME': str(root / 'config'),
            'XDG_RUNTIME_DIR': str(root / 'run'),
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + str(root / 'unused-bus'),
            'LANG': 'C.UTF-8', 'FIXTURE_STATE': str(state_path),
            'FIXTURE_LOG': str(log), 'FIXTURE_BIN': str(bin_dir),
        }
        runs = []
        for action in actions:
            # Never delegate to Bash's kill builtin, even when testing old code.
            runs.append(subprocess.run([
                '/usr/bin/bash', '--noprofile', '--norc', '-c',
                'enable -n kill; kill() { "$FIXTURE_BIN/kill" "$@"; }; source "$0" "$1"',
                str(SCRIPT), action,
            ], env=env, cwd=root, text=True, capture_output=True, timeout=60))
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        return runs, calls, json.loads(state_path.read_text())

def launched(calls):
    return [next(arg.split('=', 1)[1] for arg in call['args'] if arg.startswith('--unit='))
            for call in calls if call['command'] == 'systemd-run']

class ProcessScopeTests(unittest.TestCase):
    def test_unrelated_wechat_does_not_block_up_or_receive_signal(self):
        runs, calls, state = scenario(['up', 'down'], {'units': {}, 'external_pid': 880001})
        self.assertTrue(all(run.returncode == 0 for run in runs))
        self.assertIn('wx-wechat', launched(calls))
        self.assertEqual(state['external_pid'], 880001)
        self.assertFalse(state.get('kill_requests'))
        self.assertFalse(any(call['command'] == 'pgrep' for call in calls))
        self.assertFalse(any(state['units'].values()))

    def test_active_wrapper_unit_is_not_started_again(self):
        # No process named wechat yet: a custom launcher is still starting it.
        runs, calls, _ = scenario(['up'], {'units': {'wx-wechat': True}, 'main_pid': '770003'})
        self.assertEqual(runs[0].returncode, 0)
        self.assertNotIn('wx-wechat', launched(calls))

    def test_repeated_up_reuses_service(self):
        _, calls, _ = scenario(['up', 'up'])
        self.assertEqual(launched(calls), ['wx-xvfb', 'wx-xpra', 'wx-wechat', 'wx-attach'])

    def test_status_uses_managed_main_pid(self):
        runs, _, _ = scenario(['status'], {'units': {'wx-wechat': True}, 'main_pid': '770003', 'external_pid': 880001})
        self.assertIn('wechat     770003', runs[0].stdout)
        self.assertNotIn('880001', runs[0].stdout)

    def test_missing_or_invalid_main_pid_is_not_reported(self):
        for pid in ('', '0', 'n/a', '-1'):
            with self.subTest(pid=pid):
                runs, _, _ = scenario(['status'], {'units': {}, 'main_pid': pid, 'external_pid': 880001})
                self.assertIn('wechat     -', runs[0].stdout)

    def test_failed_unit_lookup_does_not_fall_back_to_process_name(self):
        runs, calls, _ = scenario(['status'], {'units': {}, 'show_error': 1, 'external_pid': 880001})
        self.assertIn('wechat     -', runs[0].stdout)
        self.assertFalse(any(call['command'] == 'pgrep' for call in calls))

    def test_down_without_managed_client_leaves_external_process(self):
        runs, calls, state = scenario(['down'], {'units': {}, 'external_pid': 880001})
        self.assertEqual(runs[0].returncode, 0, runs[0].stderr)
        self.assertEqual(state['external_pid'], 880001)
        self.assertFalse(state.get('kill_requests'))
        # A collected/never-started unit is already down; no stop is necessary.
        self.assertNotIn(['--user', 'stop', 'wx-wechat'], [call['args'] for call in calls if call['command'] == 'systemctl'])

if __name__ == '__main__':
    unittest.main()
