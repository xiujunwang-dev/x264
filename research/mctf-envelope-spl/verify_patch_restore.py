#!/usr/bin/env python3
"""Check restored executable behavior against the frozen builds, without timing."""
import json
import subprocess
from pathlib import Path

from helpers import encoder_command, save, sha

HERE = Path(__file__).resolve().parent


def main():
    plan = json.loads((HERE / 'protocol.json').read_text())
    restored = json.loads((HERE / 'patch_restore_validation.json').read_text())
    assert restored['passed'] and len(restored['builds']) == 4
    case = plan['development'][0]
    source = HERE / 'sources' / case['file']
    assert sha(source) == case['sha256']
    directory = HERE / 'patch_smoke'
    directory.mkdir(exist_ok=False)
    records = {}
    for label, builds in [('frozen', plan['builds']), ('restored', restored['builds'])]:
        records[label] = {}
        for method in ['off', 'full', 'full4', 'envelope']:
            item = builds['upstream' if method == 'off' else 'source']
            assert sha(item['path']) == item['sha256']
            stream = directory / (label + '-' + method + '.264')
            command = encoder_command(item['path'], case, method, 27, stream, source, frames=41)
            with stream.with_suffix('.log').open('w') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
            records[label][method] = dict(command=command, sha256=sha(stream))
    for method in records['frozen']:
        assert records['frozen'][method]['sha256'] == records['restored'][method]['sha256'], method
    assert records['restored']['full']['sha256'] == records['restored']['full4']['sha256']
    stream = directory / 'restored-disabled.264'
    command = encoder_command(restored['builds']['source']['path'], case, 'off', 27,
                              stream, source, frames=41)
    with stream.with_suffix('.log').open('w') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
    assert sha(stream) == records['restored']['off']['sha256']
    save(HERE / 'patch_smoke_validation.json', dict(
        passed=True, complete_encodes=9, frames_per_encode=41, source_sha256=case['sha256'],
        restored_and_frozen_streams_identical=True, restored_full4_full8_identical=True,
        restored_disabled_matches_official=True, records=records,
        disabled=dict(command=command, sha256=sha(stream)),
        scope='Untimed patch-delivery verification, excluded from every reported performance observation'))
    print('Nine untimed patch smoke encodes passed; frozen/restored streams match.')


if __name__ == '__main__':
    main()
