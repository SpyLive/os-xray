#!/usr/bin/env python3
"""Check the global operation lock does not survive an exec() child.

Linux CI reproduces the descriptor inheritance regression; the FreeBSD
integration test remains required before production release.
"""
from pathlib import Path
import subprocess
import tempfile
import time

root = Path(__file__).resolve().parents[1]
svc = (root / "plugin/scripts/Xray/xray-service-control.php").read_text()
boot = (root / "plugin/etc/inc/plugins.inc.d/xray.inc").read_text()
for path, source in (("runtime", svc), ("boot", boot)):
    assert "fopen('/var/run/xray_service_operation.lock', 'ce')" in source, path

with tempfile.TemporaryDirectory() as temp:
    lock = str(Path(temp) / "operation.lock")
    php = r'''
$fd = fopen($argv[1], 'ce');
if (!$fd || !flock($fd, LOCK_EX | LOCK_NB)) exit(3);
exec('/bin/sleep 2 >/dev/null 2>&1 &');
exit(0);
'''
    first = subprocess.run(["php", "-r", php, lock], capture_output=True, text=True, timeout=4)
    assert first.returncode == 0, first.stderr
    contender = r'''
$fd = fopen($argv[1], 'ce');
if (!$fd) exit(4);
exit(flock($fd, LOCK_EX | LOCK_NB) ? 0 : 5);
'''
    second = subprocess.run(["php", "-r", contender, lock], capture_output=True, text=True, timeout=4)
    assert second.returncode == 0, (
        "Global lock leaked into background child (a subsequent Apply would fail)."
    )
print("behavioral exec lock inheritance: OK")
