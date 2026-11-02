#!/usr/bin/env python3
"""Real PHP CLI/controller/XML and subprocess validation; fake core executable.
No installed paths, daemons, network or OPNsense runtime are used.
"""
from pathlib import Path
import json
import sys
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
ID='00000000-0000-4000-8000-000000000001'
with tempfile.TemporaryDirectory(prefix='xray-cli-') as tmp:
    d=Path(tmp)
    core=d/'core'
    core.write_text('#!' + sys.executable + '\n' + '''from pathlib import Path
import json,sys
if sys.argv[1:]==['version']:
    print('Xray 26.3.27 test fixture'); sys.exit(0)
assert sys.argv[1:4]==['run','-test','-c'],sys.argv
assert sys.argv[5:]==['-format=json'],sys.argv
p=Path(sys.argv[4])
assert p.stat().st_mode & 0o777==0o600
config=json.loads(p.read_text())
Path(__file__).with_name('candidate-record.json').write_text(json.dumps({'path':str(p),'config':config}))
if config['outbounds'][0].get('tag')=='reject':
    print('test fixture rejects this outbound'); sys.exit(23)
print('Configuration OK')
''')
    core.chmod(0o755)
    controller=d/'xray-service-control.php'
    text=(ROOT/'plugin/scripts/Xray/xray-service-control.php').read_text()
    text=text.replace("'/usr/local/bin/xray-core'",repr(str(core)))
    controller.write_text(text)
    for name in ['xray-config.php','xray-apply.php']:
        (d/name).symlink_to(ROOT/'plugin/scripts/Xray'/name)
    (d/'config.inc').write_text('''<?php
namespace OPNsense\\Core;
class Config {
    static function getInstance() { return new self; }
    function object() { return simplexml_load_file(__DIR__.'/config.xml'); }
}
''')
    def xml(outbound):
        (d/'config.xml').write_text(f'''<opnsense><OPNsense><xray><general><enabled>1</enabled></general>
<instances><instance uuid="{ID}"><enabled>1</enabled><outbound_config>{outbound}</outbound_config>
<tun_interface>tun9</tun_interface><socks5_port>19080</socks5_port></instance></instances>
</xray></OPNsense></opnsense>''')
    def run(arg=ID):
        return subprocess.run(['php','-d','include_path='+str(d),str(controller),'validate',arg],
                              capture_output=True,text=True,timeout=10)
    xml('{"protocol":"freedom"}')
    good=run(); assert good.returncode==0,good.stdout+good.stderr
    assert 'OK: config is valid' in good.stdout
    record=json.loads((d/'candidate-record.json').read_text())
    assert not Path(record['path']).exists()
    assert record['config']['inbounds'][0]['port']==19080
    assert record['config']['inbounds'][0]['settings']['udp'] is True
    assert len(record['config']['inbounds'])==1
    print('CLI Validate: real XML -> builder -> external validator -> candidate cleanup: PASS')
    xml('{"protocol":"freedom","tag":"reject"}')
    bad=run(); assert bad.returncode==1 and 'test fixture rejects' in bad.stdout,bad.stdout+bad.stderr
    record=json.loads((d/'candidate-record.json').read_text())
    assert not Path(record['path']).exists()
    xml('{'); malformed=run(); assert malformed.returncode==1,malformed.stdout
    xml('{"protocol":"freedom"}')
    assert run('invalid').returncode==1
    assert run(ID[:-1]+'2').returncode==1
    assert run('%1').returncode==0
    core.unlink()
    missing=run(); assert missing.returncode==1 and 'unavailable' in missing.stdout,missing.stdout
    print('CLI Validate: core rejection, malformed JSON, bad/unknown UUID, configd placeholder, missing core: PASS')
