#!/usr/bin/env python3
"""Execute installer/upgrade PHP publication in temp dirs; interrupt each rename.
This does not execute the installers, change config.xml, services or /usr/local.
"""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
for filename, variable in [('install.sh','PLUGIN_DIR'),('upgrade.sh','SRC')]:
    source=(ROOT/filename).read_text()
    start=source.index('# Publish dependencies before their consumer')
    end=source.index('\ninstall_tree ',start)
    publication=source[start:end]
    count=len(list((ROOT/'plugin/scripts/Xray').iterdir()))
    for fail in range(1,count+2):
        with tempfile.TemporaryDirectory(prefix='os-xray-upgrade-') as tmp:
            d=Path(tmp); dest=d/'installed'; dest.mkdir(); commands=d/'bin'; commands.mkdir()
            controller=dest/'xray-service-control.php'
            old='<?php echo "legacy controller remains usable\\n";\n'
            controller.write_text(old)
            wrapper=commands/'mv'
            wrapper.write_text('''#!/bin/sh
n=0
[ ! -f "$COUNT_FILE" ] || n=$(cat "$COUNT_FILE")
n=$((n+1))
printf '%s' "$n" > "$COUNT_FILE"
[ "$n" -ne "$FAIL_AT" ] || exit 72
exec /bin/mv "$@"
''')
            wrapper.chmod(0o755)
            script='set -eu\n'+variable+'='+shlex.quote(str(ROOT/'plugin'))+'\n'
            script+=publication.replace('SCRIPT_DST=/usr/local/opnsense/scripts/Xray', 'SCRIPT_DST='+shlex.quote(str(dest)))
            result=subprocess.run(['sh','-c',script],env={**os.environ,'PATH':str(commands)+':'+os.environ['PATH'],
                'COUNT_FILE':str(d/'count'),'FAIL_AT':str(fail)},capture_output=True,text=True)
            assert result.returncode==(1 if fail<=count else 0),result.stderr
            actual=controller.read_text()
            assert actual in [old,(ROOT/'plugin/scripts/Xray/xray-service-control.php').read_text()]
            if actual==old:
                probe=subprocess.run(['php',str(controller)],capture_output=True,text=True)
                assert probe.returncode==0 and 'legacy controller' in probe.stdout
            else:
                for module in ['xray-config.php','xray-apply.php']:
                    assert (dest/module).read_bytes()==(ROOT/'plugin/scripts/Xray'/module).read_bytes()
            for file in dest.glob('*.php'):
                probe=subprocess.run(['php','-l',str(file)],capture_output=True,text=True)
                assert probe.returncode==0,probe.stderr
    print(f'{filename}: interruption at each of {count} publications + success: PASS')
