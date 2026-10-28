#!/usr/bin/env python3
"""Compile and render x264 PDFs after every measured study has completed."""
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] if HERE.parent.name == 'research' else HERE


def main():
    summary = json.loads((HERE / 'summary.json').read_text())
    assert summary['counts']['jobs'] == 147
    for source in summary['sources']:
        assert json.loads((HERE / 'experiments' / source['id'] / 'status.json').read_text())['status'] == 'completed'
    paper = HERE / 'manuscript'
    out = ROOT / 'output/pdf'
    renders = ROOT / 'tmp/pdfs/mctf-x264'
    out.mkdir(parents=True, exist_ok=True)
    renders.mkdir(parents=True, exist_ok=True)
    with (paper / 'authoring.log').open('w') as log:
        subprocess.run(['/Library/TeX/texbin/latexmk', '-pdf', '-silent',
                        '-interaction=nonstopmode', '-halt-on-error', 'main.tex', 'supplement.tex',
                        'main_submission.tex', 'supplement_submission.tex'],
                       cwd=paper, stdout=log, stderr=subprocess.STDOUT, check=True)
    for name, target in [('main', 'mctf_spl_x264_draft'), ('supplement', 'mctf_spl_x264_supplement'),
                         ('main_submission', 'mctf_spl_x264_submission'),
                         ('supplement_submission', 'mctf_spl_x264_submission_supplement')]:
        destination = out / (target + '.pdf')
        shutil.copy2(paper / (name + '.pdf'), destination)
        for stale in renders.glob(target + '-*.png'):
            stale.unlink()
        subprocess.run(['pdftoppm', '-r', '130', '-png', str(destination), str(renders / target)], check=True)
        print(destination)
    print('Every rendered page still requires visual review.')


if __name__ == '__main__':
    main()
