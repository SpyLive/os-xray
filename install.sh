#!/bin/sh
# os-xray OPNsense Plugin Installer
# Xray-core (VLESS+Reality) + tun2socks
# Tested target: OPNsense 26.7.x / FreeBSD 15.1 amd64
# Author: Меркулов Павел Сергеевич
#
# Usage:
#   sh install.sh            — install
#   sh install.sh uninstall  — remove

# Итерация 3:
#   - set -u: защита от неинициализированных переменных
#   - detect_existing(): PHP-парсинг вместо grep/sed/awk
#   - check_port(): проверка занятости SOCKS5 порта
#   - die()/warn(): унифицированный вывод ошибок
#   - PLUGIN_VERSION в баннере

set -e
set -u

PLUGIN_VERSION="3.1.0"
PLUGIN_DIR="$(dirname "$0")/plugin"
VERSION_FILE="/usr/local/opnsense/mvc/app/models/OPNsense/Xray/version.txt"

# Tested production matrix. Xray 26.9.9 is newer but upstream marks it prerelease;
# 3x-ui 3.8.5 uses it. The firewall client defaults to the latest stable Xray.
XRAY_VERSION="26.3.27"
XRAY_URL="https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-freebsd-64.zip"
XRAY_SHA256="c0fcd6962fc8a382e14441370ddbdb6a56e7108c73e817938c626770ac4a1358"
T2S_VERSION="2.7.0"
T2S_URL="https://github.com/xjasonlyu/tun2socks/releases/download/v${T2S_VERSION}/tun2socks-freebsd-amd64.zip"
T2S_SHA256="3ebb747aa83ee3157330beb324bbeaf9a742db6a8d24b9bbc96a4125aaeeeaea"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
warn() { echo "[WARN] $*" >&2; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

verify_sha256() {
    _FILE="$1"
    _EXPECTED="$2"
    command -v sha256 >/dev/null 2>&1 || die "sha256 utility not found"
    _ACTUAL=$(sha256 -q "$_FILE" 2>/dev/null || true)
    [ -n "$_ACTUAL" ] || die "Could not calculate SHA256 for $_FILE"
    [ "$_ACTUAL" = "$_EXPECTED" ] || die "SHA256 mismatch for $_FILE (got $_ACTUAL)"
}

download_verified() {
    _URL="$1"
    _DEST="$2"
    _SHA="$3"
    rm -f "$_DEST"
    fetch -o "$_DEST" "$_URL" || die "Download failed: $_URL"
    verify_sha256 "$_DEST" "$_SHA"
}

# ─────────────────────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────────────────────
if [ "${1:-}" = "uninstall" ]; then
    echo "==> Stopping services..."
    /usr/local/opnsense/scripts/Xray/xray-service-control.php stop 2>/dev/null || true

    echo "==> Cleaning runtime files..."
    # v2.0.0: per-instance PID, lock, flag, config files
    rm -f /var/run/xray_core_*.pid /var/run/tun2socks_*.pid
    rm -f /var/run/xray_start_*.lock /var/run/xray_stopped_*.flag
    rm -f /usr/local/etc/xray-core/config-*.json
    rm -f /usr/local/tun2socks/config-*.yaml
    # v1.x legacy files
    rm -f /var/run/xray_core.pid /var/run/tun2socks.pid
    rm -f /var/run/xray_start.lock /var/run/xray_stopped.flag

    echo "==> Removing plugin files..."
    rm -f  /usr/local/opnsense/scripts/Xray/xray-service-control.php
    rm -f  /usr/local/opnsense/scripts/Xray/xray-testconnect.php
    rm -f  /usr/local/opnsense/scripts/Xray/xray-watchdog.php
    rm -f  /usr/local/opnsense/scripts/Xray/xray-ifstats.php
    rmdir  /usr/local/opnsense/scripts/Xray 2>/dev/null || true
    # BUG-11: удаляем конфиг ротации логов newsyslog
    rm -f  /etc/newsyslog.conf.d/xray.conf
    # Логи xray-core оставляем для истории (удалять вручную при необходимости):
    # rm -f /var/log/xray-core.log /var/log/xray-core.log.0.bz2 /var/log/xray-core.log.1.bz2 /var/log/xray-core.log.2.bz2
    rm -f  /usr/local/opnsense/service/conf/actions.d/actions_xray.conf
    rm -rf /usr/local/opnsense/mvc/app/models/OPNsense/Xray       # включает ACL/, Menu/, version.txt
    rm -rf /usr/local/opnsense/mvc/app/controllers/OPNsense/Xray
    rm -rf /usr/local/opnsense/mvc/app/views/OPNsense/Xray
    rm -f  /usr/local/etc/inc/plugins.inc.d/xray.inc
    rm -f  /usr/local/etc/rc.syshook.d/start/50-xray

    echo "==> Restarting configd..."
    service configd restart

    echo "==> Clearing cache..."
    rm -f /var/lib/php/tmp/opnsense_menu_cache.xml

    echo ""
    echo "=============================="
    echo "  os-xray plugin removed."
    echo "=============================="
    echo "Refresh browser with Ctrl+F5."
    exit 0
fi

# ─────────────────────────────────────────────────────────────────────────────
# DETECT EXISTING CONFIG
#
# Итерация 3: переписан с grep/sed/awk на PHP json_decode() + yaml-парсер.
#
# Почему grep/sed ненадёжны:
#   - минифицированный JSON (всё в одну строку): grep -o не найдёт
#   - нестандартные пробелы вокруг ":" → sed-паттерн не сработает
#   - экранированные символы внутри строк → ложные совпадения
#   - поля "port" встречаются в нескольких местах → grep берёт не то
#
# Решение: PHP выводит KEY='VALUE' в tmpfile → shell сорсит его.
# Передача путей через env-переменные (не через аргументы) — без инъекций.
# Control-chars в значениях фильтруются перед записью в shell-файл.
# ─────────────────────────────────────────────────────────────────────────────
detect_existing() {
    # v2.0.0: per-instance configs (config-<uuid>.json), fallback to old single config.json
    XRAY_JSON=""
    for _F in /usr/local/etc/xray-core/config-*.json /usr/local/etc/xray-core/config.json; do
        [ -f "$_F" ] && XRAY_JSON="$_F" && break
    done
    XRAY_JSON="${XRAY_JSON:-/usr/local/etc/xray-core/config.json}"

    T2S_YAML=""
    for _F in /usr/local/tun2socks/config-*.yaml /usr/local/tun2socks/config.yaml; do
        [ -f "$_F" ] && T2S_YAML="$_F" && break
    done
    T2S_YAML="${T2S_YAML:-/usr/local/tun2socks/config.yaml}"

    # Явная инициализация (set -u не допускает необъявленных переменных)
    EXIST_SERVER=""
    EXIST_PORT_JSON=""
    EXIST_UUID=""
    EXIST_SNI=""
    EXIST_PUBKEY=""
    EXIST_SHORTID=""
    EXIST_FP=""
    EXIST_FLOW=""
    EXIST_OUTBOUND=""
    EXIST_SOCKS5=""
    EXIST_TUN=""
    EXIST_MTU=""
    EXIST_TUN_IP=""
    EXIST_TUN_GW=""
    HAS_EXISTING_CONFIG=0

    # PHP парсит оба файла и пишет shell-присваивания в tmpfile.
    # Tmpfile сорсится в текущем shell — переменные видны после return.
    _DET_TMP="/tmp/.xray_detect_$$.sh"

    _XRAY_JSON="$XRAY_JSON" _T2S_YAML="$T2S_YAML" \
    php -r '
        $xrayJson = getenv("_XRAY_JSON");
        $t2sYaml  = getenv("_T2S_YAML");

        $out = [
            "server"  => "",
            "port"    => "",
            "uuid"    => "",
            "sni"     => "",
            "pubkey"  => "",
            "shortid" => "",
            "fp"      => "",
            "flow"     => "",
            "outbound" => "",
            "socks5"   => "",
            "tun"     => "",
            "mtu"     => "",
        ];

        // ── Парсим xray config.json ──────────────────────────────────────────
        if (is_file($xrayJson)) {
            $raw = file_get_contents($xrayJson);
            if ($raw !== false) {
                $j = json_decode($raw, true);
                if (is_array($j)) {
                    $proxy = null;
                    foreach (($j["outbounds"] ?? []) as $candidate) {
                        if (is_array($candidate) && ($candidate["protocol"] ?? "") === "vless") {
                            $proxy = $candidate;
                            break;
                        }
                    }
                    if ($proxy === null) {
                        foreach (($j["outbounds"] ?? []) as $candidate) {
                            if (!is_array($candidate)) continue;
                            $proto = (string)($candidate["protocol"] ?? "");
                            if (!in_array($proto, ["freedom", "blackhole", "dns"], true)) {
                                $proxy = $candidate;
                                break;
                            }
                        }
                    }

                    if (is_array($proxy)) {
                        $settings = $proxy["settings"] ?? [];
                        if (isset($settings["address"])) {
                            $out["server"] = (string)($settings["address"] ?? "");
                            $port = (int)($settings["port"] ?? 0);
                            $out["port"] = $port > 0 ? (string)$port : "";
                            $out["uuid"] = (string)($settings["id"] ?? "");
                            $out["flow"] = (string)($settings["flow"] ?? "");
                        } else {
                            $vnext = $settings["vnext"][0] ?? [];
                            $user  = $vnext["users"][0] ?? [];
                            $out["server"] = (string)($vnext["address"] ?? "");
                            $port = (int)($vnext["port"] ?? 0);
                            $out["port"] = $port > 0 ? (string)$port : "";
                            $out["uuid"] = (string)($user["id"] ?? "");
                            $out["flow"] = (string)($user["flow"] ?? "");
                        }

                        $rs = $proxy["streamSettings"]["realitySettings"] ?? [];
                        $out["sni"]     = (string)($rs["serverName"] ?? "");
                        $out["pubkey"]  = (string)($rs["password"] ?? ($rs["publicKey"] ?? ""));
                        $out["shortid"] = (string)($rs["shortId"] ?? "");
                        $out["fp"]      = (string)($rs["fingerprint"] ?? "");
                        $out["outbound"] = base64_encode(json_encode(
                            $proxy,
                            JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
                        ));
                    }

                    foreach (($j["inbounds"] ?? []) as $inbound) {
                        if (($inbound["protocol"] ?? "") === "socks") {
                            $s5 = (int)($inbound["port"] ?? 0);
                            $out["socks5"] = $s5 > 0 ? (string)$s5 : "";
                            break;
                        }
                    }
                }
            }
        }

        // ── Парсим tun2socks config.yaml ─────────────────────────────────────
        // Формат: "ключ: значение" без вложенности и кавычек
        if (is_file($t2sYaml)) {
            foreach (file($t2sYaml, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
                $line = trim($line);
                if ($line === "" || $line[0] === "#") continue;
                $colonPos = strpos($line, ":");
                if ($colonPos === false) continue;
                $key = trim(substr($line, 0, $colonPos));
                $val = trim(substr($line, $colonPos + 1));
                switch ($key) {
                    case "device":
                        $out["tun"] = $val;
                        break;
                    case "mtu":
                        $out["mtu"] = $val;
                        break;
                    case "proxy":
                        // "proxy: socks5://127.0.0.1:10808" → извлекаем порт
                        if ($out["socks5"] === "" && preg_match("/:(\\d+)$/", $val, $m)) {
                            $out["socks5"] = $m[1];
                        }
                        break;
                }
            }
        }

        // ── Выводим EXIST_KEY='"'"'VALUE'"'"' для shell source ───────────────
        // Экранирование: убираем control-chars, затем экранируем одинарные кавычки.
        // Паттерн '\''  означает: закрыть одинарную кавычку, вставить экранированную, открыть снова.
        foreach ($out as $k => $v) {
            $v    = preg_replace("/[\\x00-\\x1F\\x7F]/u", "", (string)$v);
            $safe = str_replace("'\''", "'\''\\'\'''\''", $v);
            echo "EXIST_" . strtoupper($k) . "='\''" . $safe . "'\''\n";
        }
    ' 2>/dev/null > "$_DET_TMP"

    # shellcheck disable=SC1090
    . "$_DET_TMP"
    rm -f "$_DET_TMP"

    # Читаем IP текущего TUN-интерфейса (если он уже поднят в системе)
    _TUN_IFACE="${EXIST_TUN:-proxytun2socks0}"
    EXIST_TUN_IP=$(ifconfig "$_TUN_IFACE" 2>/dev/null | awk '/inet /{print $2}') || EXIST_TUN_IP=""
    EXIST_TUN_GW=$(ifconfig "$_TUN_IFACE" 2>/dev/null | awk '/inet /{print $4}') || EXIST_TUN_GW=""

    if [ -n "$EXIST_OUTBOUND" ] || [ -n "$EXIST_SERVER" ] || [ -n "$EXIST_UUID" ]; then
        HAS_EXISTING_CONFIG=1
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# CHECK PORT AVAILABILITY
#
# Итерация 3: проверяет что socks5_port не занят другим процессом.
# sockstat(1) — стандартная FreeBSD утилита (аналог ss/netstat).
# Не прерывает установку — только предупреждение, чтобы не блокировать
# обновление уже работающего xray-core который сам держит этот порт.
# ─────────────────────────────────────────────────────────────────────────────
check_port() {
    _PORT="${1:-10808}"
    if sockstat -4l 2>/dev/null | awk '{print $6}' | grep -q ":${_PORT}$"; then
        warn "Port ${_PORT} is already in use by another process:"
        sockstat -4l 2>/dev/null | awk -v p=":${_PORT}" '$6 ~ p {print "       " $0}'
        warn "socks5_port=${_PORT} may conflict. Change it in GUI after install if needed."
        return 1
    fi
    return 0
}

# ─────────────────────────────────────────────────────────────────────────────
# IMPORT EXISTING CONFIG INTO OPNsense config.xml
# ─────────────────────────────────────────────────────────────────────────────
import_existing_config() {
    echo "==> Importing existing xray/tun2socks config into OPNsense..."

    _SOCKS5="${EXIST_SOCKS5:-10808}"
    _TUN="${EXIST_TUN:-proxytun2socks0}"
    _MTU="${EXIST_MTU:-1500}"
    _FLOW="${EXIST_FLOW:-xtls-rprx-vision}"
    _FP="${EXIST_FP:-chrome}"
    _SNI="${EXIST_SNI:-}"
    _PUBKEY="${EXIST_PUBKEY:-}"
    _SHORTID="${EXIST_SHORTID:-}"
    _SERVER="${EXIST_SERVER:-}"
    _UUID="${EXIST_UUID:-}"
    _PORT="${EXIST_PORT_JSON:-443}"
    _OUTBOUND_B64="${EXIST_OUTBOUND:-}"

    _TMP_JSON="/tmp/.xray_import_$$.json"

    _S="$_SERVER" _P="$_PORT" _U="$_UUID" _FL="$_FLOW" \
    _SN="$_SNI" _PK="$_PUBKEY" _SI="$_SHORTID" _FP2="$_FP" \
    _S5="$_SOCKS5" _TN="$_TUN" _MT="$_MTU" _OB="$_OUTBOUND_B64" \
    php -r '
        echo json_encode([
            "server"       => getenv("_S"),
            "port"         => (int)getenv("_P") ?: 443,
            "uuid"         => getenv("_U"),
            "flow"         => getenv("_FL"),
            "sni"          => getenv("_SN"),
            "pubkey"       => getenv("_PK"),
            "shortid"      => getenv("_SI"),
            "fp"           => getenv("_FP2"),
            "socks5"       => (int)getenv("_S5") ?: 10808,
            "tun"          => getenv("_TN"),
            "mtu"          => (int)getenv("_MT") ?: 1500,
            "outbound_b64" => getenv("_OB"),
        ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    ' > "$_TMP_JSON" 2>/dev/null

    if [ ! -s "$_TMP_JSON" ]; then
        warn "Could not serialize config — fill fields manually in GUI."
        rm -f "$_TMP_JSON"
        return
    fi

    _XRAY_JSON="$_TMP_JSON" php << 'PHPEOF'
<?php
set_include_path('/usr/local/etc/inc' . PATH_SEPARATOR . get_include_path());
require_once('config.inc');

$jsonFile = getenv('_XRAY_JSON');
$raw = file_get_contents($jsonFile);
if ($raw === false) { echo "ERROR: cannot read tmp json\n"; exit(1); }
$d = json_decode($raw, true);
if (!is_array($d)) { echo "ERROR: bad json in tmp file\n"; exit(1); }

$outbound = null;
$obRaw = base64_decode((string)($d['outbound_b64'] ?? ''), true);
if ($obRaw !== false && $obRaw !== '') {
    $candidate = json_decode($obRaw, true);
    if (is_array($candidate) && !empty($candidate['protocol'])) {
        $outbound = $candidate;
    }
}

if ($outbound === null && !empty($d['server']) && !empty($d['uuid'])) {
    $reality = [
        'serverName'  => (string)($d['sni'] ?? ''),
        'fingerprint' => (string)($d['fp'] ?? 'chrome'),
        'shortId'     => (string)($d['shortid'] ?? ''),
        'spiderX'     => '/',
    ];
    if (!empty($d['pubkey'])) {
        $reality['publicKey'] = (string)$d['pubkey'];
    }
    $outbound = [
        'tag' => 'proxy',
        'protocol' => 'vless',
        'settings' => [
            'address' => (string)$d['server'],
            'port' => (int)($d['port'] ?? 443),
            'id' => (string)$d['uuid'],
            'encryption' => 'none',
            'flow' => (string)($d['flow'] ?? ''),
        ],
        'streamSettings' => [
            'network' => 'tcp',
            'security' => 'reality',
            'tcpSettings' => ['header' => ['type' => 'none']],
            'realitySettings' => $reality,
        ],
    ];
}

if ($outbound === null) {
    echo "ERROR: no usable proxy outbound found\n";
    exit(1);
}

$cfg = OPNsense\Core\Config::getInstance();
$obj = $cfg->object();
if (!isset($obj->OPNsense))       { $obj->addChild('OPNsense'); }
if (!isset($obj->OPNsense->xray)) { $obj->OPNsense->addChild('xray'); }
$x = $obj->OPNsense->xray;
if (!isset($x->general))          { $x->addChild('general'); }
if (!isset($x->instances))        { $x->addChild('instances'); }

$inst = $x->instances->addChild('instance');
$instUuid = sprintf(
    '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
    mt_rand(0, 0xffff), mt_rand(0, 0xffff),
    mt_rand(0, 0xffff),
    mt_rand(0, 0x0fff) | 0x4000,
    mt_rand(0, 0x3fff) | 0x8000,
    mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
);
$inst->addAttribute('uuid', $instUuid);

$x->general->enabled = '1';
$inst->addChild('enabled', '1');
$inst->addChild('name', 'default');
$inst->addChild('outbound_config', htmlspecialchars(
    json_encode($outbound, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
    ENT_XML1 | ENT_QUOTES,
    'UTF-8'
));
$inst->addChild('socks5_listen', '127.0.0.1');
$inst->addChild('socks5_port', (string)$d['socks5']);
$inst->addChild('tun_interface', (string)$d['tun']);
$inst->addChild('mtu', (string)$d['mtu']);
$inst->addChild('bypass_networks', '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16');
$inst->addChild('loglevel', 'warning');

$cfg->save();
echo "Config imported OK\n";
PHPEOF

    _PHP_EXIT=$?
    rm -f "$_TMP_JSON"

    if [ "$_PHP_EXIT" -eq 0 ]; then
        echo "[OK]  Existing config imported into OPNsense using outbound_config."
    else
        warn "Could not auto-import config — fill fields manually in GUI."
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

# install_tree <src_dir> <dst_dir> <file_mode>
# Recursive installation of each file from <src_dir> to <dst_dir> with <file_mode> modifier
install_tree() {
    _src="$1"
    _dst="$2"
    _fmode="${3:-0644}"

    find "$_src" -mindepth 1 -type d | while IFS= read -r _dir; do
        _rel="${_dir#$_src}"
        install -d "${_dst}${_rel}"
    done
    find "$_src" -type f | while IFS= read -r _file; do
        _rel="${_file#$_src}"
        install -m "$_fmode" "$_file" "${_dst}${_rel}"
    done
}

# ─────────────────────────────────────────────────────────────────────────────
# INSTALL
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# VERSION CHECK & CONFIRMATION
# ─────────────────────────────────────────────────────────────────────────────
CURRENT_VERSION="not installed"
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION=$(cat "$VERSION_FILE" 2>/dev/null || echo "unknown")
fi

echo "============================================================"
echo "  os-xray plugin installer"
echo "============================================================"
echo ""
echo "  Current version : ${CURRENT_VERSION}"
echo "  New version     : ${PLUGIN_VERSION}"
echo ""

if [ "$CURRENT_VERSION" = "$PLUGIN_VERSION" ]; then
    echo "  Version ${PLUGIN_VERSION} is already installed."
    printf "  Reinstall? [y/N] "
    read -r _CONFIRM < /dev/tty 2>/dev/null || _CONFIRM="n"
    case "$_CONFIRM" in
        [yY]*) ;;
        *) echo "  Installation cancelled."; exit 0 ;;
    esac
elif [ "$CURRENT_VERSION" != "not installed" ]; then
    printf "  Upgrade from ${CURRENT_VERSION} to ${PLUGIN_VERSION}? [Y/n] "
    read -r _CONFIRM < /dev/tty 2>/dev/null || _CONFIRM="y"
    case "$_CONFIRM" in
        [nN]*) echo "  Installation cancelled."; exit 0 ;;
        *) ;;
    esac
else
    printf "  Install version ${PLUGIN_VERSION}? [Y/n] "
    read -r _CONFIRM < /dev/tty 2>/dev/null || _CONFIRM="y"
    case "$_CONFIRM" in
        [nN]*) echo "  Installation cancelled."; exit 0 ;;
        *) ;;
    esac
fi

echo ""

# ── Шаг 1: Проверка бинарников ───────────────────────────────────────────────
echo "==> Step 1: Checking tested binary matrix..."
BINARIES_OK=1

_FB_VER=$(freebsd-version -u 2>/dev/null || uname -r)
_ARCH=$(uname -m)
echo "[INFO] FreeBSD: $_FB_VER"
echo "[INFO] Architecture: $_ARCH"
echo "[INFO] Tested matrix: Xray ${XRAY_VERSION}, tun2socks ${T2S_VERSION}"

if [ "$_ARCH" != "amd64" ]; then
    die "This fork currently pins/checks amd64 artifacts only (detected $_ARCH)."
fi

_XRAY_INSTALL=0
if [ ! -x /usr/local/bin/xray-core ]; then
    warn "xray-core not found; tested version ${XRAY_VERSION} will be installed."
    _XRAY_INSTALL=1
else
    XRAY_VER=$(/usr/local/bin/xray-core version 2>/dev/null | head -1 || echo 'unknown')
    echo "[OK]  xray-core: $XRAY_VER"
    case "$XRAY_VER" in
        *"Xray ${XRAY_VERSION}"*) ;;
        *)
            warn "Installed Xray differs from tested stable ${XRAY_VERSION}."
            printf "  Replace it with tested Xray ${XRAY_VERSION}? [y/N] "
            read -r _XRAY_CONFIRM < /dev/tty 2>/dev/null || _XRAY_CONFIRM="n"
            case "$_XRAY_CONFIRM" in [yY]*) _XRAY_INSTALL=1 ;; esac
            ;;
    esac
fi

if [ "$_XRAY_INSTALL" = "1" ]; then
    _XRAY_ZIP="/tmp/os-xray-xray-${XRAY_VERSION}.zip"
    echo "  Downloading Xray ${XRAY_VERSION}..."
    download_verified "$XRAY_URL" "$_XRAY_ZIP" "$XRAY_SHA256"
    rm -rf /tmp/os-xray-xray-unpack
    mkdir -p /tmp/os-xray-xray-unpack
    unzip -oq "$_XRAY_ZIP" -d /tmp/os-xray-xray-unpack || die "Could not unpack Xray archive"
    [ -x /tmp/os-xray-xray-unpack/xray ] || die "xray binary missing from archive"
    if [ -x /usr/local/bin/xray-core ]; then
        cp -p /usr/local/bin/xray-core "/usr/local/bin/xray-core.bak.$(date +%Y%m%d%H%M%S)"
    fi
    install -m 0755 /tmp/os-xray-xray-unpack/xray /usr/local/bin/xray-core
    rm -rf "$_XRAY_ZIP" /tmp/os-xray-xray-unpack
    XRAY_VER=$(/usr/local/bin/xray-core version 2>/dev/null | head -1 || echo 'unknown')
    case "$XRAY_VER" in *"Xray ${XRAY_VERSION}"*) ;; *) die "Installed Xray version check failed: $XRAY_VER" ;; esac
    echo "[OK]  xray-core installed: $XRAY_VER"
fi

_T2S_INSTALL=0
if [ ! -x /usr/local/tun2socks/tun2socks ]; then
    warn "tun2socks not found; tested version ${T2S_VERSION} will be installed."
    _T2S_INSTALL=1
else
    T2S_VER=$(/usr/local/tun2socks/tun2socks --version 2>&1 | head -1 || echo 'unknown')
    echo "[OK]  tun2socks: $T2S_VER"
    case "$T2S_VER" in
        *"${T2S_VERSION}"*) ;;
        *)
            warn "Installed tun2socks differs from tested ${T2S_VERSION}."
            printf "  Replace it with tested tun2socks ${T2S_VERSION}? [y/N] "
            read -r _T2S_CONFIRM < /dev/tty 2>/dev/null || _T2S_CONFIRM="n"
            case "$_T2S_CONFIRM" in [yY]*) _T2S_INSTALL=1 ;; esac
            ;;
    esac
fi

if [ "$_T2S_INSTALL" = "1" ]; then
    _T2S_ZIP="/tmp/os-xray-tun2socks-${T2S_VERSION}.zip"
    echo "  Downloading tun2socks ${T2S_VERSION}..."
    download_verified "$T2S_URL" "$_T2S_ZIP" "$T2S_SHA256"
    rm -rf /tmp/os-xray-t2s-unpack
    mkdir -p /tmp/os-xray-t2s-unpack
    unzip -oq "$_T2S_ZIP" -d /tmp/os-xray-t2s-unpack || die "Could not unpack tun2socks archive"
    _T2S_SRC=$(find /tmp/os-xray-t2s-unpack -type f -name 'tun2socks-freebsd-amd64*' | head -1)
    [ -n "$_T2S_SRC" ] || die "tun2socks binary missing from archive"
    if [ -x /usr/local/tun2socks/tun2socks ]; then
        cp -p /usr/local/tun2socks/tun2socks "/usr/local/tun2socks/tun2socks.bak.$(date +%Y%m%d%H%M%S)"
    fi
    install -d -m 0750 /usr/local/tun2socks
    install -m 0755 "$_T2S_SRC" /usr/local/tun2socks/tun2socks
    rm -rf "$_T2S_ZIP" /tmp/os-xray-t2s-unpack
    T2S_VER=$(/usr/local/tun2socks/tun2socks --version 2>&1 | head -1 || echo 'unknown')
    case "$T2S_VER" in *"${T2S_VERSION}"*) ;; *) die "Installed tun2socks version check failed: $T2S_VER" ;; esac
    echo "[OK]  tun2socks installed: $T2S_VER"
fi

[ -x /usr/local/bin/xray-core ] || BINARIES_OK=0
[ -x /usr/local/tun2socks/tun2socks ] || BINARIES_OK=0
if [ "$BINARIES_OK" = "0" ]; then
    die "Required binaries are not available after Step 1."
fi

# ── Шаг 2: Определение существующего конфига ─────────────────────────────────
echo ""
echo "==> Step 2: Detecting existing configuration..."
detect_existing

if [ "$HAS_EXISTING_CONFIG" = "1" ]; then
    echo "[FOUND] Existing xray/tun2socks config detected:"
    [ -n "${EXIST_SERVER:-}"  ] && echo "        Server:      ${EXIST_SERVER}:${EXIST_PORT_JSON:-443}"
    [ -n "${EXIST_UUID:-}"    ] && echo "        UUID:        ${EXIST_UUID}"
    [ -n "${EXIST_FLOW:-}"    ] && echo "        Flow:        ${EXIST_FLOW}"
    [ -n "${EXIST_SNI:-}"     ] && echo "        SNI:         ${EXIST_SNI}"
    [ -n "${EXIST_PUBKEY:-}"  ] && echo "        PublicKey:   ${EXIST_PUBKEY}"
    [ -n "${EXIST_SHORTID:-}" ] && echo "        ShortID:     ${EXIST_SHORTID}"
    [ -n "${EXIST_TUN:-}"     ] && echo "        TUN:         ${EXIST_TUN}"
    [ -n "${EXIST_TUN_IP:-}"  ] && echo "        TUN IP:      ${EXIST_TUN_IP}"
    [ -n "${EXIST_TUN_GW:-}"  ] && echo "        TUN Gateway: ${EXIST_TUN_GW}"
    [ -n "${EXIST_MTU:-}"     ] && echo "        MTU:         ${EXIST_MTU}"
    [ -n "${EXIST_SOCKS5:-}"  ] && echo "        SOCKS5 port: ${EXIST_SOCKS5}"
else
    echo "[INFO] No existing xray/tun2socks config found — fill fields manually in GUI."
fi

# ── Шаг 2.5: Проверка занятости SOCKS5 порта ─────────────────────────────────
echo ""
echo "==> Step 2.5: Checking SOCKS5 port availability..."
_CHECK_PORT="${EXIST_SOCKS5:-10808}"

# Если xray-core уже запущен — он сам держит порт, предупреждение лишнее
# v2.0.0: per-instance PID files
_XRAY_RUNNING=0
for _PIDFILE in /var/run/xray_core_*.pid /var/run/xray_core.pid; do
    [ -f "$_PIDFILE" ] || continue
    _XRAY_PID=$(cat "$_PIDFILE" 2>/dev/null || echo "0")
    if kill -0 "$_XRAY_PID" 2>/dev/null; then
        _XRAY_RUNNING=1
        break
    fi
done

if [ "$_XRAY_RUNNING" = "1" ]; then
    echo "[SKIP] xray-core is running — port ${_CHECK_PORT} is held by xray itself."
elif check_port "$_CHECK_PORT"; then
    echo "[OK]  Port ${_CHECK_PORT} is available."
fi
# check_port при занятом порте уже вывел warn — установка продолжается

# ── Шаг 3: Установка файлов плагина ──────────────────────────────────────────
echo ""
echo "==> Step 3: Installing plugin files..."

# PHP-scripts (executable)
install -d /usr/local/opnsense/scripts/Xray
install_tree "$PLUGIN_DIR/scripts/Xray" \
             "/usr/local/opnsense/scripts/Xray" 0755

# configd actions
install -d /usr/local/opnsense/service/conf/actions.d
install_tree "$PLUGIN_DIR/service/conf/actions.d" \
             "/usr/local/opnsense/service/conf/actions.d" 0644

# MVC: models, controllers, views (including subdirectories — partials и т.д.)
install -d /usr/local/opnsense/mvc/app/models/OPNsense/Xray
install_tree "$PLUGIN_DIR/mvc/app/models/OPNsense/Xray" \
             "/usr/local/opnsense/mvc/app/models/OPNsense/Xray" 0644

install -d /usr/local/opnsense/mvc/app/controllers/OPNsense/Xray
install_tree "$PLUGIN_DIR/mvc/app/controllers/OPNsense/Xray" \
             "/usr/local/opnsense/mvc/app/controllers/OPNsense/Xray" 0644

install -d /usr/local/opnsense/mvc/app/views/OPNsense/Xray
install_tree "$PLUGIN_DIR/mvc/app/views/OPNsense/Xray" \
             "/usr/local/opnsense/mvc/app/views/OPNsense/Xray" 0644

# System hooks
install -d /usr/local/etc/inc/plugins.inc.d
install_tree "$PLUGIN_DIR/etc/inc/plugins.inc.d" \
             "/usr/local/etc/inc/plugins.inc.d" 0644

install -d /usr/local/etc/rc.syshook.d/start
install_tree "$PLUGIN_DIR/etc/rc.syshook.d/start" \
             "/usr/local/etc/rc.syshook.d/start" 0755

install -d /etc/newsyslog.conf.d
install_tree "$PLUGIN_DIR/etc/newsyslog.conf.d" \
             "/etc/newsyslog.conf.d" 0644

# Working directories for xray-core and tun2socks
install -d -m 0750 /usr/local/etc/xray-core
install -d -m 0750 /usr/local/tun2socks

# Write version file
echo "$PLUGIN_VERSION" > "$VERSION_FILE"
chmod 0644 "$VERSION_FILE"

echo "[OK]  Plugin files installed."

# ── Шаг 4: Импорт существующего конфига ──────────────────────────────────────
# Импорт нужен только при ПЕРВОЙ установке — когда в config.xml ещё нет секции xray,
# но есть файловые конфиги от ручной установки xray-core/tun2socks.
# При обновлении (повторный install.sh) config.xml уже содержит настройки из GUI —
# перезаписывать их из файлового конфига нельзя (затрёт изменения пользователя).
echo ""
echo "==> Step 4: Importing existing config (if found)..."

CONFIG_XML_HAS_XRAY=0
NEEDS_MIGRATION=0
_PHP_OUT=$(php -r '
set_include_path("/usr/local/etc/inc" . PATH_SEPARATOR . get_include_path());
require_once("config.inc");
$cfg = OPNsense\Core\Config::getInstance()->object();

// v2.0.0: check new ArrayField structure first
$instances = $cfg->OPNsense->xray->instances ?? null;
if ($instances) {
    foreach ($instances->instance as $inst) {
        if ((string)($inst->outbound_config ?? "") !== "" ||
            (string)($inst->server_address ?? "") !== "" ||
            (string)($inst->vless_uuid ?? "") !== "") {
            echo "new";
            exit(0);
        }
    }
}

// v1.x: check old single-instance structure (needs migration)
$inst = $cfg->OPNsense->xray->instance ?? null;
if ($inst && ((string)($inst->server_address ?? "") !== "" || (string)($inst->vless_uuid ?? "") !== "" || (string)($inst->uuid ?? "") !== "")) {
    echo "old";
    exit(0);
}
' 2>/dev/null) || true
if [ "$_PHP_OUT" = "new" ]; then
    CONFIG_XML_HAS_XRAY=1
elif [ "$_PHP_OUT" = "old" ]; then
    CONFIG_XML_HAS_XRAY=1
    NEEDS_MIGRATION=1
fi

if [ "$CONFIG_XML_HAS_XRAY" = "1" ]; then
    echo "[SKIP] config.xml already has Xray settings (from GUI). Skipping file import to preserve your configuration."
elif [ "$HAS_EXISTING_CONFIG" = "1" ]; then
    import_existing_config
else
    echo "[SKIP] No existing config to import."
fi

# ── Шаг 4.5: Миграция v1.x → v3.0.0 (single instance → ArrayField) ─────────
if [ "$NEEDS_MIGRATION" = "1" ]; then
    echo ""
    echo "==> Step 4.5: Migrating config.xml from v1.x to v3.0.0 (ArrayField)..."

    _MIGRATE_OK=$(php << 'PHPEOF'
<?php
set_include_path('/usr/local/etc/inc' . PATH_SEPARATOR . get_include_path());
require_once('config.inc');

$cfg = OPNsense\Core\Config::getInstance();
$obj = $cfg->object();
$x   = $obj->OPNsense->xray ?? null;
if (!$x) { echo "SKIP"; exit(0); }

$old = $x->instance ?? null;
if (!$old) { echo "SKIP"; exit(0); }

// Уже есть новая структура — не мигрируем
if (isset($x->instances)) { echo "SKIP"; exit(0); }

// Копируем все поля из старого <instance> в новый <instances><instance uuid="...">
$instances = $x->addChild('instances');
$newInst   = $instances->addChild('instance');

// Генерируем UUID
$instUuid = sprintf(
    '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
    mt_rand(0, 0xffff), mt_rand(0, 0xffff),
    mt_rand(0, 0xffff),
    mt_rand(0, 0x0fff) | 0x4000,
    mt_rand(0, 0x3fff) | 0x8000,
    mt_rand(0, 0xffff), mt_rand(0, 0xffff), mt_rand(0, 0xffff)
);
$newInst->addAttribute('uuid', $instUuid);

// Копируем дочерние элементы
$fields = [
    'name', 'config_mode', 'custom_config',
    'server_address', 'server_port', 'vless_uuid', 'flow',
    'reality_sni', 'reality_pubkey', 'reality_shortid', 'reality_fingerprint',
    'socks5_listen', 'socks5_port', 'tun_interface', 'mtu',
    'bypass_networks', 'loglevel',
];
foreach ($fields as $f) {
    $val = (string)($old->$f ?? '');
    if ($val !== '') {
        $newInst->addChild($f, htmlspecialchars($val, ENT_XML1 | ENT_QUOTES, 'UTF-8'));
    }
}
// v2.0.0: rename old <uuid> to <vless_uuid> (avoid ArrayField UUID conflict)
$oldUuid = (string)($old->uuid ?? '');
if ($oldUuid !== '') {
    $newInst->addChild('vless_uuid', htmlspecialchars($oldUuid, ENT_XML1 | ENT_QUOTES, 'UTF-8'));
}

// Удаляем старый <instance> (singular)
$dom = dom_import_simplexml($old);
$dom->parentNode->removeChild($dom);

$cfg->save();
echo "OK";
PHPEOF
    ) || true

    if [ "$_MIGRATE_OK" = "OK" ]; then
        echo "[OK]  Migrated v1.x config to v3.0.0 ArrayField format."
    elif [ "$_MIGRATE_OK" = "SKIP" ]; then
        echo "[SKIP] Migration not needed."
    else
        warn "Migration failed. You may need to re-enter settings in the GUI."
    fi
fi

# ── Шаг 4.6: Rename <uuid> → <vless_uuid> in existing v2.0.0 instances ────────
# Avoids ArrayField UUID attribute conflict with VLESS user UUID field.
echo ""
echo "==> Step 4.6: Checking for <uuid> → <vless_uuid> rename..."

_RENAME_OK=$(php << 'PHPEOF'
<?php
set_include_path('/usr/local/etc/inc' . PATH_SEPARATOR . get_include_path());
require_once('config.inc');

$cfg = OPNsense\Core\Config::getInstance();
$obj = $cfg->object();
$instances = $obj->OPNsense->xray->instances ?? null;
if (!$instances) { echo "SKIP"; exit(0); }

$changed = false;
foreach ($instances->instance as $inst) {
    $oldVal = (string)($inst->uuid ?? '');
    $newVal = (string)($inst->vless_uuid ?? '');
    if ($oldVal !== '' && $newVal === '') {
        $inst->addChild('vless_uuid', htmlspecialchars($oldVal, ENT_XML1 | ENT_QUOTES, 'UTF-8'));
        $dom = dom_import_simplexml($inst->uuid);
        $dom->parentNode->removeChild($dom);
        $changed = true;
    }
}

if ($changed) {
    $cfg->save();
    echo "OK";
} else {
    echo "SKIP";
}
PHPEOF
) || true

if [ "$_RENAME_OK" = "OK" ]; then
    echo "[OK]  Renamed <uuid> to <vless_uuid> in config.xml."
elif [ "$_RENAME_OK" = "SKIP" ]; then
    echo "[SKIP] No rename needed."
else
    warn "Rename failed: $_RENAME_OK"
fi

# ── Шаг 4.6.5: Legacy wizard/custom fields → outbound_config ────────────────
echo ""
echo "==> Step 4.6.5: Migrating legacy instance fields to outbound_config..."

_LEGACY_OB_OK=$(php << 'PHPEOF'
<?php
set_include_path('/usr/local/etc/inc' . PATH_SEPARATOR . get_include_path());
require_once('config.inc');

$cfg = OPNsense\Core\Config::getInstance();
$obj = $cfg->object();
$instances = $obj->OPNsense->xray->instances ?? null;
if (!$instances) { echo "SKIP"; exit(0); }

$changed = false;
foreach ($instances->instance as $inst) {
    if (trim((string)($inst->outbound_config ?? '')) !== '') {
        continue;
    }

    $outbound = null;
    $custom = trim((string)($inst->custom_config ?? ''));
    if ($custom !== '') {
        $decoded = json_decode($custom, true);
        if (is_array($decoded)) {
            if (!empty($decoded['protocol'])) {
                $outbound = $decoded;
            } elseif (!empty($decoded['outbounds']) && is_array($decoded['outbounds'])) {
                foreach ($decoded['outbounds'] as $candidate) {
                    if (is_array($candidate) && ($candidate['protocol'] ?? '') === 'vless') {
                        $outbound = $candidate;
                        break;
                    }
                }
                if ($outbound === null) {
                    foreach ($decoded['outbounds'] as $candidate) {
                        if (!is_array($candidate)) continue;
                        $proto = (string)($candidate['protocol'] ?? '');
                        if (!in_array($proto, ['freedom', 'blackhole', 'dns'], true)) {
                            $outbound = $candidate;
                            break;
                        }
                    }
                }
            }
        }
    }

    if ($outbound === null) {
        $server = trim((string)($inst->server_address ?? ''));
        $uuid   = trim((string)($inst->vless_uuid ?? ''));
        if ($server !== '' && $uuid !== '') {
            $port  = (int)(string)($inst->server_port ?? '443');
            if ($port < 1 || $port > 65535) $port = 443;
            $flow  = (string)($inst->flow ?? 'xtls-rprx-vision');
            $sni   = (string)($inst->reality_sni ?? '');
            $key   = (string)($inst->reality_pubkey ?? '');
            $sid   = (string)($inst->reality_shortid ?? '');
            $fp    = (string)($inst->reality_fingerprint ?? 'chrome');
            if ($fp === '') $fp = 'chrome';

            $reality = [
                'serverName' => $sni,
                'fingerprint' => $fp,
                'shortId' => $sid,
                'spiderX' => '/',
            ];
            if ($key !== '') $reality['publicKey'] = $key;

            $outbound = [
                'tag' => 'proxy',
                'protocol' => 'vless',
                'settings' => [
                    'address' => $server,
                    'port' => $port,
                    'id' => $uuid,
                    'encryption' => 'none',
                    'flow' => $flow,
                ],
                'streamSettings' => [
                    'network' => 'tcp',
                    'security' => 'reality',
                    'tcpSettings' => ['header' => ['type' => 'none']],
                    'realitySettings' => $reality,
                ],
            ];
        }
    }

    if ($outbound !== null) {
        $json = json_encode($outbound, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $inst->addChild('outbound_config', htmlspecialchars($json, ENT_XML1 | ENT_QUOTES, 'UTF-8'));
        if (!isset($inst->enabled)) $inst->addChild('enabled', '1');
        $changed = true;
    }
}

if ($changed) {
    $cfg->save();
    echo "OK";
} else {
    echo "SKIP";
}
PHPEOF
) || true

if [ "$_LEGACY_OB_OK" = "OK" ]; then
    echo "[OK]  Legacy instances migrated to outbound_config."
elif [ "$_LEGACY_OB_OK" = "SKIP" ]; then
    echo "[SKIP] No legacy outbound migration needed."
else
    warn "Legacy outbound migration failed: $_LEGACY_OB_OK"
fi

# ── Шаг 4.7: Cleanup v1.x/v2.x PID files and stale flags ─────────────────────
echo ""
echo "==> Step 4.7: Cleaning up old runtime files..."
# v3.0.0: старые PID-файлы без UUID — tun2socks и xray-core не будут найдены per-instance stop
for _OLD_PID in /var/run/xray_core.pid /var/run/tun2socks.pid; do
    if [ -f "$_OLD_PID" ]; then
        _PID=$(cat "$_OLD_PID" 2>/dev/null)
        if [ -n "$_PID" ]; then
            kill "$_PID" 2>/dev/null || true
            echo "[OK]  Killed old process (PID=$_PID) from $_OLD_PID"
        fi
        rm -f "$_OLD_PID"
    fi
done
# Удаляем stale flags от некорректных UUID (e.g. xray_stopped_1.flag от configd %1)
rm -f /var/run/xray_stopped_1.flag 2>/dev/null
echo "[OK]  Old runtime files cleaned."

# ── Шаг 5: Перезапуск configd ─────────────────────────────────────────────────
echo ""
echo "==> Step 5: Restarting configd..."
service configd restart

# ── Шаг 6: Очистка кешей ──────────────────────────────────────────────────────
echo ""
echo "==> Step 6: Clearing cache..."
rm -f /var/lib/php/tmp/opnsense_menu_cache.xml
rm -f /var/lib/php/tmp/PHP_errors.log

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  os-xray v${PLUGIN_VERSION} installed successfully!"
echo "============================================================"
echo ""
echo "  Check version:  configctl xray version"
echo ""

if [ "$CONFIG_XML_HAS_XRAY" = "1" ]; then
    echo "  Existing Xray settings preserved in config.xml."
    echo ""
    echo "  Quick steps:"
    echo "  1. Refresh browser (Ctrl+F5) → VPN → Xray"
    echo "  2. Verify your settings are intact"
    echo "  3. Click Apply if needed"
    echo ""
elif [ "$HAS_EXISTING_CONFIG" = "1" ]; then
    echo "  Existing config was detected and imported automatically."
    echo "  Your settings are already loaded in the GUI."
    echo ""
    echo "  Quick steps:"
    echo "  1. Refresh browser (Ctrl+F5) → VPN → Xray"
    echo "  2. Check that Instance tab shows your settings"
    echo "  3. General tab → verify 'Enable Xray' is checked"
    echo "  4. Click Apply"
    echo ""
else
    echo "  Quick steps:"
    echo "  1. Refresh browser (Ctrl+F5) → VPN → Xray"
    echo "  2. Instance tab → 'Import VLESS link' → paste link → Parse & Fill"
    echo "  3. General tab → check 'Enable Xray'"
    echo "  4. Click Apply"
    echo ""
fi

MEMO_TUN="${EXIST_TUN:-proxytun2socks0}"
MEMO_TUN_IP="${EXIST_TUN_IP:-<TUN_IP>}"
MEMO_TUN_CIDR="${EXIST_TUN_IP:+${EXIST_TUN_IP}/30}"
MEMO_TUN_CIDR="${MEMO_TUN_CIDR:-<e.g. 10.255.0.1/30>}"

echo "  OPNsense interface & gateway setup:"
echo ""
echo "  5. Interfaces → Assignments"
echo "       + Add: $MEMO_TUN"
echo "       Enable interface ✓"
echo "       IPv4 Configuration Type: Static"
echo "       IPv4 Address: $MEMO_TUN_CIDR"
echo "       Prevent interface removal: ✓  (обязательно!)"
echo ""
echo "  6. System → Gateways → Configuration → Add"
echo "       Interface:             <your $MEMO_TUN interface name>"
echo "       Gateway IP:            $MEMO_TUN_IP"
echo "       Name:                  PROXYTUN_GW"
echo "       Far Gateway:           ✓  (обязательно!)"
echo "       Disable GW monitoring: ✓"
echo ""
echo "  7. Firewall → Aliases → Add"
echo "       Type: Network/Host(s)"
echo "       Add IPs/domains to route via VPN"
echo ""
echo "  8. Firewall → Rules → LAN → Add"
echo "       Source:      LAN net"
echo "       Destination: <your alias>"
echo "       Gateway:     PROXYTUN_GW"
echo ""
echo "  To uninstall: sh install.sh uninstall"
echo ""
