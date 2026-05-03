#!/usr/local/bin/php
<?php
/**
 * xray-log.php — хвост per-instance лога xray-core.
 * Аргумент: UUID инстанса. Без UUID — выводит общий лог (fallback).
 */

$uuid    = isset($argv[1]) ? preg_replace('/[^0-9a-fA-F\-]/', '', trim($argv[1])) : '';
$perInst = $uuid !== '' ? "/var/log/xray-core-{$uuid}.log" : '';
$logfile = ($perInst !== '' && file_exists($perInst)) ? $perInst : '/var/log/xray-core.log';

if (!file_exists($logfile)) {
    echo "(log file not found: {$logfile})\n";
    exit(0);
}

exec('/usr/bin/tail -n 200 ' . escapeshellarg($logfile), $out);
echo implode("\n", $out) . "\n";
