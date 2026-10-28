#!/usr/bin/env python3
"""Create a fresh x264 replication plan without rewriting original evidence."""
import argparse
import copy
import datetime
import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

from helpers import save, sha

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-directory', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    args = parser.parse_args()
    build = args.build_directory.resolve()
    dest = args.study.resolve()
    inputs = args.inputs.resolve()
    assert not dest.exists(), 'Use a fresh study directory'
    assert platform.machine() == 'arm64' and platform.system() == 'Darwin'
    original = json.loads((HERE / 'protocol.json').read_text())
    assert sha(HERE / 'protocol.json') == (HERE / 'protocol.sha256').read_text().split()[0]
    validation = json.loads((build / 'restore_validation.json').read_text())
    assert validation['passed'] and len(validation['builds']) == 4
    assert validation['source_manifest_sha256'] == sha(HERE / 'source_manifest.json')
    for item in validation['builds'].values():
        assert sha(item['path']) == item['sha256']
    for case in original['development'] + original['sources']:
        assert sha(inputs / case['file']) == case['sha256'], case['file']
    dest.mkdir(parents=True)
    shutil.copy2(build / 'restore_validation.json', dest / 'patch_restore_validation.json')
    for name in ['run_study.py', 'helpers.py', 'metrics.py', 'replay.c', 'summarize.py',
                 'write_results.py', 'write_report.py', 'build_pdfs.py', 'check_package.py',
                 'validate_integration.py', 'run_correctness.py', 'test_envelope.c', 'test_uniform8.c',
                 'restore_and_build.py', 'make_review_bundle.py', 'prepare_replication.py',
                 'source_manifest.json', 'upstream_provenance.json', 'upstream.tar', 'x264_mctf.patch',
                 'literature_audit.json', 'REPRODUCE.txt', 'submission_handoff.md', 'cover_letter.txt',
                 'author_information.json', 'publication.json']:
        if not (HERE / name).exists() and name in {'submission_handoff.md', 'cover_letter.txt'}:
            continue  # Paper-only files are supplied separately from the public code export.
        shutil.copy2(HERE / name, dest / name)
    shutil.copytree(HERE / 'templates', dest / 'templates')
    for name in ['source', 'upstream', 'capture', 'sanitizer']:
        (dest / name).symlink_to(build / name, target_is_directory=True)
    shutil.copytree(HERE / 'manuscript', dest / 'manuscript',
                    ignore=shutil.ignore_patterns('*.aux', '*.log', '*.out', '*.pdf', '*.fls', '*.fdb_latexmk'))
    (dest / 'sources').mkdir()
    for case in original['development'] + original['sources']:
        try:
            os.link(inputs / case['file'], dest / 'sources' / case['file'])
        except OSError:
            shutil.copy2(inputs / case['file'], dest / 'sources' / case['file'])
    command = ['clang', '-O3', '-std=c11', '-DX264_MCTF_NEON_INTERPOLATION=1',
               '-DX264_MCTF_NEON_NORMALIZE=1', '-DX264_MCTF_PRIOR_CONTROL=1',
               '-I', str(build / 'source/encoder'), str(dest / 'replay.c'), '-o', str(dest / 'replay')]
    with (dest / 'replay_build.log').open('w') as output:
        subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, check=True)
    subprocess.run([os.sys.executable, str(dest / 'run_correctness.py')], check=True)
    plan = copy.deepcopy(original)
    plan['created_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    plan['status'] = 'Fresh replication plan using the previously reported fixed x264 settings'
    plan['original_protocol_sha256'] = sha(HERE / 'protocol.json')
    plan['builds'] = validation['builds']
    plan['replay_binary'] = dict(path=str(dest / 'replay'), sha256=sha(dest / 'replay'), compile_command=command)
    plan['code'] = {name: sha(dest / name) for name in original['code']}
    plan['source_manifest_sha256'] = sha(dest / 'source_manifest.json')
    plan['replication_platform'] = dict(platform=platform.platform(), machine=platform.machine(),
                                        compiler=subprocess.check_output(['clang', '--version'], text=True))
    save(dest / 'protocol.json', plan)
    (dest / 'protocol.sha256').write_text(sha(dest / 'protocol.json') + '  protocol.json\n')
    save(dest / 'builds.json', validation['builds'])
    print(dest / 'protocol.json')
    print('New plan saved. Run run_study.py alone, without other benchmarks or document rendering.')


if __name__ == '__main__':
    main()
