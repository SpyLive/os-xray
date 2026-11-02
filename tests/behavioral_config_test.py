#!/usr/bin/env python3
"""Legacy builders run without OPNsense, binaries or filesystem side effects."""
from pathlib import Path
import json
import hashlib
import subprocess

root = Path(__file__).resolve().parents[1]
builder = root / "plugin/scripts/Xray/xray-config.php"
cases = [
    {"protocol": "vless", "tag": "proxy", "settings": {
        "address": "example.invalid", "port": 443,
        "id": "00000000-0000-4000-8000-000000000001", "encryption": "none"},
     "streamSettings": {"network": "xhttp", "security": "tls", "xhttpSettings": {"path": "/"}}},
    {"protocol": "vless", "tag": "custom", "settings": {"vnext": [{
        "address": "192.0.2.1", "port": 443, "users": [{
            "id": "00000000-0000-4000-8000-000000000001", "encryption": "none"}]}]}},
    {"protocol": "http", "settings": {"servers": [{"address": "example.invalid", "port": 8080}]},
     "mux": {"enabled": False}, "extension": {"keep": [1, False, "Пример"]}},
]
php = r'''
require $argv[1];
$cases = json_decode(stream_get_contents(STDIN), true);
$result = [];
foreach ($cases as $outbound) {
    $c = ['outbound_config'=>json_encode($outbound), 'socks5_listen'=>'127.0.0.1',
          'socks5_port'=>19080, 'tun_iface'=>'tun9', 'mtu'=>1400,
          'bypass_networks'=>' 192.0.2.0/24, ,2001:db8::/32 ', 'loglevel'=>'debug'];
    $result[] = ['config'=>xray_build_config($c), 'yaml'=>xray_build_t2s_config($c)];
}
$result[] = ['defaults'=>xray_build_config(['outbound_config'=>'{"protocol":"freedom"}'])];
foreach (['', '{', 'null', '[]', '{}', '{"tag":"missing-protocol"}'] as $raw) {
    try { xray_build_config(['outbound_config'=>$raw]); exit(90); }
    catch (InvalidArgumentException $e) { /* expected */ }
}
echo json_encode($result, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
'''
run = subprocess.run(["php", "-r", php, str(builder)], input=json.dumps(cases),
                     text=True, capture_output=True, timeout=10, check=True)
results = json.loads(run.stdout)
for outbound, actual in zip(cases, results):
    expected = {
        "log": {"loglevel": "debug"},
        "inbounds": [{"tag": "socks-in", "port": 19080, "listen": "127.0.0.1",
                      "protocol": "socks", "settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"}}],
        "outbounds": [outbound, {"tag": "direct", "protocol": "freedom"}],
        "routing": {"domainStrategy": "IPIfNonMatch", "rules": [
            {"type": "field", "ip": ["192.0.2.0/24", "2001:db8::/32"], "outboundTag": "direct"}]},
    }
    assert actual["config"] == expected, actual
    assert actual["yaml"] == (
        'proxy: "socks5://127.0.0.1:19080"\ndevice: tun9\nmtu: 1400\nloglevel: info\n'
    )
defaults = results[-1]["defaults"]
assert defaults["inbounds"][0]["port"] == 10808
assert defaults["inbounds"][0]["listen"] == "127.0.0.1"
assert defaults["log"] == {"loglevel": "warning"}
assert defaults["routing"]["domainStrategy"] == "IPIfNonMatch"
assert len(defaults["routing"]["rules"][0]["ip"]) == 3
print("behavioral legacy config builders: OK (flat, vnext, generic outbound, defaults, malformed JSON)")
# Frozen pre-refactor defaults, including exact bypass list and outbound order.
assert hashlib.sha256(json.dumps(defaults, sort_keys=True, separators=(",", ":")).encode()).hexdigest() == "22a2ac483e88948ead7c4ba3107d1387074af0c83957ee33cb32d0259112173b"
