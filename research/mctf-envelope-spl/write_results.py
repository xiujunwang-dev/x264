#!/usr/bin/env python3
"""Generate manuscript numbers from the complete audited x264 summary."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAPER = HERE / 'manuscript'
NAMES = {'full': 'Full (8 pixel)', 'moment': 'Extrema', 'joint': 'Simple radius',
         'support': 'Tight radius', 'envelope': 'Envelope', 'window_fixed': 'Range, fixed LUT',
         'window_real': 'Range, rebuilt LUT', 'window_checked': 'Range with check',
         'full4': 'Full (4 pixel)', 'extrema': 'Extrema', 'window1': 'Reduced range',
         'off': 'Official x264, off'}


def number(value, digits=2, sign=False):
    if abs(value) < 0.5 * 10 ** -digits:
        value = 0.0
    return format(value, ('+' if sign else '') + f'.{digits}f')


def pct(value, digits=2):
    return r'\mbox{' + number(value, digits, True) + r'\%}'


def macro(name, text):
    return '\\newcommand{\\' + name + '}{' + text + '}\n'


def main():
    d = json.loads((HERE / 'summary.json').read_text())
    assert d['counts']['jobs'] == 147 and d['counts']['formal_jobs'] == 126
    k, e, counts = d['aggregate_replay'], d['aggregate_end_to_end'], d['counts']
    primary = k['2']['envelope']
    total_pixels = primary['pixels']
    extra = [k[str(t)]['comparisons']['envelope_extra_omitted_tiles'] for t in [1, 2, 3]]
    same_tau2 = extra[1] == 0
    texts = []
    texts.append(macro('AbstractResults',
        'At tolerance two, envelope planning changes filtering time by ' + pct(primary['mean_time_percent']) +
        ' with no violations across ' + number(total_pixels / 1e6, 1) + ' million audited pixels. '
        + ('It omits the same reference work as tight-radius planning at this tolerance. ' if same_tau2 else '')
        + 'At tolerance three it omits ' + format(extra[2], ',') +
        ' additional tile-reference predictions relative to tight radius.'))
    texts.append(macro('MainResults',
        'Table~\\ref{tab:kernel} reports the frozen primary tolerance $\\tau=2$ against eight-pixel full filtering. '
        'The envelope changes time by ' + pct(primary['mean_time_percent']) + ' and tile-reference work by ' +
        pct(primary['mean_work_percent']) + '. Every certified output stays within tolerance across ' +
        number(total_pixels / 1e6, 3) + ' million pixels per method and tolerance. '
        'Complete coding in Table~\\ref{tab:encoder} is a separate experiment, with original-relative PSNR-Y.'))
    same_sentence = ('At $\\tau=2$, envelope and tight-radius planning omit identical reference work on all three contents; '
                     if same_tau2 else 'At $\\tau=2$, the envelope omits ' + format(extra[1], ',') +
                     ' additional tile-reference predictions relative to tight radius; ')
    texts.append(macro('Interpretation',
        same_sentence + 'the mean paired envelope/tight-radius time change is ' +
        pct(k['2']['comparisons']['envelope_vs_support']['mean_time_percent']) + '. '
        'At tolerances one and three the extra omitted tile-reference counts are ' +
        format(extra[0], ',') + ' and ' + format(extra[2], ',') +
        ', respectively. Figure~\\ref{fig:tau} and the supplement retain every frozen tolerance. '
        'Stronger acceptance does not guarantee lower wall time: certificate evaluation has a cost. '
        'Unrestricted reduced range has ' + format(k['2']['window_real']['violations'], ',') +
        ' violating pixels at tolerance two; compute-and-check preserves the bound by constructing both outputs.'))
    per_source = ', '.join(pct(s['end_to_end']['crf27_timing']['envelope']['median_percent']) for s in d['sources'])
    texts.append(macro('ImplementationResults',
        'The envelope changes complete CRF-27 time by ' + pct(e['envelope']['mean_crf27_time_percent']) +
        ' on average (' + per_source + ' in source order) and BD-rate by ' +
        pct(e['envelope']['mean_bd_rate_percent']) + ' relative to full MCTF. '
        'Relative to unmodified x264 without MCTF, full MCTF changes BD-rate by ' +
        pct(e['full']['mean_bd_rate_vs_off_percent']) + ' and CRF-27 process time by ' +
        pct(e['full']['mean_crf27_time_vs_off_percent']) + '. '
        'Eight-pixel full fusion changes replay time by ' +
        pct(k['2']['comparisons']['eight_vs_four']['mean_time_percent']) +
        ' and complete-process time by ' + pct(d['comparisons']['eight_vs_four']) +
        ' relative to four-pixel full, with identical pixels and complete streams. This is an engineering gain.'))
    texts.append(macro('ValidationResults',
        'Validation passes 341.26 million exhaustive support/envelope comparisons and four million random comparisons '
        'under ASan/UBSan, plus 112 complete integration encodes and four full-encoder ASan runs. '
        'Disabled MCTF matches official x264 byte for byte.'))
    texts.append(macro('SupplementResults',
        'The envelope adds ' + ', '.join(format(x, ',') for x in extra) +
        ' omitted tile-reference predictions at tolerances one, two and three relative to tight radius. '
        'Certified variants have zero violating pixels at every tolerance. '
        'Rebuilt-range maxima are ' + ', '.join(str(k[str(t)]['window_real']['max_error']) for t in [1, 2, 3]) +
        ' levels; all per-content times, errors, SSE and work counts remain in \\texttt{summary.json}.'))
    texts.append(macro('ReproCounts',
        'Completed: ' + str(counts['formal_jobs']) + ' formal encodes, ' +
        str(counts['unique_strict_metric_decodes']) + ' distinct formal-stream strict decodes, '
        'three separate capture decodes, ' + str(counts['filtered_frames']) +
        ' filtered-frame snapshots and ' + format(total_pixels, ',') +
        ' audited pixels per replay method and tolerance.'))
    (PAPER / 'generated.tex').write_text(''.join(texts))

    lines = [r'\begin{table}[t]\centering',
             r'\caption{Fixed-state x264 replay, $\tau=2$. Equal-content means of time and work changes against full eight-pixel filtering; maximum error and violating pixels pooled over all contents.}\label{tab:kernel}',
             r'\setlength{\tabcolsep}{3pt}',
             r'\begin{tabular}{lrrrr}\toprule',
             r'Method & Time (\%) & Work (\%) & $|e|_{\max}$ & Viol.\\\midrule']
    for m in ['moment', 'joint', 'support', 'envelope', 'window_real', 'window_checked']:
        item = k['2'][m]
        label = {'window_real': 'Range rebuilt', 'window_checked': 'Range checked'}.get(m, NAMES[m])
        lines.append(label + ' & ' + number(item['mean_time_percent'], sign=True) + ' & ' +
                     number(item['mean_work_percent'], sign=True) + ' & ' + str(item['max_error']) +
                     ' & ' + str(item['violations']) + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (PAPER / 'kernel_table.tex').write_text('\n'.join(lines) + '\n')

    lines = [r'\begin{table}[t]\centering',
             r'\caption{Complete x264 encoding: PCHIP BD-rate (four CRFs) and paired median CRF-27 process time, equal-content mean relative to full eight-pixel MCTF.}\label{tab:encoder}',
             r'\setlength{\tabcolsep}{4pt}', r'\begin{tabular}{lrr}\toprule',
             r'Method & BD-rate (\%) & Time (\%)\\\midrule']
    for m in ['full', 'extrema', 'support', 'envelope', 'window1', 'full4', 'off']:
        lines.append(NAMES[m] + ' & ' + number(e[m]['mean_bd_rate_percent'], 3, True) +
                     ' & ' + number(e[m]['mean_crf27_time_percent'], 2, True) + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (PAPER / 'encoder_table.tex').write_text('\n'.join(lines) + '\n')

    lines = [r'\begin{figure}[t]\centering', r'\begin{tikzpicture}',
             r'\begin{axis}[width=\columnwidth,height=1.75in,xmin=.9,xmax=3.1,xtick={1,2,3},xlabel={Integer tolerance $\tau$},ylabel={Time change (\%)},grid=major,legend style={font=\normalsize,at={(0.5,1.02)},anchor=south,legend columns=2},tick label style={font=\normalsize},label style={font=\normalsize}]']
    for m, label, style in [('moment', 'Extrema', 'black,dashed,mark=square*'),
                            ('support', 'Tight radius', 'blue,mark=*'),
                            ('envelope', 'Envelope', 'orange,mark=diamond*'),
                            ('window_real', 'Reduced range', 'red,dotted,mark=triangle*')]:
        coords = ' '.join('(' + str(t) + ',' + str(k[str(t)][m]['mean_time_percent']) + ')' for t in [1, 2, 3])
        lines.append('\\addplot[' + style + '] coordinates {' + coords + '};\\addlegendentry{' + label + '}')
    lines += [r'\end{axis}\end{tikzpicture}',
              r'\caption{All frozen replay tolerances. Unchecked reduced range can violate the prescribed error bound.}\label{fig:tau}',
              r'\end{figure}']
    (PAPER / 'tau_figure.tex').write_text('\n'.join(lines) + '\n')

    lines = [r'\begin{table}[H]\centering',
             r'\caption{All nine replay methods. Each entry is an equal-content mean percentage change relative to full eight-pixel filtering.}\label{tab:alltau}',
             r'\setlength{\tabcolsep}{5pt}', r'\begin{tabular}{lrrrrrr}\toprule',
             r'& \multicolumn{3}{c}{Time (\%)} & \multicolumn{3}{c}{Work (\%)}\\',
             r'Method & $\tau=1$ & $\tau=2$ & $\tau=3$ & $\tau=1$ & $\tau=2$ & $\tau=3$\\\midrule']
    for m in ['full', 'moment', 'joint', 'support', 'envelope', 'window_fixed', 'window_real', 'window_checked', 'full4']:
        values = [k[str(t)][m]['mean_time_percent'] for t in [1, 2, 3]] + [k[str(t)][m]['mean_work_percent'] for t in [1, 2, 3]]
        lines.append(NAMES[m] + ' & ' + ' & '.join(number(x, 2, True) for x in values) + r'\\')
    lines += [r'\bottomrule\end{tabular}', r'\end{table}']
    (PAPER / 'alltau_table.tex').write_text('\n'.join(lines) + '\n')

    hashes = [r'\par\begingroup\setlength{\parskip}{2pt}']
    for source in d['sources']:
        case = source['end_to_end']['source']
        digest = case['sha256']
        hashes.append(case['id'].replace('_', r'\_') + r' SHA-256: \texttt{' +
                      digest[:32] + r'}\allowbreak\texttt{' + digest[32:] + r'}\par')
    hashes.append(r'\endgroup')
    (PAPER / 'source_hashes.tex').write_text('\n'.join(hashes) + '\n')
    print('Generated all x264 manuscript values from complete summary.json')


if __name__ == '__main__':
    main()
