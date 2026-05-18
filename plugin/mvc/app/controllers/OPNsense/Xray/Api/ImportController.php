<?php

namespace OPNsense\Xray\Api;

use OPNsense\Base\ApiControllerBase;

class ImportController extends ApiControllerBase
{
    public function parseAction()
    {
        if (!$this->request->isPost()) {
            return ['status' => 'error', 'message' => 'POST required'];
        }

        $requestData = $this->extractRequestData();
        $link = $requestData['link'];

        if (empty($link)) {
            return ['status' => 'error', 'message' => 'No VLESS link provided'];
        }

        if (strlen($link) > 2048) {
            return ['status' => 'error', 'message' => 'Link too long'];
        }

        $data = $this->parseVless($link);
        if (isset($data['error'])) {
            return ['status' => 'error', 'message' => $data['error']];
        }

        $data['status'] = 'ok';
        return $data;
    }

    /**
     * Extracts the link from request body (JSON with link_b64, or plain POST).
     * @return array{link: string}
     */
    private function extractRequestData(): array
    {
        $result = ['link' => ''];

        // JSON body ($.ajax contentType: application/json)
        $rawBody = file_get_contents('php://input');
        if (!empty($rawBody)) {
            $json = json_decode($rawBody, true);
            if (json_last_error() === JSON_ERROR_NONE) {
                if (!empty($json['link_b64'])) {
                    $decoded = base64_decode($json['link_b64'], true);
                    if ($decoded !== false) {
                        $result['link'] = trim($decoded);
                    }
                } elseif (!empty($json['link'])) {
                    $result['link'] = trim($json['link']);
                }
                return $result;
            }
        }

        // POST param link_b64 (base64-safe, & in link is not a problem)
        $b64 = $this->request->getPost('link_b64', 'string', '');
        if (!empty($b64)) {
            $decoded = base64_decode($b64, true);
            if ($decoded !== false) {
                $result['link'] = trim($decoded);
            }
        }

        // Plain POST link
        if (empty($result['link'])) {
            $link = $this->request->getPost('link', 'string', '');
            if (!empty($link)) {
                $result['link'] = trim($link);
            }
        }

        return $result;
    }

    private function parseVless(string $link): array
    {
        // Убираем лишние пробелы и кавычки
        $link = trim($link, " \t\n\r\0\x0B\"'");

        if (strpos($link, 'vless://') !== 0) {
            return ['error' => 'Link must start with vless://'];
        }

        // Убираем схему
        $rest = substr($link, 8); // после "vless://"

        // Отделяем #name в конце
        $name = '';
        if (($hashPos = strrpos($rest, '#')) !== false) {
            $name = htmlspecialchars(urldecode(substr($rest, $hashPos + 1)), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
            $rest = substr($rest, 0, $hashPos);
        }

        // Отделяем ?query
        $query = '';
        if (($qPos = strpos($rest, '?')) !== false) {
            $query = substr($rest, $qPos + 1);
            $rest  = substr($rest, 0, $qPos);
        }

        // Отделяем UUID@host:port
        // UUID — всё до последнего @ (на случай если @ есть в UUID — маловероятно, но надёжно)
        $atPos = strrpos($rest, '@');
        if ($atPos === false) {
            return ['error' => 'Missing @ separator between UUID and host'];
        }

        $uuid    = substr($rest, 0, $atPos);
        $hostport = substr($rest, $atPos + 1);

        // Разбираем host:port (с учётом IPv6 [::1]:port)
        if (substr($hostport, 0, 1) === '[') {
            // IPv6
            $closeBracket = strpos($hostport, ']');
            if ($closeBracket === false) {
                return ['error' => 'Invalid IPv6 address format'];
            }
            $host = substr($hostport, 1, $closeBracket - 1);
            $portStr = ltrim(substr($hostport, $closeBracket + 1), ':');
        } else {
            $lastColon = strrpos($hostport, ':');
            if ($lastColon === false) {
                return ['error' => 'Missing port in host:port'];
            }
            $host    = substr($hostport, 0, $lastColon);
            $portStr = substr($hostport, $lastColon + 1);
        }

        $port = (int)$portStr;
        if ($port <= 0 || $port > 65535) {
            return ['error' => 'Invalid port: ' . $portStr];
        }

        if (empty($uuid)) {
            return ['error' => 'UUID is empty'];
        }
        // BUG-10 FIX: валидация формата UUID до попадания в ответ.
        // Без этой проверки пользователь получал ошибку только в момент Apply через XML Mask —
        // непонятно далеко от точки ввода. Теперь ошибка сразу при парсинге.
        // \z вместо $ — строгий конец строки, не допускает трейлинг \n (баг PHP PCRE: $ совпадает перед \n)
        if (!preg_match('/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\z/', $uuid)) {
            return ['error' => 'Invalid UUID format (expected xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)'];
        }
        if (empty($host)) {
            return ['error' => 'Host is empty'];
        }

        // Парсим query string
        parse_str($query, $params);

        $type     = $params['type']     ?? 'tcp';
        $security = $params['security'] ?? 'reality';

        $flow = $params['flow'] ?? '';
        if (empty($flow)) {
            $flow = 'xtls-rprx-vision';
        }
        if ($type !== 'tcp') {
            $flow = '';
        }

        $fp = $params['fp'] ?? '';
        if (empty($fp)) {
            $fp = 'chrome';
        }

        // flow and fp whitelisted to known values (RCE/injection guard)
        $allowedFlow = ['xtls-rprx-vision', 'none', ''];
        $allowedFp   = ['chrome', 'firefox', 'safari', 'edge', 'random'];
        $flow = in_array($flow, $allowedFlow, true) ? $flow : 'xtls-rprx-vision';
        $fp   = in_array($fp,   $allowedFp,   true) ? $fp   : 'chrome';

        // Build outbound object — raw values (json_encode handles escaping)
        $outbound = [
            'tag'      => 'proxy',
            'protocol' => 'vless',
            'settings' => [
                'vnext' => [[
                    'address' => $host,
                    'port'    => $port,
                    'users'   => [[
                        'id'         => $uuid,
                        'encryption' => $params['encryption'] ?? 'none',
                        'flow'       => $flow,
                    ]],
                ]],
            ],
            'streamSettings' => $this->buildStreamSettings($type, $security, $params),
        ];

        return [
            'name'            => $name,
            'outbound_config' => json_encode($outbound, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE),
        ];
    }

    /**
     * Собирает streamSettings для xray-core конфига на основе transport type и security.
     */
    private function buildStreamSettings(string $type, string $security, array $params): array
    {
        $ss = [
            'network'  => $type,
            'security' => $security,
        ];

        // ── Security settings ────────────────────────────────────────────
        if ($security === 'reality') {
            $ss['realitySettings'] = [
                'serverName'  => $params['sni'] ?? '',
                'fingerprint' => $params['fp']  ?? 'chrome',
                'show'        => false,
                'publicKey'   => $params['pbk'] ?? '',
                'shortId'     => $params['sid'] ?? '',
                'spiderX'     => $params['spx'] ?? '',
            ];
        } elseif ($security === 'tls') {
            $tls = [
                'serverName'  => $params['sni'] ?? '',
                'fingerprint' => $params['fp']  ?? 'chrome',
            ];
            if (!empty($params['alpn'])) {
                $tls['alpn'] = explode(',', $params['alpn']);
            }
            $ss['tlsSettings'] = $tls;
        }

        // ── Transport settings ───────────────────────────────────────────
        switch ($type) {
            case 'xhttp':
                $xhttp = [];
                if (!empty($params['path'])) $xhttp['path'] = $params['path'];
                if (!empty($params['host'])) $xhttp['host'] = $params['host'];
                if (!empty($params['mode'])) $xhttp['mode'] = $params['mode'];
                if (!empty($xhttp)) $ss['xhttpSettings'] = $xhttp;
                break;

            case 'ws':
                $ws = [];
                if (!empty($params['path'])) $ws['path'] = $params['path'];
                if (!empty($params['host'])) $ws['headers'] = ['Host' => $params['host']];
                if (!empty($ws)) $ss['wsSettings'] = $ws;
                break;

            case 'grpc':
                $grpc = [];
                if (!empty($params['serviceName'])) $grpc['serviceName'] = $params['serviceName'];
                if (!empty($params['mode']))        $grpc['multiMode']   = ($params['mode'] === 'multi');
                if (!empty($grpc)) $ss['grpcSettings'] = $grpc;
                break;

            case 'h2':
            case 'http':
                $h2 = [];
                if (!empty($params['path'])) $h2['path'] = $params['path'];
                if (!empty($params['host'])) $h2['host'] = [$params['host']];
                if (!empty($h2)) $ss['httpSettings'] = $h2;
                break;

            case 'kcp':
                $kcp = [];
                if (!empty($params['headerType'])) $kcp['header'] = ['type' => $params['headerType']];
                if (!empty($params['seed']))       $kcp['seed']   = $params['seed'];
                if (!empty($kcp)) $ss['kcpSettings'] = $kcp;
                break;

            case 'tcp':
                if (!empty($params['headerType']) && $params['headerType'] === 'http') {
                    $tcp = ['header' => ['type' => 'http']];
                    if (!empty($params['path'])) {
                        $tcp['header']['request'] = ['path' => explode(',', $params['path'])];
                    }
                    if (!empty($params['host'])) {
                        if (!isset($tcp['header']['request'])) $tcp['header']['request'] = [];
                        $tcp['header']['request']['headers'] = ['Host' => explode(',', $params['host'])];
                    }
                    $ss['tcpSettings'] = $tcp;
                }
                break;
        }

        return $ss;
    }
}
