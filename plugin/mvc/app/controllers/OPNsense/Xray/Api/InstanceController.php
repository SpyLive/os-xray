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
                $ob    = json_decode($row['outbound_config'] ?? '', true);
                $vnext = $ob['settings']['vnext'][0] ?? [];
                $row['server_address'] = $vnext['address'] ?? '';
                $row['server_port']    = isset($vnext['port']) ? (string)$vnext['port'] : '';
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

    public function toggleItemAction($uuid, $enabled = null)
    {
        return $this->toggleBase('instance', $uuid, $enabled);
    }

    public function getItemAction($uuid = null)
    {
        return $this->getBase('instance', 'instance', $uuid);
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
