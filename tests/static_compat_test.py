#!/usr/bin/env python3
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
svc = (root / "plugin/scripts/Xray/xray-service-control.php").read_text()
imp = (root / "plugin/mvc/app/controllers/OPNsense/Xray/Api/ImportController.php").read_text()
ctl = (root / "plugin/mvc/app/controllers/OPNsense/Xray/Api/InstanceController.php").read_text()
stats = (root / "plugin/scripts/Xray/xray-ifstats.php").read_text()
installer = (root / "install.sh").read_text()
boot = (root / "plugin/etc/inc/plugins.inc.d/xray.inc").read_text()
boot_hook = (root / "plugin/etc/rc.syshook.d/start/50-xray").read_text()
model = (root / "plugin/mvc/app/models/OPNsense/Xray/Instance.xml").read_text()
watchdog = (root / "plugin/scripts/Xray/xray-watchdog.php").read_text()
ui = (root / "plugin/mvc/app/views/OPNsense/Xray/partials/scripts.volt").read_text()
api = (root / "plugin/mvc/app/controllers/OPNsense/Xray/Api/ServiceController.php").read_text()
all_php = "\n".join(p.read_text() for p in (root / "plugin").rglob("*.php"))
upgrade = (root / "upgrade.sh").read_text()
assert "sh upgrade.sh" in (root / "README.ru.md").read_text()
assert "sh upgrade.sh" in (root / "README.md").read_text()
assert 'cp -p /conf/config.xml "$BACKUP/config.xml"' in upgrade
assert 'service configd restart' in upgrade
assert 'system_cron_configure();' in upgrade
assert 'xray-service-control.php stop' not in upgrade
assert 'configctl xray reconfigure' not in upgrade
assert '/usr/local/bin/xray-core' not in upgrade
assert '/usr/local/tun2socks/tun2socks' not in upgrade
assert 'install.sh uninstall' not in upgrade

# Regressions confirmed on FreeBSD 15.1 with multiple profiles sharing one TUN.
assert "Opened by PID" in svc and "implode(" in svc and "tun_owner_pid" in svc
assert 'echo "Already stopped.' in svc
assert 'return true;' in svc
assert "WARNING: stale PID file" in svc
assert "xray_service_operation.lock" in svc
assert "function xray_socks_conflict(" in svc
assert "xray_socks_conflict($c['socks5_listen']" in svc
assert "foreach ($enabledSocks as $previous)" in boot
assert "isset($enabledTuns[$tun])" in boot
assert '}, false, function () {' in ui and 'dfObj.reject();' in ui
action = api.split('public function reconfigureAction', 1)[1].split('public function statusAction', 1)[0]
assert "'status' => 'failed'" in action
assert "'status' => 'ok'" in action
assert "'status_msg'" in action
# A failed Apply must return the script's ERROR text through configd,
# not masquerade as an unavailable backend.
actions = (root / "plugin/service/conf/actions.d/actions_xray.conf").read_text()
reconfigure = actions.split("[reconfigure]", 1)[1].split("[status]", 1)[0]
assert "type:script_output" in reconfigure
assert "errors:no" in reconfigure
assert "if (empty($output))" in action
assert "stripos($output, 'ERROR')" in action

assert "T2S_BIN, '--config " in svc
assert "T2S_BIN, '-config " not in svc
assert "' --config ' . escapeshellarg($t2sConf)" in boot
assert "' -config ' . escapeshellarg($t2sConf)" not in boot
assert "' -config '" not in all_php
assert "run -test -c" in svc
# Apply must configure TUN synchronously, without waiting on recursive configd reloads.
assert "exec($hook . ' --tun-only 2>&1', $tunOutput, $tunRc);" in svc
assert "if ($tunRc !== 0)" in svc
assert "exec($hook . ' >/dev/null 2>&1 &');" in svc
assert 'TUN_ONLY="${2:-}"' in boot_hook
assert 'if [ "$TUN_ONLY" = "--tun-only" ]; then' in boot_hook
assert 'setup_instance "$INST_UUID"' in boot_hook
assert "    exit $?" in boot_hook
assert "    ifconfig \"$TUN_IFACE\" inet \"$TUN_IP\" 2>&1 || return 1" in boot_hook
# OPNsense cron plugin hooks need ['autocron' => [command, minute]] entries.
assert "['autocron' => ['/usr/local/sbin/configctl -d xray watchdog', '*']]" in boot
assert "['xray_cron_watchdog', '/', '*', '*', '*', '*']" not in boot
# Regression: FreeBSD tun_destroy may block while tun2socks still owns /dev/tun.
assert "tun_destroy($tunIface);" not in svc
assert 'proc_is_running(t2s_pid_path($uuid)) || proc_is_running(xray_pid_path($uuid))' in svc
assert 'if (isset($enabledIfaces[$iface]))' in svc
assert "function xray_instance_hash(array $c): string" in svc
assert "hash_equals(xray_instance_hash($c)" in svc
assert 'INFO: Instance {$uuid} already running with unchanged configuration' in svc
assert "function tun_owned_by_instance(string $iface, string $uuid): bool" in svc
assert "strpos($command, t2s_conf_path($uuid)) !== false" in svc
assert "tun_owned_by_instance($c['tun_iface'], $inst_uuid)" in svc
assert "tun_owner_pid($c['tun_iface']) === $tunPid" not in svc
assert "function proc_kill(string $pidfile): bool" in svc
assert "if (!proc_kill(t2s_pid_path($inst_uuid))) return false;" in svc
assert "if (!proc_kill(xray_pid_path($inst_uuid))) return false;" in svc
assert 'if (!do_stop($uuid, $c[\'tun_iface\']' in svc
assert "proc_is_running(t2s_pid_path($otherUuid))" in svc
assert "if ((string)($inst->enabled ?? '0') !== '1')" in watchdog
assert "'address'    => $host" in imp
assert "'vnext' => [[" not in imp
assert "$settings['address']" in ctl and "$settings['vnext'][0]" in ctl
assert "$settings['address']" in stats and "$settings['vnext'][0]['address']" in stats
assert 'PLUGIN_VERSION="3.1.3"' in installer
assert 'XRAY_VERSION="26.3.27"' in installer
assert 'T2S_VERSION="2.7.0"' in installer
assert 'XRAY_SHA256="c0fcd6962fc8a382e14441370ddbdb6a56e7108c73e817938c626770ac4a1358"' in installer
assert 'T2S_SHA256="3ebb747aa83ee3157330beb324bbeaf9a742db6a8d24b9bbc96a4125aaeeeaea"' in installer
assert 'EXIST_OUTBOUND=""' in installer
assert "outbound_config" in installer
assert "Legacy instances migrated to outbound_config" in installer
assert "'enabled', 'name', 'outbound_config', 'config_mode', 'custom_config'" in installer
assert 'Any old single-instance node needs migration' in installer
assert 'Пустой контейнер НЕ должен блокировать миграцию' in installer
assert "$instances = $x->instances;" in installer
assert "if (!isset($newInst->enabled))" in installer
assert "$newInst->addChild('enabled', '0');" in installer
assert "xray_valid_instance_uuid" in svc
assert "yaml_scalar($proxyUri)" in svc
assert "xray_valid_instance_uuid_boot" in boot
assert "valid_inst_uuid() {" in boot_hook
assert "grep -Eq '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$'" in boot_hook
assert "ENABLED=$(php -r '" in boot_hook
assert "{12}$(php -r" not in boot_hook
assert boot_hook.count("setup_instance() {") == 1
assert boot_hook.count("ENABLED=$(php -r '") == 1
assert boot_hook.splitlines().count("exit 0") == 1
assert boot_hook.rstrip().endswith("exit 0")
assert "releases/latest/download" not in installer
assert 'Gateway IP:            $MEMO_TUN_GW' in installer
assert 'Gateway IP:            $MEMO_TUN_IP' not in installer
assert "<version>3.1.2</version>" in model
print("static compatibility checks: OK")
