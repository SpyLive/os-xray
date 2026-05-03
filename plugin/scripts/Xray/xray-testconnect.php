#!/usr/local/bin/php
<?php
/**
 * xray-testconnect.php — BUG-4 FIX: тест подключения через SOCKS5-прокси.
 *
 * До исправления: порт 10808 был захардкожен в actions_xray.conf:
 *   parameters:--socks5 127.0.0.1:10808 -s -L ...
 * Проблема: если пользователь изменил socks5_port в GUI, тест продолжал
 * стучаться на старый порт и всегда возвращал ошибку подключения.
 *
 * После: читаем socks5_port из config.xml — тест всегда использует актуальный порт.
 */

require_once('config.inc');

// UUID инстанса как первый аргумент (из actions_xray.conf %1)
$instUuid = isset($argv[1]) ? preg_replace('/[^0-9a-fA-F\-]/', '', trim($argv[1])) : '';

$cfg = OPNsense\Core\Config::getInstance()->object();
$ins = $cfg->OPNsense->xray->instances ?? null;

$inst = null;
if ($ins) {
    foreach ($ins->instance as $candidate) {
        if ($instUuid === '' || (string)$candidate['uuid'] === $instUuid) {
            $inst = $candidate;
            if ($instUuid !== '') break;
        }
    }
}

// Читаем адрес и порт из конфига найденного инстанса
$listen = (string)($inst->socks5_listen ?? '127.0.0.1') ?: '127.0.0.1';
$port   = (int)(string)($inst->socks5_port ?? 10808);

// Защита: порт должен быть в допустимом диапазоне
if ($port < 1 || $port > 65535) {
    $port = 10808;
}

// 0.0.0.0 слушает на всех интерфейсах — для теста подключаемся на loopback
$connectAddr = ($listen === '0.0.0.0') ? '127.0.0.1' : $listen;
$proxy   = $connectAddr . ':' . $port;
$target  = 'https://1.1.1.1';
$timeout = '10';

exec(
    '/usr/local/bin/curl'
    . ' --socks5 ' . escapeshellarg($proxy)
    . ' -s -L -o /dev/null'
    . ' -w %{http_code}'
    . ' ' . escapeshellarg($target)
    . ' --max-time ' . $timeout,
    $out,
    $rc
);

echo implode('', $out) . "\n";
exit($rc);
