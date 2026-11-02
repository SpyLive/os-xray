#!/usr/bin/env python3
"""Production PID ownership/Stop helpers; ps/kill boundaries are simulated."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root/'plugin/scripts/Xray/xray-service-control.php').read_text()
names = ['proc_matches_instance', 'proc_is_running', 'proc_kill', 'do_stop']
functions = []
for name in names:
    start = source.index('function '+name+'(')
    end = source.index('\n}\n', start)+3
    functions.append(source[start:end])
prelude = r'''<?php
namespace Test;
const XRAY_BIN='/usr/local/bin/xray-core';
const T2S_BIN='/usr/local/bin/tun2socks';
const ID='00000000-0000-4000-8000-000000000001';
$dir=$argv[1]; $events=[]; $command=''; $alive=true;
function verify($condition,$message) { if (!$condition) throw new \RuntimeException($message); }
function xray_pid_path($id) { return $GLOBALS['dir'].'/xray_core_'.$id.'.pid'; }
function t2s_pid_path($id) { return $GLOBALS['dir'].'/tun2socks_'.$id.'.pid'; }
function xray_conf_path($id) { return '/fixture/config-'.$id.'.json'; }
function t2s_conf_path($id) { return '/fixture/config-'.$id.'.yaml'; }
function xray_valid_instance_uuid($id) { return $id===ID; }
function xray_stopped_flag($id) { return $GLOBALS['dir'].'/stop'; }
function xray_applied_hash_path($id) { return $GLOBALS['dir'].'/hash'; }
function xray_atomic_write($path,$bytes) { return file_put_contents($path,$bytes)!==false; }
function xray_owned_tuns($id) { return $GLOBALS['scan']; }
function tun_owned_by_instance($iface,$id) { return false; }
function tun_owner_pid($iface) { return 0; }
function tun_wait_unowned($iface,$pid=0) { return true; }
function shell_exec($command) { return $GLOBALS['command']; }
function exec($cmd,&$output=null,&$rc=null) {
 if (str_contains($cmd,'-0 ')) { $rc=$GLOBALS['alive']?0:1; return; }
 $GLOBALS['events'][]=$cmd; $GLOBALS['alive']=false; $rc=0;
}
function usleep($n) {}
'''
checks = r'''
foreach(['','tun1'] as $tun) {
 $alive=true; $scan=[]; $command=''; $events=[];
 file_put_contents(xray_pid_path(ID),'123');
 verify(!do_stop(ID,$tun),'unknown identity must fail Stop');
 verify($events===[],'no signal without confirmed identity');
 verify(is_file(xray_pid_path(ID)) && is_file(xray_stopped_flag(ID)),'PID retained and admin intent stored');
}
$command='/unrelated/program'; $events=[]; $scan=[];
verify(do_stop(ID,''),'known unrelated PID is stale');
verify($events===[] && !is_file(xray_pid_path(ID)),'foreign process untouched');
$command=XRAY_BIN.' run -c '.xray_conf_path(ID); $alive=true; $events=[];
file_put_contents(xray_pid_path(ID),'123');
verify(do_stop(ID,''),'identified process stopped without config files');
verify(count($events)===1 && str_contains($events[0],'-TERM'),'only identified process signalled');
$scan=null;
verify(!do_stop(ID,''),'failed interface scan not silently treated as absence');
$scan=[];
verify(do_stop(ID,''),'confirmed absent processes accepted');
echo "Process identity, corrupt-runtime Stop and absence/uncertainty: PASS\n";
'''
with tempfile.TemporaryDirectory(prefix='xray-identity-') as tmp:
    script = Path(tmp)/'test.php'
    script.write_text(prelude+'\n'.join(functions)+checks)
    run = subprocess.run(['php',str(script),tmp],capture_output=True,text=True,timeout=15)
    assert run.returncode == 0, run.stdout+run.stderr
    print(run.stdout.strip())
