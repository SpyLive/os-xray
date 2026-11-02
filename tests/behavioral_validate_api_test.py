#!/usr/bin/env python3
"""Production API actions; only framework and configd boundaries are stubbed."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
api = root / 'plugin/mvc/app/controllers/OPNsense/Xray/Api'
prelude = r'''<?php
namespace OPNsense\Base;
class ApiMutableServiceControllerBase { public $request; }
class ApiMutableModelControllerBase {
 function getBase($prefix,$node,$uuid) {
  return $uuid===null || $uuid===$GLOBALS['known'] ? ['instance'=>['name'=>'fixture']] : [];
 }
}
namespace OPNsense\Core;
class Backend {
 function configdRun($command) { $GLOBALS['commands'][]=$command; return 'OK: config is valid'; }
}
namespace Test;
function verify($value,$message) { if (!$value) throw new \RuntimeException($message); }
'''
checks = r'''
namespace Test;
$known='00000000-0000-4000-8000-000000000002'; $commands=[];
$instance=new \OPNsense\Xray\Api\InstanceController();
verify($instance->getItemAction($known)['instance_uuid']===$known,'saved UUID metadata');
verify($instance->getItemAction()['instance_uuid']==='','unsaved instance metadata');
verify($instance->getItemAction('00000000-0000-4000-8000-000000000001')['instance_uuid']==='','unknown UUID metadata');
$service=new \OPNsense\Xray\Api\ServiceController();
$service->request=new class { public $post=true; function isPost() { return $this->post; } };
verify($service->validateAction($known)['result']==='ok','saved instance validation');
verify($commands===['xray validate '.$known],'exact selected UUID forwarded');
foreach(['invalid','!!!',$known.';'] as $bad) verify($service->validateAction($bad)['result']==='failed','invalid UUID refused');
verify(count($commands)===1,'invalid UUID cannot fall back to first instance');
$service->request->post=false;
verify($service->validateAction($known)['result']==='failed','POST required');
verify(count($commands)===1,'GET no backend call');
$service->request->post=true;
verify($service->validateAction()['result']==='ok','legacy empty UUID API remains available');
verify($commands[1]==='xray validate','legacy endpoint preserved');
echo "Validate API and saved dialog identity: PASS\n";
'''
source = '\n'.join((api / name).read_text()[5:] for name in
                   ['InstanceController.php', 'ServiceController.php'])
run = subprocess.run(['php'], input=prelude + source + checks,
                     capture_output=True, text=True, timeout=15)
assert run.returncode == 0, run.stdout + run.stderr
print(run.stdout.strip())
