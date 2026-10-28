#!/usr/bin/env python3
"""Restore the exact published-source patch into a fresh review directory."""
import argparse
import json
import platform
import shutil
import subprocess
import tarfile
from pathlib import Path

from helpers import save, sha

HERE = Path(__file__).resolve().parent
CONFIG = ['--host=aarch64-apple-darwin', '--bit-depth=8', '--chroma-format=420',
          '--enable-static', '--disable-opencl', '--disable-lavf', '--disable-swscale',
          '--disable-ffms', '--disable-avs', '--disable-gpac']


def extract(archive, destination):
    with tarfile.open(archive) as tf:
        for item in tf.getmembers():
            relative = Path(item.name)
            assert not relative.is_absolute() and '..' not in relative.parts
            assert item.isdir() or item.isfile(), 'Unexpected archive member type'
        tf.extractall(destination, filter='data')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--build', action='store_true')
    args = parser.parse_args()
    dest = args.destination.resolve()
    assert not dest.exists(), 'Use a fresh destination; existing work is never replaced'
    provenance = json.loads((HERE / 'upstream_provenance.json').read_text())
    manifest = json.loads((HERE / 'source_manifest.json').read_text())
    assert sha(HERE / 'upstream.tar') == provenance['archive_sha256']
    assert sha(HERE / 'x264_mctf.patch') == manifest['patch_sha256']
    dest.mkdir(parents=True)
    for name in ['upstream', 'source']:
        extract(HERE / 'upstream.tar', dest / name)
    log = dest / 'restore.log'
    with log.open('w') as output:
        subprocess.run(['patch', '-p1', '-i', str(HERE / 'x264_mctf.patch')], cwd=dest / 'source',
                       stdout=output, stderr=subprocess.STDOUT, check=True)
    for name, digest in manifest['files'].items():
        assert sha(dest / 'source' / name) == digest, name
    # Metadata only: both exported trees report their pinned official revision.
    shutil.copy2(dest / 'source/version.sh', dest / 'upstream/version.sh')
    for name in ['capture', 'sanitizer']:
        shutil.copytree(dest / 'source', dest / name)
    record = dict(passed=True, source_files_verified=len(manifest['files']),
                  upstream=provenance, source_manifest_sha256=sha(HERE / 'source_manifest.json'),
                  patch_sha256=sha(HERE / 'x264_mctf.patch'),
                  platform=platform.platform(), machine=platform.machine(), builds={})
    if args.build:
        assert platform.system() == 'Darwin' and platform.machine() == 'arm64', (
            'The measured extension uses ARM64 NEON. Porting is required on another architecture.')
        for name, extra in [('upstream', []), ('source', []),
                            ('capture', ['--extra-cflags=-DX264_MCTF_CAPTURE=1']),
                            ('sanitizer', ['--disable-asm',
                             '--extra-cflags=-O1 -g -fsanitize=address -fno-sanitize-recover=all',
                             '--extra-ldflags=-fsanitize=address'])]:
            root = dest / name
            command = ['./configure', *CONFIG, *extra]
            with (root / 'build.log').open('w') as output:
                subprocess.run(command, cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
                subprocess.run(['make', '-j4', 'x264'], cwd=root, stdout=output, stderr=subprocess.STDOUT, check=True)
            record['builds'][name] = dict(path=str(root / 'x264'), sha256=sha(root / 'x264'),
                                          configure_command=command,
                                          config_mak_sha256=sha(root / 'config.mak'))
    save(dest / 'restore_validation.json', record)
    print(json.dumps({k: v for k, v in record.items() if k not in ['upstream', 'builds']}, indent=2))
    print('This restores sources/builds only; it does not rerun or validate performance claims.')


if __name__ == '__main__':
    main()
