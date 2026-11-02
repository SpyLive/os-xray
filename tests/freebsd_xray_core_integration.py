#!/usr/bin/env python3
"""Isolated FreeBSD packet-path test: kernel TCP -> NativeTun -> tun2socks -> real Xray-core SOCKS.

Uses a fake destination in the benchmarking range 198.18.0.0/15.
Adds only an interface-specific /32 route, removes it before exit, and never
changes default route, host firewall, or any OPNsense interface.
"""
import os
import json
import re
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if not sys.platform.startswith("freebsd") or os.geteuid() != 0:
    raise SystemExit("Run as root in disposable FreeBSD VM only")

binary = str(Path(sys.argv[1]).resolve())
iface = "t2sxray95"
target = "198.18.95.1"
port = 18095
payload = b"NativeTun-XrayCore-HTTP-OK"
received = []
proxy_error = []
ready = threading.Event()
stop = threading.Event()

def local_http_server():
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 18195))
    listener.listen(1)
    listener.settimeout(15)
    ready.set()
    try:
        client, _ = listener.accept()
        with client:
            client.settimeout(10)
            request = client.recv(8192)
            assert b"GET /tun-smoke" in request, request
            received.append("HTTP")
            reply = (b"HTTP/1.1 200 OK\r\nContent-Length: " +
                     str(len(payload)).encode() + b"\r\nConnection: close\r\n\r\n" + payload)
            client.sendall(reply)
    except Exception as exc:
        proxy_error.append(str(exc))
    finally:
        listener.close()
        stop.set()

def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, timeout=8, **kwargs)

def tun_info():
    return subprocess.run(["/sbin/ifconfig", iface], capture_output=True, text=True, timeout=4)

if tun_info().returncode == 0:
    raise RuntimeError(f"Refusing to touch pre-existing {iface}")

thread = threading.Thread(target=local_http_server, daemon=True)
thread.start()
assert ready.wait(4), "Local HTTP server did not start"
process = None
xray_process = None
route_added = False
with tempfile.TemporaryDirectory(prefix="xray-packet-path-") as directory:
    # Exercise the production legacy builder with the installer-pinned real core.
    settings = {
        "outbound_config": json.dumps({"tag": "proxy", "protocol": "freedom",
                                      "settings": {"redirect": "127.0.0.1:18195"}}),
        "socks5_listen": "127.0.0.1", "socks5_port": 19995,
        "tun_iface": iface, "mtu": 1500, "bypass_networks": "192.0.2.0/24",
    }
    generated = subprocess.run([
        "php", "-r", "require $argv[1]; $c=json_decode(stream_get_contents(STDIN),true); "
        "echo json_encode(['json'=>xray_build_config($c),'yaml'=>xray_build_t2s_config($c)],JSON_THROW_ON_ERROR);",
        str(Path(__file__).resolve().parents[1]/"plugin/scripts/Xray/xray-config.php"),
    ], input=json.dumps(settings), text=True, capture_output=True, check=True, timeout=8)
    built = json.loads(generated.stdout)
    xray_config = Path(directory) / "xray-candidate"
    xray_config.write_text(json.dumps(built["json"]))
    xray_config.chmod(0o600)
    run([sys.argv[2], "run", "-test", "-c", str(xray_config), "-format=json"])
    xray_log = Path(directory) / "xray.log"
    xray_output = xray_log.open("wb")
    xray_process = subprocess.Popen([sys.argv[2], "run", "-c", str(xray_config), "-format=json"],
                                    stdout=xray_output, stderr=subprocess.STDOUT,
                                    start_new_session=True)
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", 19995), timeout=0.2):
                break
        except OSError:
            if xray_process.poll() is not None:
                raise RuntimeError("Xray process exited: " + xray_log.read_text(errors="replace"))
            time.sleep(0.15)
    else:
        raise TimeoutError("Xray SOCKS listener not ready")
    cfg = Path(directory) / "tun2socks.yaml"
    cfg.write_text(built["yaml"])
    log = Path(directory) / "tun2socks.log"
    with log.open("wb") as output:
        try:
            process = subprocess.Popen([binary, "--config", str(cfg)],
                                       stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                details = tun_info()
                m = re.search(r"Opened by PID\s+(\d+)", details.stdout)
                if m and int(m.group(1)) == process.pid:
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"tun2socks exited: {process.returncode}")
                time.sleep(0.2)
            else:
                raise TimeoutError("tun2socks did not acquire NativeTun")
            run(["/sbin/ifconfig", iface, "inet", "10.253.95.1/30", "up"])
            run(["/sbin/route", "add", "-host", target, "-iface", iface])
            route_added = True
            with socket.create_connection((target, port), timeout=8) as client:
                client.settimeout(8)
                client.sendall(b"GET /tun-smoke HTTP/1.1\r\nHost: smoke\r\nConnection: close\r\n\r\n")
                response = b""
                while True:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            assert payload in response, f"No HTTP reply via SOCKS5: {response!r}"
            assert received == ["HTTP"], f"Local HTTP destination mismatch: {received}"
            assert not proxy_error, proxy_error
            print("PASS: FreeBSD TCP -> TUN -> tun2socks -> real Xray-core SOCKS -> freedom redirect -> HTTP", flush=True)
        finally:
            if xray_process and xray_process.poll() is None:
                os.killpg(xray_process.pid, signal.SIGTERM)
                xray_process.wait(timeout=6)
            xray_output.close()
            if xray_process and xray_process.returncode not in (0, -signal.SIGTERM):
                print(xray_log.read_text(errors="replace")[-3000:], file=sys.stderr)
            if route_added:
                run(["/sbin/route", "delete", "-host", target])
            if process and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=4)
            info = tun_info()
            if info.returncode == 0:
                if re.search(r"Opened by PID\s+\d+", info.stdout):
                    raise AssertionError("Refusing to destroy still-owned TUN")
                run(["/sbin/ifconfig", iface, "destroy"])
            if not stop.wait(1):
                print("Local HTTP server was not reached", file=sys.stderr)
            if proxy_error:
                print("SOCKS mock errors: " + repr(proxy_error), file=sys.stderr)
            if process and process.returncode not in (0, -signal.SIGTERM):
                print(log.read_text(errors="replace")[-3000:], file=sys.stderr)
