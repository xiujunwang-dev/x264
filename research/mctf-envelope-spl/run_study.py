#!/usr/bin/env python3
"""Run the complete x264 protocol, preserving every stream and observation."""
import argparse,datetime,json,mmap,os,resource,subprocess,time
from pathlib import Path
from helpers import sha,save,inspect_source,encoder_command
HERE=Path(__file__).resolve().parent
def jobs(methods):
    rows=[dict(kind='warmup',repeat=-1,crf=27,method=m) for m in methods]
    for i,crf in enumerate([22,27,32,37]):
        rows += [dict(kind='formal',repeat=0,crf=crf,method=m) for m in methods[i:]+methods[:i]]
    for repeat in [1,2]:
        rows += [dict(kind='formal',repeat=repeat,crf=27,method=m) for m in methods[repeat:]+methods[:repeat]]
    return rows
def capture_and_replay(case,directory,p,expected=None,rounds=5):
    source=HERE/'sources'/case['file'];capture=directory/'capture';capture.mkdir(exist_ok=True)
    manifest=capture/'manifest.json'
    if not manifest.exists():
        assert not (capture/'capture.264').exists(),'Retain and review an incomplete capture'
        snapshots=capture/'snapshots';snapshots.mkdir(exist_ok=False)
        cmd=encoder_command(p['builds']['capture']['path'],case,'full',27,capture/'capture.264',source)
        env=dict(os.environ,MCTF_CAPTURE_DIR=str(snapshots))
        with (capture/'capture.log').open('w') as log:subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        from helpers import decode_metrics
        with source.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
            info=inspect_source(data,case['frames'])
            metrics=decode_metrics(capture/'capture.264',data,info,capture/'decode.log')
        save(capture/'metrics.json',metrics)
        digest=sha(capture/'capture.264')
        if expected:assert digest==expected,'Capture changed complete full stream'
        snapshots=sorted(snapshots.glob('*.bin'));assert snapshots
        save(manifest,dict(command=cmd,bitstream_sha256=digest,matches_full=bool(expected),
            source_sha256=case['sha256'],frames=case['frames'],
            snapshots={x.name:dict(bytes=x.stat().st_size,sha256=sha(x)) for x in snapshots}))
        print(case['id'],'captured',len(snapshots),'filtered frames',flush=True)
    if expected:assert json.loads(manifest.read_text())['bitstream_sha256']==expected
    snapshots=sorted((capture/'snapshots').glob('*.bin'))
    for tau in p['fixed_state']['tolerances']:
        target=directory/f'replay_tau{tau}.jsonl';done=directory/f'replay_tau{tau}.done.json'
        if done.exists():assert json.loads(done.read_text())['sha256']==sha(target);continue
        assert not target.exists(),'Retain an interrupted replay'
        cmd=[p['replay_binary']['path'],str(tau),str(rounds),*map(str,snapshots)]
        with target.open('w') as out,target.with_suffix('.stderr').open('w') as err:
            subprocess.run(cmd,stdout=out,stderr=err,check=True)
        save(done,dict(sha256=sha(target),snapshots=len(snapshots),rounds=rounds))
        print(case['id'],'replay tau',tau,'complete',flush=True)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--resume',action='store_true');args=ap.parse_args()
    p=json.loads((HERE/'protocol.json').read_text())
    assert sha(HERE/'protocol.json')==(HERE/'protocol.sha256').read_text().split()[0]
    for name,value in p['code'].items():assert sha(HERE/name)==value,name
    for value in p['builds'].values():assert sha(value['path'])==value['sha256']
    assert sha(p['replay_binary']['path'])==p['replay_binary']['sha256']
    for case in p['development']+p['sources']:
        assert sha(HERE/'sources'/case['file'])==case['sha256']
    for case in p['development']:
        directory=HERE/'development'/case['id'];directory.mkdir(parents=True,exist_ok=True)
        capture_and_replay(case,directory,p,rounds=3)
    from helpers import decode_metrics
    for case in p['sources']:
        directory=HERE/'experiments'/case['id']
        if directory.exists():assert args.resume,'Existing study requires --resume'
        directory.mkdir(parents=True,exist_ok=True)
        rows=json.loads((directory/'results.json').read_text()) if (directory/'results.json').exists() else []
        source=HERE/'sources'/case['file'];methods=p['end_to_end']['methods']
        with source.open('rb') as f,mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
            info=inspect_source(data,case['frames']);tasks=jobs(methods)
            metric_cache={r['sha256']:r['metric_file'] for r in rows if r.get('metric_file')}
            for index,job in enumerate(tasks):
                if index<len(rows):assert all(rows[index][k]==v for k,v in job.items());continue
                label=f"{index:02d}-{job['kind']}-{job['method']}-c{job['crf']}-r{job['repeat']}"
                stream=directory/(label+'.264');log=directory/(label+'.log')
                assert not stream.exists() and not log.exists(),'Retain and review any incomplete encode'
                binary=p['builds']['upstream' if job['method']=='off' else 'source']['path']
                command=encoder_command(binary,info,job['method'],job['crf'],stream,source)
                before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.monotonic()
                with log.open('w') as out:result=subprocess.run(command,stdout=out,stderr=subprocess.STDOUT,timeout=1200)
                seconds=time.monotonic()-start;after=resource.getrusage(resource.RUSAGE_CHILDREN)
                if result.returncode:
                    save(directory/'failure.json',dict(job=job,command=command,returncode=result.returncode,seconds=seconds))
                    raise RuntimeError('Encoding failure; retained attempt')
                digest=sha(stream)
                for old in rows:
                    if old['method']==job['method'] and old['crf']==job['crf']:assert old['sha256']==digest,'Nondeterministic repeated stream'
                    if {old['method'],job['method']}=={'full','full4'} and old['crf']==job['crf']:
                        assert old['sha256']==digest,'Eight-pixel fusion changed stream'
                row=dict(**job,command=command,seconds=seconds,cpu_user=after.ru_utime-before.ru_utime,
                    cpu_system=after.ru_stime-before.ru_stime,sha256=digest,bytes=stream.stat().st_size,
                    bitrate_kbps=stream.stat().st_size*8*info['fps_n']/info['fps_d']/info['frames']/1000,
                    stream=stream.name,log=log.name)
                if job['kind']=='formal':
                    if digest not in metric_cache:
                        metrics=decode_metrics(stream,data,info,directory/(label+'.decode.log'))
                        name=label+'.metrics.json';save(directory/name,metrics);metric_cache[digest]=name
                    metrics=json.loads((directory/metric_cache[digest]).read_text())
                    row.update(metric_file=metric_cache[digest],psnr_y=metrics['psnr_y'],sse_yuv=metrics['sse_yuv'])
                rows.append(row);save(directory/'results.json',rows)
                save(directory/'status.json',dict(status='running',source=case,completed_jobs=len(rows),prescribed_jobs=len(tasks),
                    updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
                print(case['id'],len(rows),'/',len(tasks),job['method'],'CRF',job['crf'],'r',job['repeat'],round(seconds,3),'s',flush=True)
        expected=next(r['sha256'] for r in rows if r['method']=='full' and r['crf']==27 and r['kind']=='formal')
        capture_and_replay(case,directory,p,expected)
        save(directory/'status.json',dict(status='completed',source=case,completed_jobs=len(rows),prescribed_jobs=len(tasks),
            completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        print(case['id'],'COMPLETE',flush=True)
if __name__=='__main__':main()
