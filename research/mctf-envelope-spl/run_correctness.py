#!/usr/bin/env python3
"""Run certificate/kernel sanitizers and real x264 integration in a fresh study."""
import json
import os
import subprocess
from pathlib import Path

from helpers import save, sha

HERE = Path(__file__).resolve().parent


def main():
    assert not (HERE / 'integration_validation.json').exists(), 'Preserve completed original validation'
    assert not (HERE / 'experiments').exists(), 'Correctness checks must precede measured encodes'
    headers = HERE / 'source/encoder'
    records = {}
    for name, source in [('envelope', HERE / 'test_envelope.c'),
                         ('support', HERE / 'templates/test_support.c'),
                         ('uniform8', HERE / 'test_uniform8.c')]:
        binary = HERE / ('test_' + name + '_san')
        extra = ['-DX264_MCTF_NEON_INTERPOLATION=1', '-DX264_MCTF_NEON_NORMALIZE=1',
                 '-DX264_MCTF_PRIOR_CONTROL=1'] if name == 'uniform8' else []
        command = ['clang', '-O1', '-g', '-fsanitize=address,undefined',
                   '-fno-sanitize-recover=all', *extra, '-I', str(headers), str(source), '-o', str(binary)]
        with (HERE / ('test_' + name + '.build.log')).open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        with (HERE / ('test_' + name + '.stderr')).open('w') as err:
            result = subprocess.run([str(binary)], env=env, stdout=subprocess.PIPE, stderr=err,
                                    text=True, check=True)
        value = json.loads(result.stdout)
        assert value['passed']
        save(HERE / ('test_' + name + '.json'), value)
        records[name] = dict(command=command, source_sha256=sha(source), binary_sha256=sha(binary))
    subprocess.run([os.sys.executable, str(HERE / 'validate_integration.py')], check=True)
    save(HERE / 'correctness_builds.json', records)
    print('Certificate/kernel ASan+UBSan and full-encoder integration/ASan completed before timing.')


if __name__ == '__main__':
    main()
