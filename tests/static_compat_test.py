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
all_php = "\n".join(p.read_text() for p in (root / "plugin").rglob("*.php"))

assert "T2S_BIN, '--config " in svc
assert "T2S_BIN, '-config " not in svc
assert "' --config ' . escapeshellarg($t2sConf)" in boot
assert "' -config ' . escapeshellarg($t2sConf)" not in boot
assert "' -config '" not in all_php
assert "run -test -c" in svc
assert "tun_destroy($tunIface);" in svc
assert "'address'    => $host" in imp
assert "'vnext' => [[" not in imp
assert "$settings['address']" in ctl and "$settings['vnext'][0]" in ctl
assert "$settings['address']" in stats and "$settings['vnext'][0]['address']" in stats
assert 'PLUGIN_VERSION="3.1.2"' in installer
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
