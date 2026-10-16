#!/usr/bin/env python3
"""FreeBSD-only integration: actual tun2socks 2.7.0 opens/relinquishes NativeTun.

Run only inside a disposable root FreeBSD VM; never on an operating gateway.
Does NOT touch default routes, OPNsense assigned interfaces, or firewall.
"""
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

if not sys.platform.startswith("freebsd") or os.geteuid() != 0:
    raise SystemExit("This integration requires root inside disposable FreeBSD VM")

binary = Path(sys.argv[1])
iface = "t2sreg93"
def tun_info():
    return subprocess.run(["/sbin/ifconfig", iface], capture_output=True, text=True, timeout=5)

if tun_info().returncode == 0:
    raise SystemExit(f"Refusing to use an existing interface {iface}")

with tempfile.TemporaryDirectory(prefix="xray-tun-integration-") as d:
    conf = Path(d) / "tun2socks.yaml"
    conf.write_text(f"proxy: socks5://127.0.0.1:19993\n"
                    f"device: {iface}\nmtu: 1500\nloglevel: info\n")
    logfile = open(Path(d) / "tun2socks.log", "wb")
    p = subprocess.Popen([str(binary), "--config", str(conf)], stdout=logfile,
                         stderr=subprocess.STDOUT, start_new_session=True)
    try:
        opened = False
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and p.poll() is None:
            result = tun_info()
            if result.returncode == 0:
                m = re.search(r"Opened by PID\s+(\d+)", result.stdout)
                if m and int(m.group(1)) == p.pid:
                    opened = True
                    break
            time.sleep(0.2)
        if not opened:
            logfile.flush()
            detail = (Path(d) / "tun2socks.log").read_text(errors="replace")[-2500:]
            raise AssertionError(f"tun2socks did not claim {iface}, exit={p.poll()}\n{detail}")
        print(f"NativeTun claimed by real tun2socks PID {p.pid}", flush=True)
    finally:
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=6)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=4)
        logfile.close()

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        result = tun_info()
        if result.returncode != 0 or not re.search(r"Opened by PID\s+\d+", result.stdout):
            break
        time.sleep(0.2)
    else:
        raise AssertionError("TUN still has an owner after tun2socks exit")

    # A cloned TUN may remain after exit. Clean only our own test TUN
    # after checking it has no owner; never destroy a live owner's interface.
    if tun_info().returncode == 0:
        subprocess.run(["/sbin/ifconfig", iface, "destroy"], check=True, timeout=5)
    print("NativeTun lifecycle (real FreeBSD kernel): OK")
