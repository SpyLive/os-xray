<?php

function xray_valid_instance_uuid_boot(string $uuid): bool
{
    return (bool)preg_match(
        '/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/D',
        $uuid
    );
}

function xray_enabled(): bool
{
    $cfg = OPNsense\Core\Config::getInstance()->object();
    return isset($cfg->OPNsense->xray->general->enabled)
        && (string)$cfg->OPNsense->xray->general->enabled === '1';
}

function xray_configure(): array
{
    return ['bootup' => ['xray_configure_do:10']];
}

/** Boot uses exactly the validated CLI/watchdog start path. */
function xray_configure_do(bool $verbose = false): void
{
    $ctrl='/usr/local/opnsense/scripts/Xray/xray-service-control.php';
    exec('/usr/local/bin/php '.escapeshellarg($ctrl).' boot 2>&1',$out,$rc);
    if ($verbose) echo implode("\n",$out)."\n";
    if ($rc !== 0) error_log('Xray boot lifecycle failed: '.implode(' ',$out));
}

/**
 * v3.0.0: регистрирует один сервис на каждый инстанс.
 */
function xray_services()
{
    $services  = [];
    $cfg       = OPNsense\Core\Config::getInstance()->object();
    $instances = $cfg->OPNsense->xray->instances ?? null;

    if ($instances) {
        foreach ($instances->instance as $inst) {
            $inst_uuid = (string)$inst['uuid'];
            if (!xray_valid_instance_uuid_boot($inst_uuid)
                || (string)($inst->enabled ?? '1') !== '1') {
                continue;
            }
            $name       = (string)($inst->name ?? 'default');
            $services[] = [
                'description' => 'Xray (' . $name . ')',
                'configd'     => [
                    'restart' => ['xray restart ' . $inst_uuid],
                    'start'   => ['xray start '   . $inst_uuid],
                    'stop'    => ['xray stop '    . $inst_uuid],
                ],
                'name'    => 'xray',
                'pidfile' => "/var/run/xray_core_{$inst_uuid}.pid",
            ];
        }
    }

    return $services;
}

/**
 * E1: регистрирует cron-задание для watchdog.
 */
function xray_cron(): array
{
    // OPNsense plugins_cron() expects each entry to contain an 'autocron'
    // tuple: [shell command, minute, hour, day, month, weekday].
    // A bare positional tuple is ignored by system_cron_configure().
    return [
        ['autocron' => ['/usr/local/sbin/configctl -d xray watchdog', '*']],
    ];
}

function xray_cron_watchdog(): void
{
    (new OPNsense\Core\Backend())->configdRun('xray watchdog');
}

function xray_xmlrpc_sync()
{
    return [];
}
