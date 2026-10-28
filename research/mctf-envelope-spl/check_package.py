#!/usr/bin/env python3
"""Check all retained x264 evidence and the exact delivered PDF constraints."""
import json
import platform
import re
import subprocess
from pathlib import Path

from helpers import save, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if HERE.parent.name == 'research' else HERE


def capture(directory, case, expected=None):
    manifest = json.loads((directory / 'capture/manifest.json').read_text())
    assert manifest['source_sha256'] == case['sha256']
    assert sha(directory / 'capture/capture.264') == manifest['bitstream_sha256']
    if expected:
        assert manifest['matches_full'] and manifest['bitstream_sha256'] == expected
    snapshots = directory / 'capture/snapshots'
    assert {p.name for p in snapshots.glob('*.bin')} == set(manifest['snapshots'])
    for name, item in manifest['snapshots'].items():
        path = snapshots / name
        assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256']
    for tau in [1, 2, 3]:
        path = directory / f'replay_tau{tau}.jsonl'
        done = json.loads(path.with_suffix('.done.json').read_text())
        assert done['snapshots'] == len(manifest['snapshots']) and sha(path) == done['sha256']
    return len(manifest['snapshots'])


def main():
    from pypdf import PdfReader
    import pdfplumber

    protocol = json.loads((HERE / 'protocol.json').read_text())
    d = json.loads((HERE / 'summary.json').read_text())
    assert sha(HERE / 'protocol.json') == (HERE / 'protocol.sha256').read_text().split()[0] == d['protocol_sha256']
    for name, digest in protocol['code'].items():
        assert sha(HERE / name) == digest, name
    for name, item in protocol['builds'].items():
        assert sha(item['path']) == item['sha256'], name
        assert sha(Path(item['path']).parent / 'config.mak') == item['config_mak_sha256'], name
    assert sha(protocol['replay_binary']['path']) == protocol['replay_binary']['sha256']
    assert sha(HERE / 'source_manifest.json') == protocol['source_manifest_sha256']
    manifest = json.loads((HERE / 'source_manifest.json').read_text())
    source = Path(protocol['builds']['source']['path']).parent
    for name, digest in manifest['files'].items():
        assert sha(source / name) == digest, name
    if (HERE / 'x264_mctf.patch').exists():
        assert sha(HERE / 'x264_mctf.patch') == manifest['patch_sha256']
    restored = json.loads((HERE / 'patch_restore_validation.json').read_text())
    assert restored['passed'] and restored['source_files_verified'] == len(manifest['files'])
    assert restored['source_manifest_sha256'] == sha(HERE / 'source_manifest.json')
    assert restored['patch_sha256'] == manifest['patch_sha256']
    assert set(restored['builds']) == {'upstream', 'source', 'capture', 'sanitizer'}
    for item in restored['builds'].values():
        assert sha(item['path']) == item['sha256']
    records = {}
    for case in protocol['development'] + protocol['sources']:
        assert sha(HERE / 'sources' / case['file']) == case['sha256']
        is_main = case in protocol['sources']
        directory = HERE / ('experiments' if is_main else 'development') / case['id']
        count = 0
        expected = None
        if is_main:
            rows = json.loads((directory / 'results.json').read_text())
            assert len(rows) == 49
            assert json.loads((directory / 'status.json').read_text())['status'] == 'completed'
            for row in rows:
                assert sha(directory / row['stream']) == row['sha256'], row['stream']
            count = len(rows)
            expected = next(r['sha256'] for r in rows if r['method'] == 'full' and r['crf'] == 27 and r['kind'] == 'formal')
        records[case['id']] = dict(source_verified=True, stream_hashes_verified=count,
                                   snapshot_hashes_verified=capture(directory, case, expected))
    tests = {}
    for name in ['envelope', 'support', 'uniform8']:
        value = json.loads((HERE / f'test_{name}.json').read_text())
        assert value['passed']
        tests[name] = value
    integration = json.loads((HERE / 'integration_validation.json').read_text())
    assert integration['passed'] and integration['complete_encodes'] == 112
    assert integration['upstream_disabled_byte_identical'] and integration['full4_full8_byte_identical']
    assert len(integration['sanitizer']) == 4 and all(x['returncode'] == 0 for x in integration['sanitizer'])
    pdfs = {}
    for name in ['mctf_spl_x264_draft', 'mctf_spl_x264_supplement',
                 'mctf_spl_x264_submission', 'mctf_spl_x264_submission_supplement']:
        path = ROOT / 'output/pdf' / (name + '.pdf')
        reader = PdfReader(path)
        texts = [p.extract_text() for p in reader.pages]
        text = '\n'.join(texts)
        assert 'Xiujun Wang' in text and reader.metadata.author == 'Xiujun Wang'
        assert not re.search(r'\bs264\b|authors? pending|\?\?', text, re.I)
        if 'submission' in name:
            assert 'Review draft' not in text and 'Not submitted.' not in text
        if not name.endswith('supplement'):
            compact_text = re.sub(r'\s+', '', text)
            assert 'xiujunwang.dev@gmail.com' in compact_text and '0009-0006-2773-7936' in compact_text
            assert len(texts) <= 5
            reference = next(i for i, page in enumerate(texts) if re.search(r'^\s*R\s*E\s*F\s*E\s*R\s*E\s*N\s*C\s*E\s*S\s*$', page, re.I | re.M))
            assert reference <= 4
            if len(texts) == 5:
                assert reference == 4
                assert 'CONCLUSION' not in texts[4] and 'ACKNOWLEDGMENT' not in texts[4]
        else:
            assert len(texts) == 2
            assert 'Supplementary Material' in texts[0] and 'Information for Reproducibility' in texts[1]
        with pdfplumber.open(path) as pdf:
            boxes = []
            for page in pdf.pages:
                chars = [x for x in page.chars if x['text'].strip()]
                box = dict(page=page.page_number, left=min(c['x0'] for c in chars),
                           right=max(c['x1'] for c in chars), top=min(c['top'] for c in chars),
                           bottom=max(c['bottom'] for c in chars))
                assert box['left'] >= 71.9 and box['right'] <= page.width - 71.9, box
                assert box['top'] >= 71.9 and box['bottom'] <= page.height - 71.9, box
                boxes.append(box)
        pdfs[name] = dict(pages=len(texts), sha256=sha(path), author=reader.metadata.author, text_boxes=boxes)
    main = (HERE / 'manuscript/main.tex').read_text()
    abstract = main.split('\\begin{abstract}')[1].split('\\end{abstract}')[0]
    generated = (HERE / 'manuscript/generated.tex').read_text()
    replacement = re.search(r'\\newcommand\{\\AbstractResults\}\{(.*)\}', generated).group(1)
    abstract = abstract.replace('\\AbstractResults', replacement).replace('\\%', ' percent')
    words = len(abstract.split())
    assert 100 <= words <= 175, words
    for stem in ['main', 'supplement', 'main_submission', 'supplement_submission']:
        log = (HERE / 'manuscript' / (stem + '.log')).read_text()
        assert not re.search(r'(?:LaTeX Warning:.*undefined|There were undefined references|Overfull \\hbox)', log)
    record = dict(passed=True, author='Xiujun Wang', protocol_sha256=d['protocol_sha256'],
                  source_files_verified=len(manifest['files']), evidence=records, tests=tests,
                  clean_patch_restore_builds_verified=len(restored['builds']),
                  integration_encodes=integration['complete_encodes'], full_encoder_asan_runs=4,
                  counts=d['counts'], abstract_words=words, pdfs=pdfs,
                  verification_python_platform=platform.platform(), machine=platform.machine(),
                  measured_binary_architecture=subprocess.check_output(['file', protocol['builds']['source']['path']], text=True).strip(),
                  human_scientific_review_completed=False, global_novelty_established=False,
                  visual_review_record='visual_review.json')
    save(HERE / 'package_checks.json', record)
    print(json.dumps({k: v for k, v in record.items() if k not in ['evidence', 'tests']}, indent=2))


if __name__ == '__main__':
    main()
