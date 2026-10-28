#!/usr/bin/env python3
"""Audit every frozen x264 observation and summarize without exclusions."""
import argparse
import collections
import json
import math
import statistics as st
from pathlib import Path

from helpers import save, sha
from metrics import bd_rate

HERE = Path(__file__).resolve().parent
REPLAY = ['full', 'moment', 'joint', 'support', 'window_fixed',
          'window_real', 'window_checked', 'envelope', 'full4']
CERTIFIED = ['moment', 'joint', 'support', 'envelope', 'window_checked']


def paired(a, b):
    assert len(a) == len(b) and all(x > 0 for x in a + b)
    values = [100 * (x / y - 1) for x, y in zip(a, b)]
    return dict(percent_per_round=values, median_percent=st.median(values))


def replay(path, repeats):
    done = json.loads(path.with_suffix('.done.json').read_text())
    assert done['sha256'] == sha(path) and done['rounds'] == repeats
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    groups = collections.defaultdict(list)
    for row in rows:
        assert row['method'] in REPLAY and -1 <= row['repeat'] < repeats
        assert math.isfinite(row['seconds']) and row['seconds'] > 0
        groups[(row['frame'], row['method'])].append(row)
    frames = sorted({r['frame'] for r in rows})
    assert len(frames) == done['snapshots']
    assert len(rows) == len(frames) * len(REPLAY) * (repeats + 1)
    assert len({(r['frame'], r['method'], r['repeat']) for r in rows}) == len(rows)
    tau = rows[0]['tau']
    assert all(r['tau'] == tau for r in rows)
    for frame in frames:
        for method in REPLAY:
            observations = groups[(frame, method)]
            assert sorted(r['repeat'] for r in observations) == list(range(-1, repeats))
            assert len({r['output_fnv64'] for r in observations}) == 1
            assert len({r['work'] for r in observations}) == 1
            assert sum(r['audit'] for r in observations) == 1
        assert groups[(frame, 'full')][0]['output_fnv64'] == groups[(frame, 'full4')][0]['output_fnv64']
        # Each method scans the same deterministic decreasing-moment prefixes.
        work = {m: groups[(frame, m)][0]['work'] for m in REPLAY}
        assert work['envelope'] <= work['support'] <= work['joint'] <= work['moment'] <= work['full']
    totals = {m: [sum(r['seconds'] for r in rows if r['method'] == m and r['repeat'] == i)
                  for i in range(repeats)] for m in REPLAY}
    result = dict(tau=tau, filtered_frames=len(frames), rows=len(rows), formal_rounds=repeats,
                  replay_sha256=sha(path), methods={})
    for method in REPLAY:
        audit = [r for r in rows if r['method'] == method and r['audit']]
        item = dict(seconds_per_round=totals[method],
                    **paired(totals[method], totals['full']),
                    pixels=sum(r['pixels'] for r in audit),
                    sse=sum(r['sse'] for r in audit),
                    max_error=max(r['max_error'] for r in audit),
                    violations=sum(r['violations'] for r in audit),
                    tile_reference_work=sum(r['work'] for r in audit))
        if method in CERTIFIED:
            assert item['violations'] == 0 and item['max_error'] <= tau
        if method in ['full', 'full4']:
            assert item['sse'] == item['max_error'] == item['violations'] == 0
        result['methods'][method] = item
    base_work = result['methods']['full']['tile_reference_work']
    for method, item in result['methods'].items():
        item['work_percent'] = 100 * (item['tile_reference_work'] / base_work - 1)
    result['envelope_vs_support'] = paired(totals['envelope'], totals['support'])
    result['support_vs_extrema'] = paired(totals['support'], totals['moment'])
    result['eight_vs_four'] = paired(totals['full'], totals['full4'])
    result['envelope_extra_omitted_tiles'] = (
        result['methods']['support']['tile_reference_work'] -
        result['methods']['envelope']['tile_reference_work'])
    return result


def end_to_end(directory, case, protocol):
    from run_study import jobs
    rows = json.loads((directory / 'results.json').read_text())
    prescribed = jobs(protocol['end_to_end']['methods'])
    assert len(rows) == len(prescribed) == 49
    for row, job in zip(rows, prescribed):
        assert all(row[k] == v for k, v in job.items())
    status = json.loads((directory / 'status.json').read_text())
    assert status['status'] == 'completed' and status['source'] == case
    formal = [r for r in rows if r['kind'] == 'formal']
    assert len(formal) == 42
    methods = protocol['end_to_end']['methods']
    curves, timing, bdr, vs_off = {}, {}, {}, {}
    base = [next(r['seconds'] for r in formal if r['method'] == 'full' and r['crf'] == 27 and r['repeat'] == i) for i in range(3)]
    off = [next(r['seconds'] for r in formal if r['method'] == 'off' and r['crf'] == 27 and r['repeat'] == i) for i in range(3)]
    for method in methods:
        curve = sorted([r for r in formal if r['method'] == method and r['repeat'] == 0], key=lambda r: r['crf'])
        assert [r['crf'] for r in curve] == [22, 27, 32, 37]
        curves[method] = [{k: r[k] for k in ['crf', 'bitrate_kbps', 'psnr_y', 'seconds', 'sse_yuv', 'sha256', 'bytes']} for r in curve]
        times = [next(r['seconds'] for r in formal if r['method'] == method and r['crf'] == 27 and r['repeat'] == i) for i in range(3)]
        timing[method] = dict(seconds_per_round=times, **paired(times, base), vs_off=paired(times, off))
        for crf in [22, 27, 32, 37]:
            assert len({r['sha256'] for r in rows if r['method'] == method and r['crf'] == crf}) == 1
    for crf in [22, 27, 32, 37]:
        assert {r['sha256'] for r in formal if r['method'] in ['full', 'full4'] and r['crf'] == crf}.__len__() == 1
    def points(method):
        return [(r['psnr_y'], r['bitrate_kbps']) for r in curves[method]]
    for method in methods:
        bdr[method] = bd_rate(points('full'), points(method))
        vs_off[method] = bd_rate(points('off'), points(method))
        assert bdr[method]['percent'] is not None and vs_off[method]['percent'] is not None
    unique = {r['sha256']: r['metric_file'] for r in formal}
    pixels = case['width'] * case['height'] * case['frames']
    for digest, name in unique.items():
        metrics = json.loads((directory / name).read_text())
        assert len(metrics['per_frame_sse_yuv']) == case['frames']
        assert metrics['samples_yuv'] == [pixels, pixels // 4, pixels // 4]
        assert metrics['sse_yuv'] == [sum(row[k] for row in metrics['per_frame_sse_yuv']) for k in range(3)]
        for row in formal:
            if row['sha256'] == digest:
                assert row['sse_yuv'] == metrics['sse_yuv'] and row['psnr_y'] == metrics['psnr_y']
    manifest = json.loads((directory / 'capture/manifest.json').read_text())
    fullhash = next(r['sha256'] for r in formal if r['method'] == 'full' and r['crf'] == 27)
    assert manifest['matches_full'] and manifest['bitstream_sha256'] == fullhash
    assert manifest['source_sha256'] == case['sha256']
    captures = json.loads((directory / 'capture/metrics.json').read_text())
    formal_full = next(r for r in formal if r['method'] == 'full' and r['crf'] == 27)
    assert captures['sse_yuv'] == formal_full['sse_yuv']
    return dict(jobs=len(rows), formal_jobs=len(formal), unique_strict_metric_decodes=len(unique),
                capture_strict_decodes=1, capture_matches_formal_full=True,
                full4_full8_streams_identical=True, source=case, curves=curves,
                crf27_timing=timing, bd_rate=bdr, bd_rate_vs_off=vs_off,
                envelope_vs_support=paired(timing['envelope']['seconds_per_round'], timing['support']['seconds_per_round']),
                eight_vs_four=paired(base, timing['full4']['seconds_per_round']))


def aggregate_replays(sources):
    result = {}
    for tau in [1, 2, 3]:
        key = str(tau)
        result[key] = {}
        for method in REPLAY:
            items = [s['replay'][key]['methods'][method] for s in sources]
            result[key][method] = dict(
                mean_time_percent=st.mean(x['median_percent'] for x in items),
                mean_work_percent=st.mean(x['work_percent'] for x in items),
                pixels=sum(x['pixels'] for x in items), sse=sum(x['sse'] for x in items),
                max_error=max(x['max_error'] for x in items),
                violations=sum(x['violations'] for x in items),
                tile_reference_work=sum(x['tile_reference_work'] for x in items))
        result[key]['comparisons'] = {
            k: dict(mean_time_percent=st.mean(s['replay'][key][k]['median_percent'] for s in sources))
            for k in ['envelope_vs_support', 'support_vs_extrema', 'eight_vs_four']}
        result[key]['comparisons']['envelope_extra_omitted_tiles'] = sum(s['replay'][key]['envelope_extra_omitted_tiles'] for s in sources)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--development', action='store_true')
    args = parser.parse_args()
    protocol = json.loads((HERE / 'protocol.json').read_text())
    assert sha(HERE / 'protocol.json') == (HERE / 'protocol.sha256').read_text().split()[0]
    cases = protocol['development'] if args.development else protocol['sources']
    sources = []
    for case in cases:
        directory = HERE / ('development' if args.development else 'experiments') / case['id']
        entry = dict(id=case['id'], replay={str(t): replay(directory / f'replay_tau{t}.jsonl', 3 if args.development else 5) for t in [1, 2, 3]})
        if not args.development:
            entry['end_to_end'] = end_to_end(directory, case, protocol)
        sources.append(entry)
    result = dict(scope='Previously observed development inputs' if args.development else
                  'Frozen official-x264 replication on three previously observed 1080p contents; no content significance claim',
                  author='Xiujun Wang', sources=sources, aggregate_replay=aggregate_replays(sources),
                  protocol_sha256=sha(HERE / 'protocol.json'))
    if not args.development:
        result['aggregate_end_to_end'] = {
            m: dict(mean_crf27_time_percent=st.mean(s['end_to_end']['crf27_timing'][m]['median_percent'] for s in sources),
                    mean_bd_rate_percent=st.mean(s['end_to_end']['bd_rate'][m]['percent'] for s in sources),
                    mean_crf27_time_vs_off_percent=st.mean(s['end_to_end']['crf27_timing'][m]['vs_off']['median_percent'] for s in sources),
                    mean_bd_rate_vs_off_percent=st.mean(s['end_to_end']['bd_rate_vs_off'][m]['percent'] for s in sources))
            for m in protocol['end_to_end']['methods']}
        result['counts'] = {k: sum(s['end_to_end'][k] for s in sources) for k in
                            ['jobs', 'formal_jobs', 'unique_strict_metric_decodes', 'capture_strict_decodes']}
        result['counts']['filtered_frames'] = sum(s['replay']['2']['filtered_frames'] for s in sources)
        result['counts']['audit_pixels_per_method_and_tolerance'] = result['aggregate_replay']['2']['full']['pixels']
        result['comparisons'] = {k: st.mean(s['end_to_end'][k]['median_percent'] for s in sources)
                                 for k in ['envelope_vs_support', 'eight_vs_four']}
    output = HERE / ('development_summary.json' if args.development else 'summary.json')
    save(output, result)
    print(output)
    print(json.dumps(result.get('aggregate_end_to_end', result['aggregate_replay']['2']), indent=2))


if __name__ == '__main__':
    main()
