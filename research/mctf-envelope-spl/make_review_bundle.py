#!/usr/bin/env python3
"""Bundle only the new x264 sources and compact, traceable research evidence."""
import json
import tarfile
from pathlib import Path

from helpers import save, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if HERE.parent.name == 'research' else HERE


def main():
    checks = json.loads((HERE / 'package_checks.json').read_text())
    visual = json.loads((HERE / 'visual_review.json').read_text())
    assert checks['passed'] and visual['completed']
    for name, item in checks['pdfs'].items():
        assert visual['pdfs'][name]['sha256'] == item['sha256']
    files = set()
    suffixes = {'.py', '.c', '.h', '.tex', '.json', '.jsonl', '.txt', '.md', '.patch', '.sha256', '.stderr', '.log'}
    skip_roots = {'source', 'upstream', 'capture', 'sanitizer', 'sources', '__pycache__',
                  'patch_rebuild', 'patch_restore', 'review_bundle_manifest.json'}
    skip_names = {'review_bundle_manifest.json', 'authoring.log', 'delivery.json',
                  'render_before_percent_fix.json'}
    for path in HERE.rglob('*'):
        if not path.is_file():
            continue
        relative = path.relative_to(HERE)
        if relative.parts[0] in skip_roots or any(p in ['snapshots', '__pycache__'] for p in relative.parts):
            continue
        if path.name in skip_names or path.suffix not in suffixes:
            continue
        if relative.parts[0] == 'manuscript' and path.suffix not in {'.tex'}:
            continue
        files.add(path)
    files.add(HERE / 'upstream.tar')
    for name in ['mctf_spl_x264_draft.pdf', 'mctf_spl_x264_supplement.pdf',
                 'mctf_spl_x264_submission.pdf', 'mctf_spl_x264_submission_supplement.pdf']:
        files.add(ROOT / 'output/pdf' / name)
    records = []
    for path in sorted(files):
        name = 'x264-study/' + str(path.relative_to(HERE)) if path.is_relative_to(HERE) else 'pdf/' + path.name
        records.append(dict(path=path, archive=name, bytes=path.stat().st_size, sha256=sha(path)))
    manifest = dict(author='Xiujun Wang', platform='Official x264 r3223 plus isolated MCTF extension',
                    files=[{k: v for k, v in row.items() if k != 'path'} for row in records],
                    excluded='Original Y4M files, encoded bitstreams, binary snapshots, build products and executable binaries remain locally; exact source archive, patch and evidence hashes are included.',
                    scientific_review='Author independent scientific review is not recorded as complete; the author deferred closest full-text comparisons. Global novelty is unverified; no journal submission has occurred.')
    save(HERE / 'review_bundle_manifest.json', manifest)
    output = ROOT / 'output/mctf_x264_review_bundle.tar.gz'
    with tarfile.open(output, 'w:gz') as archive:
        for row in records:
            archive.add(row['path'], arcname=row['archive'])
        archive.add(HERE / 'review_bundle_manifest.json', arcname='x264-study/review_bundle_manifest.json')
    digest = sha(output)
    output.with_suffix(output.suffix + '.sha256').write_text(digest + '  ' + output.name + '\n')
    with tarfile.open(output) as archive:
        members = {x.name: x for x in archive.getmembers()}
        assert len(members) == len(records) + 1
        import hashlib
        for row in records:
            assert hashlib.sha256(archive.extractfile(members[row['archive']]).read()).hexdigest() == row['sha256']
    print(output)
    print('Verified', len(records), 'files;', output.stat().st_size, 'bytes;', digest)


if __name__ == '__main__':
    main()
