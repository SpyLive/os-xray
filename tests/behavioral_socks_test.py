#!/usr/bin/env python3
"""Exercise production SOCKS listener conflict function with concrete cases."""
from pathlib import Path
import subprocess

src = (Path(__file__).resolve().parents[1] / "plugin/scripts/Xray/xray-service-control.php").read_text()
start = src.index("function xray_socks_conflict(")
end = src.index("\n}\n", start) + 2
function = src[start:end]
harness = r"""<?php
function verify($actual, $expected, $label) {
    if ($actual !== $expected) {
        fwrite(STDERR, "FAIL: {$label}\n");
        exit(1);
    }
}
"""
cases = r"""
verify(xray_socks_conflict('0.0.0.0', 10808, '127.0.0.1', 10808), true, 'wildcard versus loopback');
verify(xray_socks_conflict('127.0.0.1', 10808, '0.0.0.0', 10808), true, 'symmetric wildcard');
verify(xray_socks_conflict('127.0.0.1', 10808, '127.0.0.1', 10808), true, 'same listen');
verify(xray_socks_conflict('127.0.0.1', 10808, '127.0.0.2', 10808), false, 'different loopback');
verify(xray_socks_conflict('0.0.0.0', 10808, '127.0.0.1', 10809), false, 'different ports');
verify(xray_socks_conflict('::', 10808, '127.0.0.1', 10808), true, 'conservative IPv6 wildcard');
echo "behavioral SOCKS conflicts: OK\n";
"""
r = subprocess.run(["php"], input=harness + function + "\n" + cases, text=True, capture_output=True, timeout=8)
if r.returncode:
    raise SystemExit(r.stdout + r.stderr)
print(r.stdout.strip())
