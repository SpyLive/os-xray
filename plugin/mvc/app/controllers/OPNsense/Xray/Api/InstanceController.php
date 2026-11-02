<?php

namespace OPNsense\Xray\Api;

use OPNsense\Base\ApiMutableModelControllerBase;

class InstanceController extends ApiMutableModelControllerBase
{
    protected static $internalModelClass = '\OPNsense\Xray\Instance';
    protected static $internalModelName  = 'instance';

    public function searchItemAction()
    {
        $response = $this->searchBase('instance', ['enabled', 'name', 'outbound_config']);
        if (!empty($response['rows'])) {
            foreach ($response['rows'] as &$row) {
                $ob       = json_decode($row['outbound_config'] ?? '', true);
                $settings = is_array($ob) ? ($ob['settings'] ?? []) : [];

                // Xray 26.x simplified VLESS settings first, legacy vnext fallback.
                if (isset($settings['address'])) {
                    $row['server_address'] = (string)$settings['address'];
                    $row['server_port']    = isset($settings['port']) ? (string)$settings['port'] : '';
                } else {
                    $vnext = $settings['vnext'][0] ?? [];
                    $row['server_address'] = (string)($vnext['address'] ?? '');
                    $row['server_port']    = isset($vnext['port']) ? (string)$vnext['port'] : '';
                }
                unset($row['outbound_config']);
            }
            unset($row);
        }
        return $response;
    }

    public function toggleItemAction($uuid, $enabled = null)
    {
        return $this->toggleBase('instance', $uuid, $enabled);
    }

    public function getItemAction($uuid = null)
    {
        $response = $this->getBase('instance', 'instance', $uuid);
        // Dialog metadata: only an existing, saved object can be validated.
        $response['instance_uuid'] = isset($response['instance']) && is_string($uuid)
            && preg_match('/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/iD', $uuid) ? $uuid : '';
        return $response;
    }

    public function addItemAction()
    {
        return $this->addBase('instance', 'instance');
    }

    public function setItemAction($uuid)
    {
        return $this->setBase('instance', 'instance', $uuid);
    }

    public function delItemAction($uuid)
    {
        return $this->delBase('instance', $uuid);
    }
}
