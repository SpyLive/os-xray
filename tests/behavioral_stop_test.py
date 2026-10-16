#!/usr/bin/env python3
"""Execute the production do_stop() implementation against deterministic fakes.

Unlike static string assertions, these cases exercise control-flow decisions.
No OPNsense installation or root privileges are needed.
"""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
src = (root / "plugin/scripts/Xray/xray-service-control.php").read_text()
start = src.index("function do_stop(")
end = src.index("\n}\n", start) + 2
function = src[start:end]
assert "function do_stop" in function

harness = r"""<?php
error_reporting(E_ALL);
$events = [];
$alive = [];
$owner = 0;
$owned = false;
$kill_success = true;
$tmp = sys_get_temp_dir() . '/osxray-test-' . getmypid();
mkdir($tmp);
function t2s_pid_path($u) { return 't2s_' . $u; }
function xray_pid_path($u) { return 'xray_' . $u; }
function xray_applied_hash_path($u) { return $GLOBALS['tmp'] . '/hash_' . $u; }
function xray_stopped_flag($u) { return $GLOBALS['tmp'] . '/flag_' . $u; }
function xray_get_config($u) { return ['tun_iface' => 'proxytun2socks0', 'socks5_listen' => '127.0.0.1']; }
function proc_is_running($path) { return $GLOBALS['alive'][$path] ?? false; }
function tun_owner_pid($iface) { return $GLOBALS['owner']; }
function tun_owned_by_instance($iface, $u) { return $GLOBALS['owned']; }
function proc_kill($path) {
    $GLOBALS['events'][] = $path;
    return $GLOBALS['kill_success'];
}
function tun_wait_unowned($iface, $owner = 0) {
    $GLOBALS['events'][] = 'wait';
    return $GLOBALS['kill_success'];
}
function lo0_alias_remove($ip) { $GLOBALS['events'][] = 'alias'; }
function verify($condition, $message) {
    if (!$condition) { fwrite(STDERR, "FAIL: $message\n"); exit(1); }
}
"""
tests = r"""
// Disabled A sharing a TUN with live C: no signal, no removal, no error.
$owner = 71698; $owned = false; $alive = []; $events = [];
ob_start(); $ok = do_stop('A', 'proxytun2socks0'); ob_end_clean();
verify($ok && $events === [], 'Stop A must not affect active C');
verify(is_file(xray_stopped_flag('A')), 'A must be marked stopped');

// An active instance C owns the TUN: terminate only C and wait for closure.
$alive = ['t2s_C' => true, 'xray_C' => true]; $owned = true; $events = [];
ob_start(); $ok = do_stop('C', 'proxytun2socks0'); ob_end_clean();
verify($ok, 'Stop C should succeed');
verify($events === ['t2s_C', 'wait', 'xray_C', 'alias'], 'Stop C sequencing');

// A process with a foreign TUN owner must not be killed.
$alive = ['t2s_A' => true]; $owned = false; $events = [];
ob_start(); $ok = do_stop('A', 'proxytun2socks0'); ob_end_clean();
verify(!$ok && $events === [], 'Foreign owner must not be signaled');

// Failed stop must propagate and not stop xray/start a replacement.
$alive = ['t2s_C' => true, 'xray_C' => true]; $owned = true;
$kill_success = false; $events = [];
ob_start(); $ok = do_stop('C', 'proxytun2socks0'); ob_end_clean();
verify(!$ok && $events === ['t2s_C'], 'Stop failure must abort immediately');
echo "behavioral do_stop tests: OK\n";
"""
proc = subprocess.run(["php"], input=harness + function + "\n" + tests,
                      text=True, capture_output=True)
if proc.returncode:
    sys.stderr.write(proc.stdout + proc.stderr)
    raise SystemExit(proc.returncode)
print(proc.stdout.strip())
