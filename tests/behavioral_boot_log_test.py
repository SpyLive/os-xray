#!/usr/bin/env python3
"""Real boot syshook -> PHP dispatch/atomic log -> configd tail -> API.
Only lifecycle work and OPNsense framework are adapted; no router is used.
"""
from pathlib import Path
import configparser
import fcntl
import json
import os
import shlex
import select
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
service = (ROOT/'plugin/scripts/Xray/xray-service-control.php').read_text()
apply = (ROOT/'plugin/scripts/Xray/xray-apply.php').read_text()

def function(source, name):
    start = source.index('function '+name+'(')
    return source[start:source.index('\n}\n', start)+3]

with tempfile.TemporaryDirectory(prefix='xray-boot-log-') as tmp:
    d = Path(tmp)
    log = d/'xray_syshook.log'
    controller = d/'controller.php'
    main = service[service.index('// ─── Main'):]
    main = main.replace('/var/run/xray_service_operation.lock', str(d/'lock'))
    logger = function(service, 'xray_boot_log').replace('/tmp/xray_syshook.log', str(log))
    controller.write_text('''<?php
function xray_apply_action($action,$uuid) {
 if (getenv('BOOT_HOLD')==='1') {
  echo "ready\\n"; fflush(STDOUT); fgets(STDIN);
 }
 echo "synthetic-secret-not-for-boot-log\\n";
 return getenv('BOOT_FAIL')!=='1';
}
''' + function(apply, 'xray_atomic_write') + logger + main)
    hook_source = (ROOT/'plugin/etc/rc.syshook.d/start/50-xray').read_text()
    hook_source = hook_source.replace('/usr/local/bin/php', shlex.quote(shutil.which('php')))
    hook_source = hook_source.replace('/usr/local/opnsense/scripts/Xray/xray-service-control.php', shlex.quote(str(controller)))
    # configctl is an external OS boundary; reload-only must not write Boot log.
    true_executable = shutil.which('true')
    assert true_executable is not None, 'true executable not found in PATH'
    hook_source = hook_source.replace('/usr/local/sbin/configctl', shlex.quote(true_executable))
    hook = d/'hook.sh'; hook.write_text(hook_source)
    log.write_text('obsolete boot record\n')
    for fail in [False, True, False]:
        env = dict(os.environ, BOOT_FAIL='1' if fail else '0')
        run = subprocess.run(['sh', str(hook)], env=env, text=True, capture_output=True, timeout=10)
        assert run.returncode == (1 if fail else 0), run.stdout+run.stderr
        text = log.read_text()
        assert 'Xray boot: '+('failed' if fail else 'completed') in text, text
        assert 'obsolete' not in text and 'synthetic-secret' not in text
        assert len(text) < 200 and len(text.splitlines()) == 1
        assert log.stat().st_mode & 0o777 == 0o600
    print('Boot syshook: fresh bounded private summary on success/failure, no raw secrets: PASS')
    before = log.read_bytes()
    subprocess.run(['sh', str(hook), '--reload-only'], check=True, timeout=10)
    subprocess.run(['php', str(controller), 'watchdog'], check=True, capture_output=True, timeout=10)
    assert log.read_bytes() == before
    print('Reload-only and watchdog preserve Boot log: PASS')

    # A real OS flock held outside the controller: the previous success is stale.
    assert 'Xray boot: completed' in log.read_text()
    with (d/'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = subprocess.run(['sh', str(hook)], capture_output=True, text=True, timeout=10)
        assert run.returncode == 1 and 'operation is in progress' in run.stdout
        text = log.read_text()
        assert 'failed; operation lock unavailable' in text and 'completed' not in text
        assert len(text) < 200 and len(text.splitlines()) == 1
        assert log.stat().st_mode & 0o777 == 0o600
        assert 'synthetic-secret' not in text
        for action in ['start', 'stop', 'restart', 'reconfigure', 'watchdog']:
            denied = subprocess.run(['php', str(controller), action],
                                    capture_output=True, text=True, timeout=10)
            assert denied.returncode == 1
            assert log.read_text() == text
    subprocess.run(['sh', str(hook)], check=True, capture_output=True, timeout=10)
    assert 'Xray boot: completed' in log.read_text()
    print('Busy operation lock: boot failure replaces stale success; other actions unchanged; retry succeeds: PASS')

    # Two actual controller invocations: the losing boot must neither block nor
    # disrupt the owner. Each publication replaces a complete private file.
    holder = subprocess.Popen(['php', str(controller), 'boot'],
                              env=dict(os.environ, BOOT_HOLD='1', BOOT_FAIL='0'),
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
    try:
        ready, _, _ = select.select([holder.stdout], [], [], 5)
        assert ready and holder.stdout.readline() == 'ready\n', 'boot owner did not become ready'
        run = subprocess.run(['sh', str(hook)], capture_output=True, text=True, timeout=10)
        assert run.returncode == 1
        assert 'failed; operation lock unavailable' in log.read_text()
        assert holder.poll() is None, 'lock owner was interrupted'
        stdout, stderr = holder.communicate('continue\n', timeout=10)
        assert holder.returncode == 0, stdout + stderr
        text = log.read_text()
        assert 'Xray boot: completed' in text and 'failed' not in text
        assert len(text) < 200 and len(text.splitlines()) == 1
        assert log.stat().st_mode & 0o777 == 0o600
        assert 'synthetic-secret' not in text
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.communicate(timeout=5)
    print('Concurrent boot: complete records, no deadlock; lock owner completes successfully: PASS')

    actions = configparser.ConfigParser(interpolation=None)
    actions.read(ROOT/'plugin/service/conf/actions.d/actions_xray.conf')
    tail = [actions['log']['command']] + shlex.split(actions['log']['parameters'])
    assert tail[-1] == '/tmp/xray_syshook.log'
    tail[-1] = str(log)
    # Production API action calls the configured tail through a configd adapter.
    api = d/'api.php'
    api.write_text('''<?php
namespace OPNsense\\Base;
class ApiMutableServiceControllerBase { public $request; }
namespace OPNsense\\Core;
class Backend {
 function configdRun($command) {
  if ($command!=='xray log') throw new \\RuntimeException('wrong backend action');
  return shell_exec($GLOBALS['tail']);
 }
}
namespace Test;
$GLOBALS['tail']=getenv('TEST_TAIL');
''' +
        (ROOT/'plugin/mvc/app/controllers/OPNsense/Xray/Api/ServiceController.php').read_text()[5:] + '''
namespace Test;
$api=new \\OPNsense\\Xray\\Api\\ServiceController();
$api->request=new class { function isPost() { return true; } };
echo json_encode($api->logAction());
''')
    response = subprocess.run(['php', str(api)], env=dict(os.environ, TEST_TAIL=shlex.join(tail)),
                              capture_output=True, text=True, check=True, timeout=10)
    assert json.loads(response.stdout)['log'] == log.read_text()
    gui = (ROOT/'plugin/mvc/app/views/OPNsense/Xray/partials/scripts.volt').read_text()
    assert 'loadLog("/api/xray/service/log", \'logBootContent\'' in gui
    assert "var text = (data && data.log)" in gui
    print('Boot log configd tail -> production API -> existing GUI contract: PASS')
    # Refusing a symlink must not alter the boot operation's outcome or its target.
    target = d/'untouched'; target.write_text('unchanged')
    log.unlink(); log.symlink_to(target)
    run = subprocess.run(['sh', str(hook)], capture_output=True, text=True, timeout=10)
    assert run.returncode == 0 and 'Cannot update Xray Boot log' in run.stdout
    assert target.read_text() == 'unchanged'
    print('Boot log publication failure: explicit warning, boot exit status preserved: PASS')
