#!/usr/bin/env python3
"""Exercise real x264 integration and its disabled upstream equivalence."""
import json,os,subprocess
from pathlib import Path
from helpers import sha,save,encoder_command
HERE=Path(__file__).resolve().parent
def main():
    out=HERE/'validation';out.mkdir(exist_ok=False)
    sources=[]
    for w,h,n in [(34,34,41),(352,288,17)]:
        p=out/f'input-{w}x{h}.y4m'
        with p.open('wb') as f:
            f.write(f'YUV4MPEG2 W{w} H{h} F25:1 Ip A1:1 C420jpeg\n'.encode())
            for t in range(n):
                f.write(b'FRAME\n');f.write(bytes((x*3+y*5+t*7+(x+t)//8*13)%256 for y in range(h) for x in range(w)))
                f.write(bytes([128])*(w*h//2))
        sources.append((p,dict(width=w,height=h,frames=n)))
    records=[];env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0')
    for p,info in sources:
        for frames in ([1,2,3,4,5,17,41] if info['frames']==41 else [17]):
            for threads in [1,4]:
                reference=None
                for label,binary,method in [('stock',HERE/'upstream/x264','off'),
                    ('disabled',HERE/'source/x264','off'),
                    ('full4',HERE/'source/x264','full4'),('full',HERE/'source/x264','full'),
                    ('extrema',HERE/'source/x264','extrema'),('support',HERE/'source/x264','support'),
                    ('envelope',HERE/'source/x264','envelope')]:
                    name=f'{p.stem}-f{frames}-t{threads}-{label}';stream=out/(name+'.264')
                    cmd=encoder_command(binary,info,method,27,stream,p,frames,threads)
                    with (out/(name+'.log')).open('w') as log:
                        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
                    assert result.returncode==0,(name,result.returncode)
                    digest=sha(stream)
                    if label=='stock':reference=digest
                    if label=='disabled':assert digest==reference,'Disabled extension changed stock stream'
                    if label=='full4':full=digest
                    if label=='full':assert full==digest,'Fusion kernel changed complete stream'
                    records.append(dict(name=name,sha256=digest,command=cmd))
    # Complete C encoder sanitizers, separate from all timed experiments.
    sanitizer=[]
    p,info=sources[0]
    for method in ['full','extrema','support','envelope']:
        name='sanitizer-'+method;stream=out/(name+'.264')
        cmd=encoder_command(HERE/'sanitizer/x264',info,method,27,stream,p)
        with (out/(name+'.log')).open('w') as log:
            result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env)
        sanitizer.append(dict(command=cmd,returncode=result.returncode,log=name+'.log'))
        assert result.returncode==0,(name,'See retained sanitizer log')
    save(HERE/'integration_validation.json',dict(passed=True,complete_encodes=len(records),
        records=records,sanitizer=sanitizer,upstream_disabled_byte_identical=True,
        full4_full8_byte_identical=True,dimensions=[[34,34],[352,288]],
        input_lengths=[1,2,3,4,5,17,41],threads=[1,4]))
    print('PASS',len(records),'integration encodes and',len(sanitizer),'sanitizer encodes')
if __name__=='__main__':main()
