<?php

// Pure legacy configuration builders: no OPNsense, filesystem or process access.

// ─── Build routing block from comma-separated CIDR string ────────────────────
function xray_build_routing(string $bypassRaw): array
{
    $bypassNets = array_values(array_filter(array_map('trim', explode(',', $bypassRaw))));
    if (empty($bypassNets)) {
        $bypassNets = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'];
    }
    return [
        'domainStrategy' => 'IPIfNonMatch',
        'rules' => [[
            'type'        => 'field',
            'ip'          => $bypassNets,
            'outboundTag' => 'direct',
        ]],
    ];
}

function xray_build_config(array $c): array
{
    $raw = trim($c['outbound_config'] ?? '');
    if ($raw === '') {
        throw new InvalidArgumentException("outbound_config is empty");
    }
    $outbound = json_decode($raw, true);
    if (!is_array($outbound) || empty($outbound['protocol'])) {
        throw new InvalidArgumentException("outbound_config must be a valid Xray outbound JSON object");
    }
    return [
        'log'      => ['loglevel' => $c['loglevel'] ?? 'warning'],
        'inbounds' => [[
            'tag'      => 'socks-in',
            'port'     => (int)($c['socks5_port'] ?? 10808),
            'listen'   => $c['socks5_listen'] ?? '127.0.0.1',
            'protocol' => 'socks',
            'settings' => ['auth' => 'noauth', 'udp' => true, 'ip' => $c['socks5_listen'] ?? '127.0.0.1'],
        ]],
        'outbounds' => [$outbound, ['tag' => 'direct', 'protocol' => 'freedom']],
        'routing'   => xray_build_routing($c['bypass_networks'] ?? ''),
    ];
}

function yaml_scalar(string $value): string
{
    // Keep simple scalars unchanged; quote everything with YAML-significant
    // characters. json_encode() produces a valid double-quoted YAML scalar.
    if ($value !== '' && preg_match('/^[A-Za-z0-9._\/@+\-]+$/D', $value)) {
        return $value;
    }

    $encoded = json_encode($value, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    return $encoded !== false ? $encoded : '""';
}

function xray_build_t2s_config(array $c): string
{
    $proxyUri  = 'socks5://' . $c['socks5_listen'] . ':' . $c['socks5_port'];
    return 'proxy: ' . yaml_scalar($proxyUri) . "\n"
          . 'device: ' . yaml_scalar((string)$c['tun_iface']) . "\n"
          . 'mtu: ' . (int)$c['mtu'] . "\n"
          . "loglevel: info\n";
}
