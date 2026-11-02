#!/usr/bin/env python3
"""P0/P1: production builder, candidate, files, Stop, launch and coordinator.

Only OPNsense/OS boundaries are adapted. Real disk I/O and fresh PHP processes.
These are Linux-portable behavioral tests, NOT FreeBSD integration tests.
"""
from pathlib import Path
import subprocess
import tempfile
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--review-fixes", action="store_true", help="Only B1 and directly related regressions")
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
svc = (ROOT / 'plugin/scripts/Xray/xray-service-control.php').read_text()
svc = svc[svc.index('// ─── Shared constants'):svc.index('// ─── Main')]
# Override path and OS boundaries; do not replace coordinator or stop/launch logic.
sources = [(ROOT/'plugin/scripts/Xray/xray-config.php').read_text()[5:], svc,
           (ROOT/'plugin/scripts/Xray/xray-apply.php').read_text()[5:]]
source = '\n'.join(sources)
replaced = ['xray_get_all_instances', 'xray_get_config',
            'proc_is_running', 'proc_kill', 'proc_start', 'tun_owner_pid', 'tun_owned_by_instance',
            'tun_wait_unowned', 'xray_owned_tuns', 'lo0_alias_ensure', 'xray_watchdog_enabled', 'xray_socks_ready',
            'xray_normalize_transport', 'xray_pid_path', 't2s_pid_path', 'xray_stopped_flag',
            'xray_applied_hash_path', 'xray_instance_log']
for name in replaced:
    a = source.index('function '+name+'(')
    b = source.index('\n}\n', a)+3
    source = source[:a]+source[b:]
for name in ['XRAY_BIN', 'T2S_BIN', 'XRAY_CONF_DIR', 'T2S_CONF_DIR']:
    import re
    source = re.sub(r"define\('"+name+r"',.*?;", '', source)

PRELUDE = r'''<?php
namespace Test\OPNsense\Core;
class Config {
 static function getInstance() { return new self; }
 function object() { return $GLOBALS['networkXml']; }
}
namespace Test;
use SimpleXMLElement;
use RuntimeException;
use Throwable;
const A='00000000-0000-4000-8000-000000000001';
const B='00000000-0000-4000-8000-000000000002';
$dir=$argv[1];
define('XRAY_BIN',$dir.'/core'); define('T2S_BIN',$dir.'/t2s');
define('XRAY_CONF_DIR',$dir.'/json'); define('T2S_CONF_DIR',$dir.'/yaml');
$events=[]; $alive=[]; $all=[]; $failStart=[]; $failStop=[]; $failWrite=[]; $failRename=[];
$networkXml=new SimpleXMLElement('<opnsense><interfaces><a><if>tun1</if><ipaddr>192.0.2.1</ipaddr><subnet>30</subnet></a><b><if>tun2</if><ipaddr>192.0.2.5</ipaddr><subnet>30</subnet></b><c><if>tun3</if><ipaddr>192.0.2.9</ipaddr><subnet>30</subnet></c></interfaces></opnsense>');
$liveTuns=[]; $failNetwork=false; $failUnlink=[];
$invalid=false; $fallbackTemp=false; $shortWrite=false; $watchdog=true;
function verify($ok,$message) { if (!$ok) throw new RuntimeException($message); }
function config($id) {
 return ['inst_uuid'=>$id,'enabled'=>true,'name'=>$id,'tun_iface'=>$id===A?'tun1':'tun2',
 'socks5_listen'=>'127.0.0.1','socks5_port'=>$id===A?19080:19081,'mtu'=>1400,
 'outbound_config'=>'{"protocol":"freedom","tag":"old"}', 'bypass_networks'=>'192.0.2.0/24','loglevel'=>'warning'];
}
function xray_get_all_instances() { return $GLOBALS['all']; }
function xray_get_config($id='') { return $GLOBALS['all'][$id ?: A] ?? []; }
function xray_pid_path($id) { return $GLOBALS['dir'].'/xray_'.$id; }
function t2s_pid_path($id) { return $GLOBALS['dir'].'/t2s_'.$id; }
function xray_stopped_flag($id) { return $GLOBALS['dir'].'/stop_'.$id; }
function xray_applied_hash_path($id) { return $GLOBALS['dir'].'/hash_'.$id; }
function xray_instance_log($id) { return $GLOBALS['dir'].'/log_'.$id; }
function xray_socks_ready($c) { return proc_is_running(xray_pid_path($c['inst_uuid'])); }
function xray_watchdog_enabled() { return $GLOBALS['watchdog']; }
function xray_normalize_transport($json) { return $json; }
function lo0_alias_ensure($ip) {}
function proc_is_running($path) { return isset($GLOBALS['alive'][$path]); }
function proc_start($bin,$args,$path,$log='') {
 $id=substr($path,-36); $part=$bin===XRAY_BIN?'xray':'t2s';
 $GLOBALS['events'][]='start:'.$part.':'.$id;
 if (($GLOBALS['failStart'][$part.':'.$id] ?? 0)>0) { $GLOBALS['failStart'][$part.':'.$id]--; return false; }
 $GLOBALS['alive'][$path]=true;
 if ($part==='t2s') $GLOBALS['liveTuns'][$id]=xray_runtime_config($id)['tun_iface'];
 return true;
}
function proc_kill($path) {
 $id=substr($path,-36); $part=str_contains(basename($path),'t2s_')?'t2s':'xray';
 $GLOBALS['events'][]='kill:'.$part.':'.$id;
 if (($GLOBALS['failStop'][$part.':'.$id] ?? 0)>0) { $GLOBALS['failStop'][$part.':'.$id]--; return false; }
 unset($GLOBALS['alive'][$path]); return true;
}
function tun_owned_by_instance($iface,$id) {
 if (!proc_is_running(t2s_pid_path($id))) return false;
 return ($GLOBALS['liveTuns'][$id] ?? null)===$iface;
}
function tun_owner_pid($iface) {
 foreach (array_keys($GLOBALS['all']) as $id) if(tun_owned_by_instance($iface,$id)) return $id===A?101:102;
 return 0;
}
function xray_owned_tuns($id) { return proc_is_running(t2s_pid_path($id)) ? [$GLOBALS['liveTuns'][$id]] : []; }
function tun_wait_unowned($iface,$owner=0) { return tun_owner_pid($iface)===0; }
function exec($cmd,&$output=null,&$rc=null) {
 if (str_starts_with($cmd,'/sbin/ifconfig ')) {
  preg_match("/ifconfig '([^']+)' (mtu|inet)(?: ([0-9]+))?/",$cmd,$m);
  verify(isset($m[2]),'expected network command');
  if ($m[2]==='mtu') {
   $id=array_search($m[1],$GLOBALS['liveTuns'],true);
   verify($id!==false,'configure actual owned runtime TUN');
   $GLOBALS['events'][]='network:'.$id.':'.$m[1].':'.$m[3];
  }
  // Fail the second command: the interface-up command already succeeded.
  $rc=$m[2]==='inet' && $GLOBALS['failNetwork'] ? 1 : 0; $output=[]; return;
 }

 if (str_contains($cmd,'--reload-only')) { $GLOBALS['events'][]='reload'; $rc=0; return; }
 // Execute the production validator's command shape through a deterministic core adapter.
 verify(str_contains($cmd,'run -test -c') && str_contains($cmd,'-format=json'),'unexpected OS command');
 $GLOBALS['events'][]='validate';
 preg_match("/-c '([^']+)'/",$cmd,$m);
 verify(isset($m[1]) && is_file($m[1]),'candidate file exists while validating');
 verify((fileperms($m[1]) & 0777)===0600,'candidate private');
 $GLOBALS['lastCandidate']=$m[1];
 $output=$GLOBALS['invalid']?['invalid candidate']:[]; $rc=$GLOBALS['invalid']?1:0;
}
function usleep($n) {}
function tempnam($dir,$prefix) {
 if ($GLOBALS['fallbackTemp'] && $prefix==='.xray-') return \tempnam($GLOBALS['dir'],$prefix);
 return \tempnam($dir,$prefix);
}
function fwrite($fd,$bytes) { if ($GLOBALS['shortWrite']) return \fwrite($fd,substr($bytes,0,1)); return \fwrite($fd,$bytes); }
function unlink($path) {
 if ($GLOBALS['failUnlink'][$path] ?? false) return false;
 return \unlink($path);
}
function rename($from,$to) {
 if (($GLOBALS['failRename'][$to] ?? 0)>0) { $GLOBALS['failRename'][$to]--; return false; }
 return \rename($from,$to);
}
function file_get_contents($path,...$rest) { return \file_get_contents($path,...$rest); }
function glob($pattern) {
 if (str_starts_with($pattern,'/var/run/')) return [];
 return \glob($pattern);
}
function started($id) { return xray_healthy(xray_get_config($id)); }
function changed($id) { $GLOBALS['all'][$id]['outbound_config']='{"protocol":"freedom","tag":"new"}'; }
function seed($id) {
 $c=$GLOBALS['all'][$id];
 verify(xray_apply_action('start',$id),'seed start'); $GLOBALS['events']=[];
}
function no_mutations() {
 foreach ($GLOBALS['events'] as $e) verify($e==='validate','unexpected mutation '.$e);
}
'''
SCENARIOS = {
 'P0_first_start': r'''
verify(xray_apply_action('start',A),'first Start'); verify(started(A),'pair ready');
verify(file_get_contents(xray_applied_hash_path(A))===xray_instance_hash($all[A]),'hash after success');
verify(!is_file($lastCandidate),'candidate removed');
''',
 'P0_stop_start': r'''
seed(A); verify(xray_apply_action('stop',A),'Stop'); verify(!xray_any_running(A),'both stopped');
verify(is_file(xray_stopped_flag(A)),'admin flag'); verify(!is_file(xray_applied_hash_path(A)),'hash removed');
verify(xray_apply_action('start',A) && started(A),'Start again'); verify(!is_file(xray_stopped_flag(A)),'intent reset');
''',
 'P0_restart': r'''
seed(A); verify(xray_apply_action('restart',A),'Restart'); verify(started(A),'ready');
verify(in_array('kill:xray:'.A,$events) && in_array('start:xray:'.A,$events),'restart really cycles');
''',
 'P0_apply_changed': r'''
seed(A); changed(A); verify(xray_apply_action('reconfigure',A),'changed Apply');
verify(str_contains(file_get_contents(xray_conf_path(A)),'new'),'new bytes applied'); verify(started(A),'ready');
verify(in_array('kill:xray:'.A,$events),'old process stopped');
''',
 'P0_apply_unchanged': r'''
seed(A); verify(xray_apply_action('reconfigure',A),'no-op Apply'); no_mutations(); verify(started(A),'still ready');
''',
 'P0_validate_valid': r'''
seed(A); $before=file_get_contents(xray_conf_path(A)); changed(A);
verify(xray_prepare_candidate($all[A])!==null,'Validate'); no_mutations();
verify(file_get_contents(xray_conf_path(A))===$before,'Validate leaves runtime unchanged');
''',
 'P0_validate_invalid': r'''
seed(A); $invalid=true; verify(xray_prepare_candidate($all[A])===null,'invalid Validate'); no_mutations(); verify(started(A),'runtime preserved');
''',
 'P0_multiple_instances': r'''
verify(xray_apply_action('start'),'Start all'); verify(started(A)&&started(B),'both ready');
changed(A); changed(B); verify(xray_apply_action('reconfigure'),'Apply all'); verify(started(A)&&started(B),'both applied');
''',
 'P0_boot_repeated': r'''
seed(A); seed(B);
for($i=0;$i<7;$i++) { $alive=[]; @unlink(xray_applied_hash_path(A)); @unlink(xray_applied_hash_path(B));
 verify(xray_apply_action('boot'),'boot '.$i); verify(started(A)&&started(B),'both booted'); }
''',
 'P0_watchdog_components': r'''
seed(A); foreach([xray_pid_path(A),t2s_pid_path(A)] as $pid) { unset($alive[$pid]);
 verify(xray_apply_action('watchdog',A),'watchdog repair'); verify(started(A),'pair repaired'); }
''',
 'P0_watchdog_admin_stop': r'''
seed(A); verify(xray_apply_action('stop',A),'Stop'); $events=[];
verify(xray_apply_action('watchdog',A),'watchdog skip'); no_mutations(); verify(!xray_any_running(A),'stays stopped');
''',
 'P1_invalid_last_candidate': r'''
seed(A); seed(B); $all[B]['outbound_config']='{'; changed(A);
$before=file_get_contents(xray_conf_path(A)); verify(!xray_apply_action('reconfigure'),'invalid batch'); no_mutations();
verify(started(A)&&started(B),'both untouched'); verify(file_get_contents(xray_conf_path(A))===$before,'A bytes intact');
''',
 'P1_socks_tun_conflicts': r'''
seed(A); seed(B); foreach(['start','restart','reconfigure'] as $action) {
 $old=$all[B]; $all[B]['socks5_port']=$all[A]['socks5_port'];
 verify(!xray_apply_action($action),'SOCKS conflict'); no_mutations(); $all[B]=$old;
 $all[B]['tun_iface']=$all[A]['tun_iface']; verify(!xray_apply_action($action),'TUN conflict'); no_mutations(); $all[B]=$old;
}
''',
 'P1_failed_xray': r'''
seed(A); $old=file_get_contents(xray_conf_path(A)); $hash=file_get_contents(xray_applied_hash_path(A)); changed(A);
$failStart['xray:'.A]=1; verify(!xray_apply_action('reconfigure',A),'failure propagated');
verify(started(A)&&file_get_contents(xray_conf_path(A))===$old,'old pair restored');
verify(file_get_contents(xray_applied_hash_path(A))===$hash,'old hash after recovery'); verify(!is_file(xray_stopped_flag(A)),'no admin stop');
''',
 'P1_failed_t2s_independent': r'''
seed(A); seed(B); changed(A); changed(B); $failStart['t2s:'.A]=1;
verify(!xray_apply_action('reconfigure'),'partial failure'); verify(started(A)&&started(B),'both ready');
verify(str_contains(file_get_contents(xray_conf_path(B)),'new'),'B independently commits'); verify(!is_file(xray_stopped_flag(A)),'watchdog allowed');
''',
 'P1_second_stop_failure': r'''
seed(A); seed(B); changed(A); changed(B); $failStop['xray:'.B]=1;
verify(!xray_apply_action('reconfigure'),'stop failure'); verify(started(A)&&started(B),'A applied, B missing component restored');
verify(str_contains(file_get_contents(xray_conf_path(A)),'new'),'A remains new');
verify(str_contains(file_get_contents(xray_conf_path(B)),'old'),'B files unchanged');
''',
 'P1_restore_rename_failure_retry': r'''
seed(A); changed(A); $failRename[t2s_conf_path(A)]=2;
verify(!xray_apply_action('reconfigure',A),'write and rollback failure');
verify(is_file(xray_backup_path(A)),'backup retained'); $backup=file_get_contents(xray_backup_path(A));
verify(!is_file(xray_applied_hash_path(A))&&!is_file(xray_stopped_flag(A)),'hash absent, watchdog allowed');
verify(!xray_apply_action('watchdog',A),'unconfirmed runtime requires explicit recovery');
$failStart['xray:'.A]=1; verify(!xray_apply_action('start',A),'explicit retry then rollback');
verify(file_get_contents(xray_backup_path(A))===$backup,'backup not overwritten by damaged runtime');
verify(started(A),'recovered later'); verify(xray_apply_action('start',A),'explicit retry new config');
''',
 'P1_partial_start': r'''
seed(A); foreach([xray_pid_path(A),t2s_pid_path(A)] as $pid) {
 unset($alive[$pid]); verify(xray_apply_action('start',A),'partial Start'); verify(started(A),'complete pair'); }
''',
 'P1_legacy_changed_resources': r'''
seed(A); @unlink(xray_applied_hash_path(A)); @unlink(xray_backup_path(A));
$old=file_get_contents(xray_conf_path(A)); $all[A]['tun_iface']='tun3'; $all[A]['socks5_port']=19083; $all[A]['mtu']=1450;
$failStart['t2s:'.A]=1; verify(!xray_apply_action('reconfigure',A),'rollback legacy');
verify(file_get_contents(xray_conf_path(A))===$old,'old SOCKS restored'); verify(xray_runtime_config(A)['tun_iface']==='tun1','old TUN restored');
verify(in_array('network:'.A.':tun1:1400',$events),'old MTU and interface setup');
verify(!is_file(xray_applied_hash_path(A)),'no invented legacy hash');
verify(xray_apply_action('reconfigure',A),'ordinary Apply without adoption'); verify(started(A),'new resources ready');
''',
 'P1_legacy_noop': r'''
seed(A); @unlink(xray_applied_hash_path(A)); verify(xray_apply_action('reconfigure',A),'legacy no-op');
foreach($events as $event) verify(!str_starts_with($event,'start:')&&!str_starts_with($event,'kill:'),'legacy not restarted');
''',
 'P1_disabled_profile_handoff': r'''
seed(B); $all[B]['enabled']=false; $all[A]['tun_iface']='tun2'; $all[A]['socks5_port']=19081;
verify(xray_apply_action('reconfigure'),'disabled to enabled handoff'); verify(started(A)&&!xray_any_running(B),'correct owner');
''',
 'P1_runtime_conflict': r'''
seed(B); $all[B]['tun_iface']='tun4'; $all[A]['tun_iface']='tun2';
verify(!xray_apply_action('restart'),'old runtime resource reserved'); no_mutations();
''',
 'P1_watchdog_independence': r'''
seed(A); seed(B); $alive=[]; $all[A]['outbound_config']='{';
for($i=0;$i<7;$i++) { unset($alive[xray_pid_path(B)]);
 verify(xray_apply_action('watchdog'),'saved invalid XML is not applied'); verify(started(B),'B still repaired'); }
''',
 'P1_private_backup': r'''
seed(A); changed(A); verify(xray_apply_action('reconfigure',A),'Apply');
verify((fileperms(xray_backup_path(A))&0777)===0600,'backup private');
''',
 'P1_atomic_write_failures': r'''
seed(A); $path=xray_conf_path(A); $old=file_get_contents($path);
$fallbackTemp=true; verify(!xray_atomic_write($path,'bad'),'tempnam fallback refused'); $fallbackTemp=false;
verify(file_get_contents($path)===$old,'old file intact');
$shortWrite=true; verify(!xray_atomic_write($path,'bad'),'short write refused'); $shortWrite=false;
verify(file_get_contents($path)===$old,'short write preserves old file');
''',
 'P1_first_start_failures': r'''
foreach(['xray'=>A,'t2s'=>B] as $part=>$id) {
 $failStart[$part.':'.$id]=1;
 verify(!xray_apply_action('start',$id),'first launch failure');
 verify(!xray_any_running($id),'candidate cleaned up');
 verify(!is_file(xray_stopped_flag($id))&&!is_file(xray_applied_hash_path($id)),'retry eligible, no success hash');
 verify(xray_apply_action('start',$id)&&started($id),'retry works');
}
''',
 'P1_yaml_equivalent': r'''
seed(A); $yaml=file_get_contents(t2s_conf_path(A));
file_put_contents(t2s_conf_path(A),str_replace('device: tun1', "device: 'tun1'",$yaml));
changed(A); verify(xray_apply_action('reconfigure',A),'equivalent YAML accepted'); verify(started(A),'new pair ready');
''',
 'P1_incomplete_first_write_retry': r'''
$failRename[t2s_conf_path(A)]=1;
verify(!xray_apply_action('start',A),'first YAML write fails');
verify(!xray_any_running(A),'nothing launched');
verify(xray_apply_action('start',A)&&started(A),'retry repairs incomplete pair of files');
''',
 'P1_backup_write_failure': r'''
seed(A); changed(A); $failRename[xray_backup_path(A)]=1;
verify(!xray_apply_action('reconfigure',A),'backup write rejected'); no_mutations(); verify(started(A),'old pair untouched');
''',
 'P1_stop_flag_failure': r'''
seed(A); $failRename[xray_stopped_flag(A)]=1;
verify(!xray_apply_action('stop',A),'cannot persist admin intent'); no_mutations(); verify(started(A),'do not kill before recording intent');
''',
 'P1_removed_instance_conflict': r'''
seed(B); unset($all[B]); $all[A]['socks5_port']=19081;
verify(!xray_apply_action('start',A),'deleted profile still reserves SOCKS'); no_mutations();
''',
 'P1_removed_instance_stop': r'''
seed(A); unset($all[A]); verify(xray_apply_action('stop'),'Stop scans runtime files');
verify(!xray_any_running(A),'deleted profile stopped');
''',
}
# Review regressions execute the same production code, including xray_network.
SCENARIOS.update({
 'R_first_start_without_assignment': r'''
$networkXml=new SimpleXMLElement('<opnsense><interfaces/></opnsense>');
ob_start(); $ok=xray_apply_action('start',A); $message=ob_get_clean();
verify($ok && started(A),'processes can create NativeTun before assignment');
verify(str_contains($message,'network setup pending'),'explicit incomplete network status');
verify(!is_file(xray_applied_hash_path(A)),'no false applied hash');
ob_start(); do_status(A); $status=json_decode(ob_get_clean(),true);
verify($status['status']==='ok' && $status['network_state']==='unconfirmed','process and network readiness distinct in API');
$events=[]; verify(xray_apply_action('watchdog',A),'healthy bootstrap preserved'); no_mutations();
$networkXml->interfaces->addChild('opt1'); $iface=$networkXml->interfaces->opt1;
$iface->addChild('if','tun1'); $iface->addChild('ipaddr','192.0.2.1'); $iface->addChild('subnet','30');
verify(xray_apply_action('reconfigure',A),'Apply finishes assignment');
verify(is_file(xray_applied_hash_path(A)),'network confirmed only after setup');
ob_start(); do_status(A); $status=json_decode(ob_get_clean(),true);
verify($status['network_state']==='applied','network receipt visible after setup');
foreach($events as $e) verify(!str_starts_with($e,'kill:')&&!str_starts_with($e,'start:'),'no process restart');
''',
 'R_invalid_assignment_preflight': r'''
seed(A); $networkXml->interfaces->a->ipaddr='dhcp'; changed(A);
verify(!xray_apply_action('reconfigure',A),'invalid explicit assignment rejected'); no_mutations();
''',
 'R_watchdog_saved_tun': r'''
seed(A); $old=file_get_contents(t2s_conf_path(A)); $all[A]['tun_iface']='tun3';
verify(xray_apply_action('watchdog',A),'XML changes are not a crash'); no_mutations();
verify(file_get_contents(t2s_conf_path(A))===$old && $liveTuns[A]==='tun1','applied TUN retained');
''',
 'R_watchdog_after_rollback': r'''
seed(A); $all[A]['tun_iface']='tun3'; changed(A); $failStart['t2s:'.A]=1;
verify(!xray_apply_action('reconfigure',A),'new TUN fails');
verify(xray_healthy(xray_runtime_config(A)) && $liveTuns[A]==='tun1','old runtime restored');
$events=[]; for($i=0;$i<3;$i++) verify(xray_apply_action('watchdog',A),'watchdog leaves rollback pair');
no_mutations(); verify($liveTuns[A]==='tun1','no repeated Apply');
''',
 'R_watchdog_component_saved_changes': r'''
seed(A); $json=file_get_contents(xray_conf_path(A)); $yaml=file_get_contents(t2s_conf_path(A));
$all[A]['tun_iface']='tun3'; $all[A]['socks5_port']=19083; changed(A);
foreach([xray_pid_path(A),t2s_pid_path(A)] as $path) {
 unset($alive[$path]); $events=[];
 verify(xray_apply_action('watchdog',A),'recover applied component');
 verify(xray_healthy(xray_runtime_config(A)) && $liveTuns[A]==='tun1','old pair recovered');
 verify(file_get_contents(xray_conf_path(A))===$json && file_get_contents(t2s_conf_path(A))===$yaml,'files unchanged');
 foreach($events as $e) verify(!str_starts_with($e,'kill:'),'survivor not stopped');
}
''',
 'R_watchdog_unconfirmed_runtime': r'''
seed(A); unset($alive[t2s_pid_path(A)]); unlink(xray_applied_hash_path(A)); changed(A);
verify(!xray_apply_action('watchdog',A),'unconfirmed runtime requires explicit recovery'); no_mutations();
verify(proc_is_running(xray_pid_path(A)),'survivor preserved');
''',
 'R_watchdog_incoherent_runtime': r'''
seed(A); unset($alive[t2s_pid_path(A)]);
file_put_contents(t2s_conf_path(A),str_replace('19080','19089',file_get_contents(t2s_conf_path(A))));
verify(!xray_apply_action('watchdog',A),'incoherent SOCKS pair rejected'); no_mutations();
''',
 'R_boot_then_watchdog': r'''
seed(A); $alive=[]; unlink(xray_applied_hash_path(A)); $all[A]['tun_iface']='tun3';
verify(xray_apply_action('boot',A),'boot applied runtime');
verify(is_file(xray_applied_hash_path(A)) && $liveTuns[A]==='tun1','boot confirms actual runtime');
unset($alive[t2s_pid_path(A)]); verify(xray_apply_action('watchdog',A),'recover after reboot');
verify($liveTuns[A]==='tun1','saved changes not applied');
''',
 'R_stop_missing_yaml': r'''
seed(A); unlink(t2s_conf_path(A));
verify(xray_apply_action('stop',A),'Stop independent of YAML');
verify(!xray_any_running(A) && is_file(xray_stopped_flag(A)),'processes stopped, intent persisted');
$events=[]; verify(xray_apply_action('watchdog',A),'skip stopped'); no_mutations();
''',
 'R_stop_corrupt_json': r'''
seed(A); file_put_contents(xray_conf_path(A),'{');
verify(xray_apply_action('stop',A),'Stop independent of JSON');
verify(!xray_any_running(A) && is_file(xray_stopped_flag(A)),'processes stopped, intent persisted');
''',
 'R_stop_corrupt_partial_pair': r'''
foreach([xray_pid_path(A),t2s_pid_path(A)] as $path) {
 seed(A); unset($alive[$path]); unlink(t2s_conf_path(A));
 verify(xray_apply_action('stop',A),'Stop partial pair without YAML');
 verify(!xray_any_running(A) && is_file(xray_stopped_flag(A)),'survivor stopped');
}
''',
 'R_stop_corrupt_failure': r'''
seed(A); unlink(t2s_conf_path(A)); $failStop['t2s:'.A]=1;
verify(!xray_apply_action('stop',A),'unconfirmed Stop returns failure');
verify(is_file(xray_stopped_flag(A)),'admin intent retained despite failure');
$events=[]; verify(xray_apply_action('watchdog',A),'watchdog respects intent'); no_mutations();
''',
 'R_reload_stop_once': r'''
seed(A); $GLOBALS['xray_runtime_changed']=false;
verify(xray_apply_action('stop',A),'Stop'); verify($GLOBALS['xray_runtime_changed'],'reload after stopping processes');
$GLOBALS['xray_runtime_changed']=false; verify(xray_apply_action('stop',A),'Stop again');
verify(!$GLOBALS['xray_runtime_changed'],'no reload when already stopped');
''',
 'R_reload_partial_stop': r'''
seed(A); $GLOBALS['xray_runtime_changed']=false; $failStop['xray:'.A]=1;
verify(!xray_apply_action('stop',A),'partial Stop error');
verify($GLOBALS['xray_runtime_changed'],'reload even on partial error');
''',
 'R_delete_apply': r'''
seed(B); unset($all[B]); $all[A]['tun_iface']='tun2'; $all[A]['socks5_port']=19081;
verify(xray_apply_action('reconfigure'),'Delete then Apply releases resources');
verify(!xray_any_running(B) && started(A),'deleted runtime stopped, new owner ready');
verify(is_file(xray_stopped_flag(B)),'deleted UUID administratively stopped');
''',
 'R_delete_missing_json': r'''
seed(A); unset($all[A]); unlink(xray_conf_path(A));
verify(xray_apply_action('reconfigure'),'deleted runtime found through remaining YAML');
verify(!xray_any_running(A) && is_file(xray_stopped_flag(A)),'identified pair stopped');
''',
 'R_delete_preflight_failure': r'''
seed(B); unset($all[B]); $all[A]['outbound_config']='{';
verify(!xray_apply_action('reconfigure'),'invalid batch'); no_mutations();
verify(xray_any_running(B),'deleted runtime preserved until successful preflight');
''',
 'R_delete_stop_failure_independence': r'''
seed(A); seed(B); unset($all[B]); changed(A); $failStop['t2s:'.B]=1;
verify(!xray_apply_action('reconfigure'),'deleted Stop failure reported');
verify(started(A) && str_contains(file_get_contents(xray_conf_path(A)),'new'),'independent A applied');
verify(xray_any_running(B),'failed Stop not reported as success');
''',
})

SCENARIOS.update({
 'B1_network_failure_then_apply': r'''
seed(A); $hash=file_get_contents(xray_applied_hash_path(A));
unset($alive[t2s_pid_path(A)]); $failNetwork=true;
verify(!xray_apply_action('watchdog',A),'network failure reported');
verify(started(A),'recovered processes remain running');
verify(!is_file(xray_applied_hash_path(A)),'old network receipt invalidated');
ob_start(); do_status(A); $status=json_decode(ob_get_clean(),true);
verify($status['status']==='ok' && $status['network_state']==='unconfirmed','no false network success');
verify(!is_file(xray_stopped_flag(A)),'not administrative Stop');
$events=[]; verify(xray_apply_action('watchdog',A),'healthy pair left alone'); no_mutations();
$failNetwork=false; verify(xray_apply_action('reconfigure',A),'explicit Apply retries network');
verify(in_array('network:'.A.':tun1:1400',$events),'network configured again');
foreach($events as $e) verify(!str_starts_with($e,'kill:') && !str_starts_with($e,'start:'),'no unnecessary process restart');
verify(file_get_contents(xray_applied_hash_path(A))===$hash,'receipt restored only after success');
ob_start(); do_status(A); $status=json_decode(ob_get_clean(),true);
verify($status['network_state']==='applied','confirmed network after retry');
''',
 'B1_invalidation_failure': r'''
seed(A); $hash=file_get_contents(xray_applied_hash_path(A)); unset($alive[t2s_pid_path(A)]);
$failUnlink[xray_applied_hash_path(A)]=true;
ob_start(); $ok=xray_apply_action('watchdog',A); $message=ob_get_clean();
verify(!$ok && str_contains($message,'Cannot invalidate applied hash'),'explicit invalidation error');
no_mutations(); verify(!proc_is_running(t2s_pid_path(A)),'recovery not attempted');
verify(file_get_contents(xray_applied_hash_path(A))===$hash,'unremovable receipt not silently replaced');
$failUnlink=[]; verify(xray_apply_action('watchdog',A) && started(A),'retry after invalidation becomes possible');
''',
})
if args.review_fixes:
    relevant = {'P0_apply_unchanged', 'P0_stop_start', 'P0_watchdog_admin_stop',
                'P0_watchdog_components', 'P1_failed_xray', 'P1_failed_t2s_independent',
                'R_watchdog_saved_tun', 'R_watchdog_after_rollback',
                'R_watchdog_component_saved_changes', 'R_watchdog_unconfirmed_runtime',
                'R_boot_then_watchdog', 'B1_network_failure_then_apply', 'B1_invalidation_failure'}
    SCENARIOS = {name: scenario for name, scenario in SCENARIOS.items() if name in relevant}

with tempfile.TemporaryDirectory(prefix='os-xray-actions-') as tmp:
    for name, scenario in SCENARIOS.items():
        d = Path(tmp)/name
        d.mkdir()
        for binary in ['core', 't2s']:
            (d/binary).write_text('#!/bin/sh\nexit 0\n')
            (d/binary).chmod(0o755)
        harness = d/'test.php'
        harness.write_text(PRELUDE+'\n'+source+'\n$all=[A=>config(A),B=>config(B)];\n'+scenario)
        run = subprocess.run(['php',str(harness),str(d)],capture_output=True,text=True,timeout=15)
        if run.returncode:
            raise AssertionError(f'{name}: {run.stdout}\n{run.stderr}')
        print(name+': PASS')
print(f'{len(SCENARIOS)} production lifecycle scenarios: PASS (OS adapters)')

# Exercise the real CLI switch too: exit status and asynchronous reload must not
# turn a partially successful Apply into false success or omit its network reload.
import json
main = (ROOT/'plugin/scripts/Xray/xray-service-control.php').read_text()
main = main[main.index('// ─── Main'):]
main = main.replace("'/var/run/xray_service_operation.lock'", "$dir.'/operation.lock'")
cli_cases = {
    'changed_apply': ("seed(A); seed(B); changed(A);", 0, True),
    'unchanged_apply': ("seed(A); seed(B);", 0, False),
    'partial_apply': ("seed(A); seed(B); changed(A); changed(B); $failStart['t2s:'.B]=1;", 1, True),
    'stop_running': ("seed(A); seed(B); $cliAction='stop';", 0, True),
    'stop_already_stopped': ("seed(A); seed(B); xray_apply_action('stop'); $cliAction='stop';", 0, False),
    'stop_partial_failure': ("seed(A); seed(B); $failStop['xray:'.A]=1; $cliAction='stop';", 1, True),
    'disable_last': ("seed(A); $all[A]['enabled']=false; $all[B]['enabled']=false;", 0, True),
    'rollback_failure': ("seed(A); seed(B); changed(A); $failStart['t2s:'.A]=2;", 1, True),
    'delete_last': ("seed(A); $all=[];", 0, True),
    'invalid_apply': ("seed(A); seed(B); $all[B]['outbound_config']='{';", 1, False),
}
if args.review_fixes:
    cli_cases = {name: case for name, case in cli_cases.items()
                 if name in {'unchanged_apply', 'partial_apply', 'stop_running'}}
with tempfile.TemporaryDirectory(prefix='xray-cli-actions-') as tmp:
    for name, (setup, expected, reload) in cli_cases.items():
        d=Path(tmp)/name; d.mkdir()
        for binary in ['core','t2s']:
            (d/binary).write_text('#!/bin/sh\nexit 0\n'); (d/binary).chmod(0o755)
        script=d/'controller.php'
        tail = r'''
$events=[]; $GLOBALS['xray_runtime_changed']=false;
$argv=[$argv[0],$cliAction ?? 'reconfigure'];
register_shutdown_function(function() { echo "\nEVENTS:".json_encode($GLOBALS['events']); });
'''
        script.write_text(PRELUDE+'\n'+source+'\n$all=[A=>config(A),B=>config(B)];\n'+setup+tail+main)
        result=subprocess.run(['php',str(script),str(d)],capture_output=True,text=True,timeout=15)
        assert result.returncode==expected,(name,result.stdout,result.stderr)
        events=json.loads(result.stdout.rsplit('EVENTS:',1)[1])
        assert ('reload' in events)==reload,(name,events)
        if expected: assert 'ERROR:' in result.stdout
        else: assert 'OK\n' in result.stdout
        print(f'CLI {name}: exit status and reload: PASS')
