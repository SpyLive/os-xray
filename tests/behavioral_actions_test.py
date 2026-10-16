#!/usr/bin/env python3
"""Execute actual runtime switch branches with fake three-profile process state.

No OPNsense, network, or root needed. One fresh PHP interpreter per scenario.
"""
from pathlib import Path
import subprocess

svc = (Path(__file__).resolve().parents[1] / "plugin/scripts/Xray/xray-service-control.php").read_text()
start = svc.index("switch ($action) {")
end = svc.index("    case 'status':", start)
switch = svc[start:end] + "\n    default: exit(90);\n}\n"
prelude = r'''<?php
$events = [];
$running = ['C' => true];
$enabled = 'A';
$failStop = '';
$hashes = [];
$dir = sys_get_temp_dir() . '/os-xray-apply-' . getmypid();
mkdir($dir);
register_shutdown_function(function () {
    foreach (glob($GLOBALS['dir'] . '/*') as $p) unlink($p);
    rmdir($GLOBALS['dir']);
});
function profiles() {
    $all = [];
    foreach (['A','C','D'] as $id) {
        $all[$id] = ['inst_uuid'=>$id,'enabled'=>$id === $GLOBALS['enabled'],
                    'tun_iface'=>'proxytun2socks0', 'socks5_listen'=>'127.0.0.1',
                    'socks5_port'=>10808, 'name'=>$id];
    }
    return $all;
}
function xray_get_all_instances() { return profiles(); }
function xray_get_config($id = '') { $p = profiles(); return $p[$id ?: 'A']; }
function t2s_pid_path($id) { return 't2s_'.$id; }
function xray_pid_path($id) { return 'xray_'.$id; }
function proc_is_running($path) {
    $id = substr($path, strpos($path, '_') + 1);
    return $GLOBALS['running'][$id] ?? false;
}
function tun_owned_by_instance($iface, $id) { return $GLOBALS['running'][$id] ?? false; }
function xray_applied_hash_path($id) { return $GLOBALS['dir'].'/'.$id; }
function xray_instance_hash($cfg) { return hash('sha256', json_encode($cfg)); }
function do_stop($id, $iface = null) {
    $GLOBALS['events'][] = 'stop:'.$id;
    if ($id === $GLOBALS['failStop']) return false;
    unset($GLOBALS['running'][$id]);
    @unlink(xray_applied_hash_path($id));
    return true;
}
function do_start($cfg) {
    $id = $cfg['inst_uuid'];
    $GLOBALS['events'][] = 'start:'.$id;
    foreach ($GLOBALS['running'] as $other => $alive) {
        if ($alive && $other !== $id) return false;
    }
    $GLOBALS['running'][$id] = true;
    file_put_contents(xray_applied_hash_path($id), xray_instance_hash($cfg));
    return true;
}
function verify($ok, $why) {
    if (!$ok) { fwrite(STDERR, "FAIL $why\n"); exit(91); }
}
'''
scenarios = {
    "switch_C_to_A": r'''
$enabled = 'A'; $action = 'reconfigure'; $inst_uuid = '';
ob_start();
''',
    "idempotent_C": r'''
$enabled = 'C'; $action = 'reconfigure'; $inst_uuid = '';
file_put_contents(xray_applied_hash_path('C'), xray_instance_hash(profiles()['C']));
ob_start();
''',
    "conflicting_profiles": r'''
$enabled = 'A'; $action = 'reconfigure'; $inst_uuid = '';
// Override enabled profile selection with fake override used by profiles().
ob_start();
''',
    "restart_all": r'''
$enabled = 'A'; $action = 'restart'; $inst_uuid = '';
ob_start();
''',
}
# Top-level runtime exits, so inspect JSON emitted by shutdown handler.
for name, setup in scenarios.items():
    if name == "conflicting_profiles":
        continue
    expected = {
        "switch_C_to_A": ["stop:C", "start:A"],
        "idempotent_C": [],
        "restart_all": ["stop:A", "stop:C", "stop:D", "start:A"],
    }[name]
    main = prelude + setup
    main += r'''
register_shutdown_function(function () {
    echo "\nTEST_EVENTS:" . json_encode($GLOBALS['events']);
});
'''
    main += switch
    run = subprocess.run(["php"], input=main, text=True, capture_output=True, timeout=15)
    if run.returncode:
        raise AssertionError(f"{name}: exit {run.returncode}\n{run.stdout}\n{run.stderr}")
    import json
    if "TEST_EVENTS:" not in run.stdout:
        raise AssertionError(f"{name}: no events recorded: {run.stdout}")
    events = json.loads(run.stdout.rsplit("TEST_EVENTS:", 1)[1].strip())
    if events != expected:
        raise AssertionError(f"{name}: events={events}, expected={expected}")
    print(f"behavioral {name}: OK")
