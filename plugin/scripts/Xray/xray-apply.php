<?php
/* Safe legacy configuration application. No persistent transaction state. */

function xray_atomic_write(string $path, string $bytes): bool
{
    $dir = dirname($path);
    if (is_link($path) || (!is_dir($dir) && !@mkdir($dir, 0750, true) && !is_dir($dir))) return false;
    $tmp = @tempnam($dir, '.xray-');
    if ($tmp === false) return false;
    try {
        // tempnam may silently fall back to /tmp: never allow cross-filesystem
        // rename/copy semantics to replace a working file.
        if (realpath(dirname($tmp)) !== realpath($dir) || !@chmod($tmp, 0600)) return false;
        $fd = @fopen($tmp, 'wb');
        if ($fd === false) return false;
        try {
            if (fwrite($fd, $bytes) !== strlen($bytes) || !fflush($fd) || !fsync($fd)) return false;
        } finally {
            fclose($fd);
        }
        return @rename($tmp, $path);
    } finally {
        if (is_file($tmp)) @unlink($tmp);
    }
}

function xray_prepare_candidate(array $c): ?array
{
    $tmp = false;
    try {
        $json = xray_normalize_transport(json_encode(xray_build_config($c),
            JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));
        $tmp = tempnam(sys_get_temp_dir(), 'xray-candidate-');
        if ($tmp === false || !chmod($tmp, 0600) || file_put_contents($tmp, $json) !== strlen($json)) {
            throw new RuntimeException('Cannot write private candidate');
        }
        if (!xray_validate_config($tmp)) return null;
        return ['json' => $json, 'yaml' => xray_build_t2s_config($c)];
    } catch (Throwable $e) {
        echo 'ERROR: ' . $e->getMessage() . "\n";
        return null;
    } finally {
        if ($tmp !== false) @unlink($tmp);
    }
}

function xray_network(array $c): ?array
{
    $cfg = OPNsense\Core\Config::getInstance()->object();
    foreach (($cfg->interfaces ?? new SimpleXMLElement('<interfaces/>'))->children() as $iface) {
        if ((string)$iface->if !== $c['tun_iface']) continue;
        $ip = (string)$iface->ipaddr;
        $prefix = (string)$iface->subnet;
        if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_IPV4) && preg_match('/^[0-9]+$/D', $prefix) && (int)$prefix <= 32) {
            return ['ip' => $ip, 'prefix' => (int)$prefix];
        }
        throw new RuntimeException('Invalid static IPv4 assignment for TUN ' . $c['tun_iface']);
    }
    return null; // NativeTun may need to be created before OPNsense can assign it.
}

function xray_setup_network(array $c, array $network): bool
{
    exec('/sbin/ifconfig ' . escapeshellarg($c['tun_iface']) . ' mtu ' . (int)$c['mtu'] . ' up 2>&1', $out, $rc);
    if ($rc !== 0) return false;
    $GLOBALS['xray_runtime_changed'] = true;
    exec('/sbin/ifconfig ' . escapeshellarg($c['tun_iface']) . ' inet ' .
        escapeshellarg($network['ip'] . '/' . $network['prefix']) . ' 2>&1', $out, $rc);
    return $rc === 0;
}

function xray_pair_running(string $id): bool
{
    return proc_is_running(xray_pid_path($id)) && proc_is_running(t2s_pid_path($id));
}

function xray_any_running(string $id): bool
{
    return proc_is_running(xray_pid_path($id)) || proc_is_running(t2s_pid_path($id));
}

function xray_healthy(array $c): bool
{
    return xray_pair_running($c['inst_uuid']) && tun_owned_by_instance($c['tun_iface'], $c['inst_uuid']);
}

// Read only the legacy-generated runtime fields needed for Stop and rollback.
// Formatting/quoting differences in YAML do not require adoption or migration.
function xray_runtime_config(string $id): ?array
{
    $jp = xray_conf_path($id); $yp = t2s_conf_path($id);
    if (!is_file($jp) && !is_file($yp)) return null;
    $json = @file_get_contents($jp); $yaml = @file_get_contents($yp);
    if ($json === false || $yaml === false) throw new RuntimeException("Incomplete runtime files for {$id}");
    $decoded = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
    $inbound = $decoded['inbounds'][0] ?? [];
    $values = [];
    foreach (explode("\n", $yaml) as $line) {
        if (!preg_match('/^\s*(device|mtu|proxy)\s*:\s*(.*?)\s*$/', $line, $m)) continue;
        $value = $m[2];
        if (str_starts_with($value, '"')) $value = json_decode($value, true, 512, JSON_THROW_ON_ERROR);
        elseif (str_starts_with($value, "'")) $value = str_replace("''", "'", substr($value, 1, -1));
        else $value = preg_replace('/\s+#.*$/', '', $value);
        $values[$m[1]] = $value;
    }
    if (($inbound['protocol'] ?? '') !== 'socks' || !isset($inbound['listen'], $inbound['port']) ||
        !isset($values['device'], $values['mtu'], $values['proxy']) ||
        $values['proxy'] !== 'socks5://' . $inbound['listen'] . ':' . $inbound['port'] || !preg_match('/^[a-z][a-z0-9]{0,13}[0-9]$/D', (string)$values['device'])) {
        throw new RuntimeException("Unrecognized legacy runtime for {$id}; preserve files and inspect manually");
    }
    return ['inst_uuid' => $id, 'tun_iface' => $values['device'], 'mtu' => (int)$values['mtu'],
        'socks5_listen' => $inbound['listen'], 'socks5_port' => (int)$inbound['port']];
}

function xray_backup_path(string $id): string
{
    return XRAY_CONF_DIR . '/backup-' . $id . '.json';
}

function xray_save_backup(string $id, ?array $runtime): ?array
{
    $path = xray_backup_path($id);
    // Never overwrite a retained known-good backup with a failed/partial pair.
    if (is_file($path) && ($runtime === null || !xray_healthy($runtime))) {
        $backup = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
        if (($backup['runtime']['inst_uuid'] ?? '') !== $id || !isset($backup['json'], $backup['yaml'], $backup['runtime'])) {
            throw new RuntimeException("Invalid backup {$path}; inspect manually");
        }
        return $backup;
    }
    if ($runtime === null) return null;
    // A removed interface assignment must not prohibit applying a new one.
    // Its files remain recoverable, but automatic network rollback may fail.
    try { $network = xray_network($runtime); }
    catch (Throwable $e) { $network = null; }
    $backup = ['runtime' => $runtime, 'network' => $network,
        'json' => file_get_contents(xray_conf_path($id)), 'yaml' => file_get_contents(t2s_conf_path($id)),
        'hash' => is_file(xray_applied_hash_path($id)) ? trim(file_get_contents(xray_applied_hash_path($id))) : null];
    if ($backup['json'] === false || $backup['yaml'] === false ||
        !xray_atomic_write($path, json_encode($backup, JSON_THROW_ON_ERROR))) {
        throw new RuntimeException("Cannot save backup {$path}; runtime untouched");
    }
    return $backup;
}

function xray_install_files(string $id, array $files): bool
{
    return xray_atomic_write(xray_conf_path($id), $files['json']) &&
        xray_atomic_write(t2s_conf_path($id), $files['yaml']);
}

function xray_socks_ready(array $c): bool
{
    $listen = $c['socks5_listen'];
    if ($listen === '0.0.0.0') $listen = '127.0.0.1';
    if ($listen === '::') $listen = '::1';
    if (strpos($listen, ':') !== false) $listen = '[' . $listen . ']';
    $socket = @fsockopen($listen, (int)$c['socks5_port'], $errno, $error, 0.1);
    if ($socket === false) return false;
    fclose($socket);
    return true;
}

function xray_launch(array $c, ?array $network, ?string $hash): bool
{
    $id = $c['inst_uuid']; $log = xray_instance_log($id);
    $wasXray = proc_is_running(xray_pid_path($id));
    $wasT2s = proc_is_running(t2s_pid_path($id));
    try {
        lo0_alias_ensure($c['socks5_listen']);
        if (!proc_is_running(xray_pid_path($id)) &&
            !proc_start(XRAY_BIN, 'run -c ' . escapeshellarg(xray_conf_path($id)), xray_pid_path($id), $log)) return false;
        if (!$wasXray && proc_is_running(xray_pid_path($id))) $GLOBALS['xray_runtime_changed'] = true;
        $ready = false;
        for ($i = 0; $i < 30; $i++) {
            if (proc_is_running(xray_pid_path($id)) && xray_socks_ready($c)) { $ready = true; break; }
            usleep(100000);
        }
        if (!$ready) return false;
        if (!proc_is_running(t2s_pid_path($id)) &&
            !proc_start(T2S_BIN, '--config ' . escapeshellarg(t2s_conf_path($id)), t2s_pid_path($id), $log)) return false;
        if (!$wasT2s && proc_is_running(t2s_pid_path($id))) $GLOBALS['xray_runtime_changed'] = true;
        for ($i = 0; $i < 30; $i++) {
            if (xray_healthy($c) && xray_socks_ready($c)) {
                if ($network === null) {
                    @unlink(xray_applied_hash_path($id));
                    echo "WARNING: Processes running for {$id}; network setup pending. Assign {$c['tun_iface']} a static IPv4 address in OPNsense, then Apply.\n";
                    return true;
                }
                if (!xray_setup_network($c, $network) || !xray_healthy($c)) return false;
                $GLOBALS['xray_runtime_changed'] = true;
                if ($hash !== null && !xray_atomic_write(xray_applied_hash_path($id), $hash)) return false;
                echo "Started {$id}.\n";
                return true;
            }
            usleep(100000);
        }
        return false;
    } finally {
        if ($wasXray !== proc_is_running(xray_pid_path($id)) ||
            $wasT2s !== proc_is_running(t2s_pid_path($id))) $GLOBALS['xray_runtime_changed'] = true;
    }
}

function xray_resources_conflict(array $a, array $b): bool
{
    return $a['tun_iface'] === $b['tun_iface'] || xray_socks_conflict(
        $a['socks5_listen'], (int)$a['socks5_port'], $b['socks5_listen'], (int)$b['socks5_port']);
}

function xray_runtime_ids(): array
{
    $ids = [];
    foreach (array_merge(glob('/var/run/xray_core_*.pid') ?: [], glob('/var/run/tun2socks_*.pid') ?: [],
        glob(XRAY_CONF_DIR . '/config-*.json') ?: [], glob(T2S_CONF_DIR . '/config-*.yaml') ?: []) as $path) {
        if (preg_match('/[_-]([0-9a-fA-F-]{36})\.(pid|json|yaml)$/D', $path, $m) && xray_valid_instance_uuid($m[1])) {
            $ids[$m[1]] = $m[1];
        }
    }
    return array_values($ids);
}

function xray_check_resources(array $all, array $targets, array $releasing = []): void
{
    foreach (xray_runtime_ids() as $id) {
        // A deleted XML instance can still own a live SOCKS listener or TUN.
        if (!isset($all[$id])) $all[$id] = ['enabled' => false];
    }
    foreach ($targets as $id => $c) {
        foreach ($all as $otherId => $other) {
            if ($otherId === $id) continue;
            if ($other['enabled'] && xray_resources_conflict($c, $other)) {
                throw new RuntimeException("SOCKS/TUN settings conflict: {$id}, {$otherId}");
            }
            if (xray_any_running($otherId) && !isset($releasing[$otherId])) {
                $runtime = xray_runtime_config($otherId);
                if ($runtime === null || xray_resources_conflict($c, $runtime)) {
                    throw new RuntimeException("SOCKS/TUN still used by {$otherId}; stop it explicitly before transferring resources");
                }
            }
        }
        $owner = tun_owner_pid($c['tun_iface']);
        if ($owner < 0) throw new RuntimeException('Invalid TUN name');
        if ($owner > 0 && !tun_owned_by_instance($c['tun_iface'], $id)) {
            $released = false;
            foreach ($releasing as $otherId => $_) {
                if (tun_owned_by_instance($c['tun_iface'], $otherId)) $released = true;
            }
            if (!$released) throw new RuntimeException("TUN {$c['tun_iface']} has another owner");
        }
    }
}

function xray_apply_one(array $c, array $files, ?array $network, bool $force): bool
{
    $id = $c['inst_uuid'];
    try { $runtime = xray_runtime_config($id); }
    catch (Throwable $e) {
        if (xray_any_running($id)) throw $e;
        // An interrupted/failed first write may leave only one file. There is
        // no running pair to preserve; keep any retained backup and allow retry.
        echo "WARNING: Incomplete stopped runtime for {$id}; retrying validated candidate.\n";
        $runtime = null;
    }
    if (!$force && xray_healthy($c) &&
        @file_get_contents(xray_conf_path($id)) === $files['json'] &&
        @file_get_contents(t2s_conf_path($id)) === $files['yaml']) {
        // Also accepts an unchanged working legacy instance without restarting it.
        if (is_file(xray_stopped_flag($id)) && !unlink(xray_stopped_flag($id))) return false;
        if ($network === null || !is_file(xray_applied_hash_path($id))) {
            // Finish initial network setup without restarting the existing pair.
            return xray_launch($c, $network, xray_instance_hash($c));
        }
        return true;
    }
    $backup = xray_save_backup($id, $runtime);
    $old = $runtime ?? ($backup['runtime'] ?? $c);
    // Explicit Start/Apply is an instruction to run, even if recovery fails.
    // Automatic paths reach here only when there is no administrative flag.
    if (is_file(xray_stopped_flag($id)) && !unlink(xray_stopped_flag($id))) return false;
    try {
        if (!do_stop($id, $old['tun_iface'], false)) {
            // A partial stop may have removed one component. Files are unchanged;
            // repair just the missing component, without killing the survivor.
            if ($runtime !== null && xray_any_running($id)) {
                try {
                    $oldHash = $backup['hash'] ?? null;
                    if (!xray_launch($runtime, xray_network($runtime), $oldHash)) {
                        @unlink(xray_applied_hash_path($id));
                        echo "ERROR: Partial-stop repair failed for {$id}\n";
                    }
                } catch (Throwable $e) {
                    echo 'ERROR: Partial-stop repair failed: ' . $e->getMessage() . "\n";
                }
            }
            echo "ERROR: Stop failed for {$id}; candidate was not installed\n";
            return false;
        }
        if (!xray_install_files($id, $files) || !xray_launch($c, $network, xray_instance_hash($c))) {
            throw new RuntimeException("Install/start failed for {$id}");
        }
        return true;
    } catch (Throwable $e) {
        echo 'ERROR: ' . $e->getMessage() . "\n";
        @unlink(xray_applied_hash_path($id));
        if (!do_stop($id, $c['tun_iface'], false)) {
            echo "ERROR: Cleanup unconfirmed; runtime files and backup retained for {$id}\n";
            return false;
        }
        if ($backup !== null) {
            try {
                $restored = xray_install_files($id, $backup);
                if ($restored) {
                    $restored = xray_launch($backup['runtime'], $backup['network'], $backup['hash']);
                } else $restored = false;
            } catch (Throwable $e) {
                echo 'ERROR: Rollback: ' . $e->getMessage() . "\n";
                $restored = false;
            }
            if (!$restored) {
                @unlink(xray_applied_hash_path($id));
                do_stop($id, $backup['runtime']['tun_iface'], false);
            }
            echo ($restored ? 'WARNING: Previous runtime restored; Apply failed. ' : 'ERROR: Rollback incomplete. ') .
                'Backup retained: ' . xray_backup_path($id) . "\n";
        }
        return false;
    }
}

function xray_stop_instance(string $id): bool
{
    if (!xray_atomic_write(xray_stopped_flag($id), date('c'))) {
        echo "ERROR: Cannot record administrative Stop for {$id}\n";
        return false;
    }
    try { $runtime = xray_runtime_config($id); }
    catch (Throwable $e) {
        echo "WARNING: Runtime unreadable for {$id}; stopping only identified processes.\n";
        $runtime = null;
    }
    return do_stop($id, $runtime['tun_iface'] ?? '', false);
}

function xray_recover_runtime(string $id, bool $boot = false): bool
{
    $runtime = xray_runtime_config($id);
    if ($runtime === null) throw new RuntimeException("No applied runtime for {$id}; use explicit Start/Apply");
    if (xray_healthy($runtime)) return true;
    $hashFile = xray_applied_hash_path($id);
    $hash = is_file($hashFile) ? trim(file_get_contents($hashFile)) : null;
    // A failed candidate can leave valid-looking files. Without evidence of a
    // completed Apply, watchdog must not promote them or read a different XML config.
    if (!$boot && ($hash === null || !preg_match('/^[a-f0-9]{64}$/D', $hash))) {
        throw new RuntimeException("Applied runtime is not confirmed for {$id}; use explicit Start/Apply");
    }
    // Recovery must earn a new network receipt. Invalidate before any recovery
    // work, so a failed setup cannot make a later Start/Apply skip the network.
    if ((file_exists($hashFile) || is_link($hashFile)) && !@unlink($hashFile)) {
        throw new RuntimeException("Cannot invalidate applied hash for {$id}; recovery aborted");
    }
    xray_check_resources([], [$id => $runtime]);
    if (!is_executable(T2S_BIN) || !xray_validate_config(xray_conf_path($id))) return false;
    $network = xray_network($runtime);
    if (!$boot && $network === null) throw new RuntimeException("Applied TUN assignment missing for {$id}");
    if ($boot && $hash === null && $network !== null) {
        // /var/run is cleared at reboot. Record successful runtime recovery,
        // without claiming that the saved (possibly edited) XML was applied.
        $hash = hash('sha256', file_get_contents(xray_conf_path($id)) .
            file_get_contents(t2s_conf_path($id)));
    }
    if (!xray_launch($runtime, $network, $hash)) {
        echo "ERROR: Could not restore applied runtime for {$id}; saved XML was not applied\n";
        return false;
    }
    return true;
}

function xray_watchdog_enabled(): bool
{
    $cfg = OPNsense\Core\Config::getInstance()->object();
    return (string)($cfg->OPNsense->xray->general->watchdog_enabled ?? '0') === '1';
}

function xray_apply_action(string $action, string $uuid = ''): bool
{
    $all = xray_get_all_instances();
    if ($uuid !== '' && !isset($all[$uuid])) {
        if ($action !== 'stop') throw new RuntimeException('Unknown instance UUID');
        $all[$uuid] = ['inst_uuid' => $uuid, 'tun_iface' => 'proxytun2socks0'];
    }
    $selected = $uuid === '' ? $all : [$uuid => $all[$uuid]];
    $auto = in_array($action, ['boot', 'watchdog'], true);
    if ($action === 'watchdog' && !xray_watchdog_enabled()) return true;
    $ok = true;
    if ($action === 'stop') {
        // Include runtime PID files for deleted XML instances (including legacy).
        if ($uuid === '') {
            foreach (xray_runtime_ids() as $id) {
                $selected[$id] = $selected[$id] ?? ['inst_uuid' => $id, 'tun_iface' => 'proxytun2socks0'];
            }
        }
        foreach ($selected as $id => $c) {
            try {
                if (!xray_stop_instance($id)) $ok = false;
            } catch (Throwable $e) { echo 'ERROR: ' . $e->getMessage() . "\n"; $ok = false; }
        }
        return $ok;
    }
    $targets = []; $releasing = []; $prepared = [];
    foreach ($selected as $id => $c) {
        if (!$c['enabled']) {
            if (!$auto && $action !== 'start') $releasing[$id] = $c;
            continue;
        }
        if ($auto) {
            if (is_file(xray_stopped_flag($id))) continue;
            // Boot may initialize a new enabled instance; watchdog never applies XML.
            if ($action === 'watchdog' || is_file(xray_conf_path($id)) || is_file(t2s_conf_path($id))) {
                try {
                    if (!xray_recover_runtime($id, $action === 'boot')) $ok = false;
                } catch (Throwable $e) { echo 'ERROR: ' . $e->getMessage() . "\n"; $ok = false; }
                continue;
            }
        }
        $targets[$id] = $c;
    }
    if ($action === 'reconfigure' && $uuid === '') {
        // Delete saves XML; general Apply retires its runtime after preflight.
        foreach (xray_runtime_ids() as $id) {
            if (!isset($all[$id])) $releasing[$id] = ['inst_uuid' => $id];
        }
    }
    // Manual batches: EVERY candidate/resource checked before the first stop.
    // Automatic recovery is independent per instance: one invalid profile must
    // not prevent the watchdog from repairing another.
    foreach ($targets as $id => $c) {
        try {
            xray_check_resources($all, $auto ? [$id => $c] : $targets, $releasing);
            if (!is_executable(T2S_BIN)) throw new RuntimeException('tun2socks is unavailable');
            $network = xray_network($c);
            $candidate = xray_prepare_candidate($c);
            if ($candidate === null) throw new RuntimeException("Invalid candidate for {$id}");
            $prepared[$id] = [$candidate, $network];
        } catch (Throwable $e) {
            echo 'ERROR: ' . $e->getMessage() . "\n";
            if (!$auto) return false;
            $ok = false;
        }
    }
    // Disabled profiles may intentionally hand their TUN to an enabled profile.
    foreach ($releasing as $id => $c) {
        try {
            if (!xray_stop_instance($id)) $ok = false;
        } catch (Throwable $e) { echo 'ERROR: ' . $e->getMessage() . "\n"; $ok = false; }
    }
    foreach ($prepared as $id => [$files, $network]) {
        try {
            // Recheck actual ownership after disabled-profile stops or rollback.
            xray_check_resources($all, [$id => $targets[$id]]);
            if (!xray_apply_one($targets[$id], $files, $network, $action === 'restart')) $ok = false;
        } catch (Throwable $e) { echo 'ERROR: ' . $e->getMessage() . "\n"; $ok = false; }
    }
    return $ok;
}
