#!/usr/local/bin/php
<?php

set_include_path('/usr/local/etc/inc' . PATH_SEPARATOR . get_include_path());
require_once('config.inc');
require_once __DIR__ . '/xray-config.php';
require_once __DIR__ . '/xray-apply.php';

// ─── Shared constants (not per-instance) ─────────────────────────────────────
define('XRAY_BIN',          '/usr/local/bin/xray-core');
define('XRAY_CONF_DIR',     '/usr/local/etc/xray-core');
define('T2S_BIN',           '/usr/local/tun2socks/tun2socks');
define('T2S_CONF_DIR',      '/usr/local/tun2socks');
// BUG-7 FIX: stderr демонов в лог-файл вместо /dev/null
define('XRAY_DAEMON_LOG',   '/var/log/xray-core.log'); // общий лог (fallback)
define('XRAY_VERSION_FILE', '/usr/local/opnsense/mvc/app/models/OPNsense/Xray/version.txt');

function xray_valid_instance_uuid(string $uuid): bool
{
    return (bool)preg_match(
        '/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/D',
        $uuid
    );
}


// ─── Per-instance path functions ─────────────────────────────────────────────
// v3.0.0: все runtime-файлы именуются по UUID инстанса, чтобы N инстансов
// не конфликтовали за один PID-файл / конфиг / lock.
function xray_conf_path(string $inst_uuid): string
{
    return XRAY_CONF_DIR . "/config-{$inst_uuid}.json";
}
function xray_pid_path(string $inst_uuid): string
{
    return "/var/run/xray_core_{$inst_uuid}.pid";
}
function t2s_conf_path(string $inst_uuid): string
{
    return T2S_CONF_DIR . "/config-{$inst_uuid}.yaml";
}
function t2s_pid_path(string $inst_uuid): string
{
    return "/var/run/tun2socks_{$inst_uuid}.pid";
}
function xray_stopped_flag(string $inst_uuid): string
{
    return "/var/run/xray_stopped_{$inst_uuid}.flag";
}
function xray_instance_log(string $inst_uuid): string
{
    return "/var/log/xray-core-{$inst_uuid}.log";
}
function xray_applied_hash_path(string $inst_uuid): string
{
    return "/var/run/xray_applied_{$inst_uuid}.sha256";
}
function xray_instance_hash(array $c): string
{
    // Includes all parsed service settings; never persist the plaintext outbound.
    return hash('sha256', json_encode($c, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
}

// ─── Read config from OPNsense config.xml ────────────────────────────────────

/**
 * Парсит один <instance> SimpleXMLElement в плоский PHP-массив конфига.
 * globalEnabled — значение general.enabled (общий выключатель плагина).
 */
function xray_parse_instance($inst, bool $globalEnabled): array
{
    // B6: нормализация loglevel.
    // Старые: ключ "e" (до v1.0.1) → "error"
    // Новые:  ключ "loglevel_error" (v1.0.1+) → "error"
    $rawLevel = (string)($inst->loglevel ?? 'warning');
    $levelMap = [
        'e'              => 'error',
        'loglevel_error' => 'error',
    ];
    $loglevel = $levelMap[$rawLevel] ?? ($rawLevel ?: 'warning');

    return [
        'enabled'         => $globalEnabled && (string)($inst->enabled ?? '1') === '1',
        'name'            => (string)($inst->name             ?? 'default'),
        'outbound_config' => (string)($inst->outbound_config  ?? ''),
        'socks5_listen'   => (string)($inst->socks5_listen    ?? '127.0.0.1') ?: '127.0.0.1',
        'socks5_port'     => (int)(string)($inst->socks5_port ?? 10808) ?: 10808,
        'tun_iface'       => (string)($inst->tun_interface    ?? 'proxytun2socks0'),
        'mtu'             => (int)(string)($inst->mtu         ?? 1500),
        'loglevel'        => $loglevel,
        'bypass_networks' => (string)($inst->bypass_networks  ?? '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16')
                            ?: '10.0.0.0/8,172.16.0.0/12,192.168.0.0/16',
    ];
}

/**
 * Читает все инстансы из config.xml.
 * Возвращает массив, индексированный по inst_uuid (UUID инстанса OPNsense).
 */
function xray_get_all_instances(): array
{
    $cfg = OPNsense\Core\Config::getInstance()->object();
    $g   = $cfg->OPNsense->xray->general   ?? null;
    $ins = $cfg->OPNsense->xray->instances  ?? null;

    $globalEnabled = (string)($g->enabled ?? '0') === '1';

    if (!$ins) {
        return [];
    }

    $result = [];
    foreach ($ins->instance as $inst) {
        // SimpleXML: атрибуты читаются через $element['attr']
        $inst_uuid = (string)$inst['uuid'];
        if (!xray_valid_instance_uuid($inst_uuid)) {
            // Never allow config.xml data to influence runtime file paths unless
            // it is a canonical instance UUID.
            continue;
        }
        $c = xray_parse_instance($inst, $globalEnabled);
        $c['inst_uuid'] = $inst_uuid;
        $result[$inst_uuid] = $c;
    }
    return $result;
}

/**
 * Читает конфиг конкретного инстанса по его UUID.
 * Если UUID не указан — возвращает первый найденный инстанс (обратная совместимость).
 */
function xray_get_config(string $inst_uuid = ''): array
{
    $all = xray_get_all_instances();
    if (empty($all)) {
        return [];
    }
    if ($inst_uuid !== '') {
        return $all[$inst_uuid] ?? [];
    }
    // Возвращаем первый инстанс если UUID не указан
    return reset($all);
}


// ─── P2.5: xhttp/splithttp compatibility ─────────────────────────────────────
function xray_normalize_transport(string $json): string
{
    if (!file_exists(XRAY_BIN)) {
        return $json;
    }
    exec(escapeshellarg(XRAY_BIN) . ' version 2>/dev/null', $out);
    $verLine = $out[0] ?? '';

    if (preg_match('/Xray\s+1\./', $verLine)) {
        $json = str_replace('"xhttp"', '"splithttp"', $json);
        $json = str_replace('"xhttpSettings"', '"splithttpSettings"', $json);
    }

    return $json;
}

// NativeTun reports its actual owner even when a daemon PID file is missing.
function tun_owner_pid(string $iface): int
{
    if (!preg_match('/^[a-z][a-z0-9]{0,13}[0-9]$/D', $iface)) return -1;
    $lines = [];
    exec('/sbin/ifconfig ' . escapeshellarg($iface) . ' 2>/dev/null', $lines, $rc);
    if ($rc !== 0) return 0; // interface absent
    if (preg_match('/Opened by PID\s+(\d+)/', implode("\n", $lines), $m)) return (int)$m[1];
    return 0; // interface may exist without an open NativeTun handle
}

function tun_owned_by_instance(string $iface, string $uuid): bool
{
    $pid = tun_owner_pid($iface);
    if ($pid <= 0) return false;
    $command = trim((string)shell_exec('/bin/ps -ww -o command= -p ' . $pid . ' 2>/dev/null'));
    return strpos($command, T2S_BIN) !== false &&
           strpos($command, t2s_conf_path($uuid)) !== false;
}

// Used only when runtime files cannot identify the old interface. Read-only scan.
function xray_owned_tuns(string $uuid): ?array
{
    exec('/sbin/ifconfig -l 2>/dev/null', $out, $rc);
    if ($rc !== 0) return null;
    $owned = [];
    foreach (preg_split('/\s+/', trim(implode(' ', $out))) as $iface) {
        if (tun_owned_by_instance($iface, $uuid)) $owned[] = $iface;
    }
    return $owned;
}

function tun_wait_unowned(string $iface, int $oldOwner = 0): bool
{
    for ($i = 0; $i < 30; $i++) {
        $owner = tun_owner_pid($iface);
        if ($owner === 0) return true;
        if ($owner < 0) return false;
        usleep(100000);
    }
    echo "ERROR: TUN {$iface} is still owned by PID " . tun_owner_pid($iface) . ".\n";
    return false;
}

// A wildcard SOCKS listener conflicts with any specific listener on the same port.
function xray_socks_conflict(string $listenA, int $portA, string $listenB, int $portB): bool
{
    if ($portA !== $portB) return false;
    return $listenA === $listenB ||
        $listenA === '0.0.0.0' || $listenB === '0.0.0.0' ||
        $listenA === '::' || $listenB === '::';
}

// ─── PID helpers (FreeBSD: no posix extension — use /bin/kill) ───────────────
function proc_matches_instance(string $pidfile, int $pid): ?bool
{
    if (!preg_match('/^(xray_core|tun2socks)_([0-9a-fA-F-]{36})\.pid$/D',basename($pidfile),$m)) return false;
    $uuid=$m[2];
    if (!xray_valid_instance_uuid($uuid)) return false;
    $bin=$m[1] === 'xray_core' ? XRAY_BIN : T2S_BIN;
    $conf=$m[1] === 'xray_core' ? xray_conf_path($uuid) : t2s_conf_path($uuid);
    $command=trim((string)shell_exec('/bin/ps -ww -o command= -p '.$pid.' 2>/dev/null'));
    // Missing ps output is uncertainty, not proof of an unrelated/dead process.
    if ($command === '') return null;
    return strpos($command,$bin) !== false && strpos($command,$conf) !== false;
}

function proc_is_running(string $pidfile): bool
{
    if (!file_exists($pidfile)) {
        return false;
    }
    $pid = (int)trim(file_get_contents($pidfile));
    if ($pid <= 0) {
        return false;
    }
    exec('/bin/kill -0 ' . $pid . ' 2>/dev/null', $out, $rc);
    return $rc === 0 && proc_matches_instance($pidfile,$pid);
}

function proc_kill(string $pidfile): bool
{
    if (!file_exists($pidfile)) return true;
    $pid = (int)trim(file_get_contents($pidfile));
    if ($pid <= 0) {
        @unlink($pidfile);
        return true;
    }
    exec('/bin/kill -0 ' . $pid . ' 2>/dev/null', $probe, $alive);
    if ($alive !== 0) {
        @unlink($pidfile);
        return true;
    }
    $matches = proc_matches_instance($pidfile, $pid);
    if ($matches === null) {
        echo "ERROR: Cannot confirm process identity for PID {$pid}; no signal sent.\n";
        return false;
    }
    if (!$matches) {
        // PID reuse: leave the unrelated process untouched, forget the stale file.
        echo "WARNING: stale PID file {$pidfile} points to an unrelated process.\n";
        @unlink($pidfile);
        return true;
    }
    exec('/bin/kill -TERM ' . $pid . ' 2>/dev/null');
    for ($i = 0; $i < 30; $i++) {
        usleep(100000);
        exec('/bin/kill -0 ' . $pid . ' 2>/dev/null', $out, $rc);
        if ($rc !== 0) break;
    }
    if ($rc === 0) {
        // Narrow the PID-reuse window before escalation; numeric PIDs cannot
        // provide an atomic identity-and-signal guarantee.
        $matches = proc_matches_instance($pidfile, $pid);
        if ($matches === null) {
            echo "ERROR: Cannot reconfirm process identity for PID {$pid}; no KILL sent.\n";
            return false;
        }
        if (!$matches) {
            @unlink($pidfile);
            return true;
        }
        exec('/bin/kill -KILL ' . $pid . ' 2>/dev/null');
        for ($i = 0; $i < 20; $i++) {
            usleep(100000);
            exec('/bin/kill -0 ' . $pid . ' 2>/dev/null', $out2, $rc);
            if ($rc !== 0) break;
        }
    }
    if ($rc === 0) {
        echo "ERROR: PID {$pid} still exists; refusing to start replacement.\n";
        return false;
    }
    @unlink($pidfile);
    return true;
}

function proc_start(string $bin, string $args, string $pidfile, string $logfile = ''): bool
{
    // daemon(8) detaches itself; do not add an untracked background shell.
    $log = escapeshellarg($logfile !== '' ? $logfile : XRAY_DAEMON_LOG);
    exec('/usr/sbin/daemon -p ' . escapeshellarg($pidfile)
       . ' ' . escapeshellarg($bin) . ' ' . $args . ' >> ' . $log . ' 2>&1', $out, $rc);
    return $rc === 0;
}

// ─── BUG-3 FIX: config validation before start ──────────────────────────────
function xray_validate_config(string $confFile): bool
{
    if (!is_executable(XRAY_BIN)) {
        echo "ERROR: xray-core is unavailable; candidate was not validated.\n";
        return false;
    }
    if (!file_exists($confFile)) {
        echo "ERROR: config file not found after write: {$confFile}\n";
        return false;
    }
    exec(escapeshellarg(XRAY_BIN) . ' run -test -c ' . escapeshellarg($confFile) . ' -format=json 2>&1', $out, $rc);
    if ($rc !== 0) {
        echo "ERROR: xray config validation failed:\n" . implode("\n", $out) . "\n";
        return false;
    }
    return true;
}

// ─── lo0 alias management ─────────────────────────────────────────────────────
function lo0_needs_alias(string $addr): bool
{
    if ($addr === '127.0.0.1' || $addr === '0.0.0.0') {
        return false;
    }
    $parts = explode('.', $addr);
    return count($parts) === 4 && $parts[0] === '127';
}

function lo0_alias_ensure(string $addr): void
{
    if (!lo0_needs_alias($addr)) {
        return;
    }
    exec('/sbin/ifconfig lo0 2>/dev/null', $out, $rc);
    if ($rc !== 0) {
        echo "WARNING: Cannot read lo0 interface\n";
        return;
    }
    $ifOutput = implode("\n", $out);
    if (strpos($ifOutput, $addr) !== false) {
        return;
    }
    exec('/sbin/ifconfig lo0 alias ' . escapeshellarg($addr) . ' 2>/dev/null', $out2, $rc2);
    if ($rc2 !== 0) {
        echo "WARNING: Failed to add lo0 alias {$addr}\n";
    } else {
        echo "INFO: Added lo0 alias {$addr}\n";
    }
}

function lo0_alias_remove(string $addr): void
{
    if (!lo0_needs_alias($addr)) {
        return;
    }
    exec('/sbin/ifconfig lo0 -alias ' . escapeshellarg($addr) . ' 2>/dev/null', $out, $rc);
    if ($rc === 0) {
        echo "INFO: Removed lo0 alias {$addr}\n";
    }
}

// ─── High-level per-instance actions ─────────────────────────────────────────

/**
 * do_stop() — останавливает tun2socks и xray-core инстанса, выставляет stopped flag.
 */
function do_stop(string $inst_uuid, ?string $tunIface = null, bool $administrative = true): bool
{
    $beforeXray = proc_is_running(xray_pid_path($inst_uuid));
    $beforeT2s = proc_is_running(t2s_pid_path($inst_uuid));
    try {
        if ($administrative && !xray_atomic_write(xray_stopped_flag($inst_uuid), date('c'))) return false;
        if ($tunIface === '') {
            // Corrupt/missing files: PID command identity remains independent of file contents.
            $ifaces = xray_owned_tuns($inst_uuid);
            @unlink(xray_applied_hash_path($inst_uuid));
            if (!proc_kill(t2s_pid_path($inst_uuid))) return false;
            if (!proc_kill(xray_pid_path($inst_uuid))) return false;
            if ($ifaces === null) {
                echo "ERROR: Cannot confirm TUN ownership after Stop for {$inst_uuid}\n";
                return false;
            }
            foreach ($ifaces as $iface) {
                if (!tun_wait_unowned($iface)) return false;
            }
            echo "Stopped identified processes for {$inst_uuid}.\n";
            return true;
        }
        if ($tunIface === null) {
            $c        = xray_get_config($inst_uuid);
            $tunIface = $c['tun_iface'] ?? 'proxytun2socks0';
        }

        // Never explicitly destroy an OPNsense-assigned TUN here.  tun2socks owns
        // its FreeBSD NativeTun handle; destroying the interface while that handle
        // remains open can block forever inside kernel tun_destroy (FreeBSD 15.1).
        // A disabled profile sharing this TUN must never stop its active owner.
        if (!proc_is_running(t2s_pid_path($inst_uuid))
            && !proc_is_running(xray_pid_path($inst_uuid))) {
            // An unreadable identity must not be mistaken for an absent process.
            foreach ([t2s_pid_path($inst_uuid), xray_pid_path($inst_uuid)] as $pidfile) {
                if (is_file($pidfile) && !proc_kill($pidfile)) return false;
            }
            // A missing PID file is not proof that this instance released NativeTun.
            // Do not silently mark it stopped while its real process owns the TUN.
            if (tun_owned_by_instance($tunIface, $inst_uuid)) {
                echo "ERROR: Instance {$inst_uuid} still owns TUN {$tunIface} without a usable PID file.\n";
                return false;
            }
            @unlink(xray_applied_hash_path($inst_uuid));

            echo "Already stopped.\n";
            return true;
        }
        $ownerBefore = tun_owner_pid($tunIface);
        if ($ownerBefore > 0 && !tun_owned_by_instance($tunIface, $inst_uuid)) {
            echo "ERROR: TUN {$tunIface} belongs to a different instance (PID {$ownerBefore}).\n";
            return false;
        }
        @unlink(xray_applied_hash_path($inst_uuid));
        if (!proc_kill(t2s_pid_path($inst_uuid))) return false;
        // Missing/stale PID files are not evidence that NativeTun was released.
        // Never terminate an unrelated TUN owner; abort safely instead.
        if ($ownerBefore > 0 && !tun_wait_unowned($tunIface, $ownerBefore)) return false;

        // Останавливаем xray-core
        if (!proc_kill(xray_pid_path($inst_uuid))) return false;

        // Keep shared aliases when stopping one instance.
        // Loopback aliases may be shared by independent instances; keep them.

        // Only administrative Stop sets the flag; emergency cleanup preserves intent.
        @unlink(xray_applied_hash_path($inst_uuid));


        echo "Stopped.\n";
        return true;
    } finally {
        if ($beforeXray !== proc_is_running(xray_pid_path($inst_uuid)) ||
            $beforeT2s !== proc_is_running(t2s_pid_path($inst_uuid))) {
            $GLOBALS['xray_runtime_changed'] = true;
        }
    }
}


function do_status(string $inst_uuid = ''): void
{
    if ($inst_uuid !== '') {
        $xray = proc_is_running(xray_pid_path($inst_uuid));
        $t2s  = proc_is_running(t2s_pid_path($inst_uuid));
        echo json_encode([
            'status'      => ($xray && $t2s) ? 'ok' : 'stopped',
            'xray_core'   => $xray ? 'running' : 'stopped',
            'tun2socks'   => $t2s  ? 'running' : 'stopped',
            'inst_uuid'   => $inst_uuid,
            'network_state' => is_file(xray_applied_hash_path($inst_uuid)) ? 'applied' : 'unconfirmed',
        ]) . "\n";
        return;
    }

    // Без UUID: статус всех инстансов + агрегированный статус
    $all = xray_get_all_instances();
    if (empty($all)) {
        echo json_encode(['status' => 'stopped', 'xray_core' => 'stopped', 'tun2socks' => 'stopped']) . "\n";
        return;
    }
    // Для совместимости с текущим GUI: возвращаем статус первого инстанса
    $first = reset($all);
    $uuid0 = $first['inst_uuid'];
    $xray  = proc_is_running(xray_pid_path($uuid0));
    $t2s   = proc_is_running(t2s_pid_path($uuid0));
    echo json_encode([
        'status'    => ($xray && $t2s) ? 'ok' : 'stopped',
        'xray_core' => $xray ? 'running' : 'stopped',
        'tun2socks' => $t2s  ? 'running' : 'stopped',
        'network_state' => is_file(xray_applied_hash_path($uuid0)) ? 'applied' : 'unconfirmed',
    ]) . "\n";
}

function do_status_all(): void
{
    $all    = xray_get_all_instances();
    $result = [];
    foreach ($all as $inst_uuid => $c) {
        $xray = proc_is_running(xray_pid_path($inst_uuid));
        $t2s  = proc_is_running(t2s_pid_path($inst_uuid));
        $result[$inst_uuid] = [
            'name'      => $c['name'],
            'status'    => ($xray && $t2s) ? 'ok' : 'stopped',
            'xray_core' => $xray ? 'running' : 'stopped',
            'tun2socks' => $t2s  ? 'running' : 'stopped',
            'network_state' => is_file(xray_applied_hash_path($inst_uuid)) ? 'applied' : 'unconfirmed',
        ];
    }
    echo json_encode($result) . "\n";
}

// A bounded, secret-free summary shared by the boot syshook and plugin hook.
// Replace the previous event; never persist raw validator/controller output.
function xray_boot_log(string $state): void
{
    $entry = gmdate('[Y-m-d H:i:s UTC]') . " Xray boot: {$state}\n";
    if (!xray_atomic_write('/tmp/xray_syshook.log', $entry)) {
        echo "WARNING: Cannot update Xray Boot log\n";
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────
$action    = $argv[1] ?? 'status';
$inst_uuid = isset($argv[2]) ? trim($argv[2]) : '';

// configd uses a literal placeholder when no UUID argument is supplied.
if (in_array($inst_uuid, ['%1', '%s'], true)) $inst_uuid = '';
if ($inst_uuid !== '' && !xray_valid_instance_uuid($inst_uuid)) {
    echo "ERROR: Invalid instance UUID\n";
    exit(1);
}

// Serialize all service mutations across profiles sharing a TUN.
if (in_array($action, ['start', 'stop', 'restart', 'reconfigure', 'boot', 'watchdog'], true)) {
    $globalLock = fopen('/var/run/xray_service_operation.lock', 'ce');
    if ($globalLock === false || !flock($globalLock, LOCK_EX | LOCK_NB)) {
        // Atomic log replacement takes no operation lock. Concurrent boot writers
        // publish complete records; the last publication remains visible.
        if ($action === 'boot') xray_boot_log('failed; operation lock unavailable');
        echo "ERROR: Another Xray service operation is in progress.\n";
        exit(1);
    }
}

switch ($action) {
    case 'start':
    case 'stop':
    case 'restart':
    case 'reconfigure':
    case 'boot':
    case 'watchdog':
        if ($action === 'boot') xray_boot_log('started');
        try {
            $ok = xray_apply_action($action, $inst_uuid);
        } catch (Throwable $e) {
            echo "ERROR: " . $e->getMessage() . "\n";
            $ok = false;
        }
        // Successful independent changes and rollback also need a reload when
        // another instance failed. Never wait for configd while holding its lock.
        if (!empty($GLOBALS['xray_runtime_changed'])) {
            exec('/bin/sh /usr/local/etc/rc.syshook.d/start/50-xray --reload-only >/dev/null 2>&1 &');
        }
        if ($action === 'boot') xray_boot_log($ok ? 'completed' : 'failed; inspect controller output and per-instance logs');
        echo $ok ? "OK\n" : "ERROR: One or more Xray operations failed; inspect preceding diagnostics.\n";
        exit($ok ? 0 : 1);

    case 'status':
        do_status($inst_uuid);
        break;

    case 'statusall':
        do_status_all();
        break;

    case 'validate':
        $c = xray_get_config($inst_uuid);
        $candidate = $c ? xray_prepare_candidate($c) : null;
        if ($candidate === null) {
            echo "ERROR: No valid candidate configuration\n";
            exit(1);
        }
        echo "OK: config is valid\n";
        exit(0);

    case 'version':
        $ver = file_exists(XRAY_VERSION_FILE) ? trim(file_get_contents(XRAY_VERSION_FILE)) : 'unknown';
        echo json_encode(['version' => $ver]) . "\n";
        break;

    default:
        echo "Unknown action: $action\n";
        exit(1);
}
