#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
svc = (root / "plugin/scripts/Xray/xray-service-control.php").read_text()
imp = (root / "plugin/mvc/app/controllers/OPNsense/Xray/Api/ImportController.php").read_text()
ctl = (root / "plugin/mvc/app/controllers/OPNsense/Xray/Api/InstanceController.php").read_text()
stats = (root / "plugin/scripts/Xray/xray-ifstats.php").read_text()
installer = (root / "install.sh").read_text()
boot = (root / "plugin/etc/inc/plugins.inc.d/xray.inc").read_text()
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
assert 'PLUGIN_VERSION="3.1.0"' in installer
assert 'XRAY_VERSION="26.3.27"' in installer
assert 'T2S_VERSION="2.7.0"' in installer
assert 'XRAY_SHA256="c0fcd6962fc8a382e14441370ddbdb6a56e7108c73e817938c626770ac4a1358"' in installer
assert 'T2S_SHA256="3ebb747aa83ee3157330beb324bbeaf9a742db6a8d24b9bbc96a4125aaeeeaea"' in installer
assert 'EXIST_OUTBOUND=""' in installer
assert "outbound_config" in installer
assert "Legacy instances migrated to outbound_config" in installer
assert "'enabled', 'name', 'outbound_config', 'config_mode', 'custom_config'" in installer
assert 'Any old single-instance node needs migration' in installer
assert "releases/latest/download" not in installer
assert 'Gateway IP:            $MEMO_TUN_GW' in installer
assert 'Gateway IP:            $MEMO_TUN_IP' not in installer
assert "<version>3.1.0</version>" in model
print("static compatibility checks: OK")
