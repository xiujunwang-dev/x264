"""Input inspection, exact decoded error, and explicit x264 commands."""
import hashlib,json,math,subprocess
from pathlib import Path
import numpy as np
METHODS={'full':(1,2,8),'extrema':(2,2,8),'support':(3,2,8),
         'envelope':(4,2,8),'window1':(1,1,8),'full4':(1,2,4),'off':(0,2,8)}
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def save(p,value):
    p=Path(p);tmp=p.with_suffix('.pending');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(p)
def inspect_source(data,expected_frames=None):
    end=data.find(b'\n')+1;assert end>0 and data[:end].startswith(b'YUV4MPEG2 ')
    header=data[:end];tags={s[:1].decode():s[1:].decode() for s in header.split()[1:]}
    width,height=int(tags['W']),int(tags['H']);size=width*height*3//2
    assert width%2==height%2==0 and tags.get('C','420') in ['420','420jpeg','420mpeg2','420paldv']
    assert tags.get('I','p')=='p'
    offsets=[];pos=end
    while pos<len(data):
        stop=data.find(b'\n',pos)+1;assert stop>pos and data[pos:stop].startswith(b'FRAME')
        offsets.append(stop);pos=stop+size;assert pos<=len(data)
    assert pos==len(data)
    if expected_frames is not None:assert len(offsets)==expected_frames
    fn,fd=map(int,tags['F'].split(':'))
    return dict(width=width,height=height,frames=len(offsets),frame_bytes=size,
                offsets=offsets,fps_n=fn,fps_d=fd,header=header.decode().strip())
def encoder_command(binary,info,method,crf,stream,source,frames=None,threads=1):
    mode,ran,kernel=METHODS[method]
    command=[str(binary),'--preset','medium','--threads',str(threads),'--sync-lookahead','0',
        '--lookahead-threads','1','--bframes','3','--rc-lookahead','20','--keyint','60',
        '--min-keyint','25','--scenecut','40','--frames',str(frames or info['frames']),
        '--mctf-method',str(mode),'--mctf-range',str(ran),'--mctf-kernel',str(kernel),
        '--mctf-tau','2','--mctf-qp','27','--log-level','error','--no-progress',
        '--crf',str(crf),'-o',str(stream),str(source)]
    if method=='off':
        command=[x for i,x in enumerate(command) if not x.startswith('--mctf-')
                 and not (i and command[i-1].startswith('--mctf-'))]
    return command
def decode_metrics(stream,source,info,log):
    command=['ffmpeg','-nostdin','-v','error','-xerror','-err_detect','explode',
        '-threads','1','-i',str(stream),'-vsync','0','-pix_fmt','yuv420p','-f','rawvideo','pipe:1']
    sums=[0,0,0];pixels=info['width']*info['height'];cuts=[0,pixels,pixels*5//4,pixels*3//2]
    digest=hashlib.sha256();per_frame=[]
    with Path(log).open('wb') as f:
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=f)
        try:
            for offset in info['offsets']:
                decoded=proc.stdout.read(info['frame_bytes']);assert len(decoded)==info['frame_bytes'],'Short decoded frame'
                digest.update(decoded)
                a=np.frombuffer(source,dtype=np.uint8,count=info['frame_bytes'],offset=offset)
                b=np.frombuffer(decoded,dtype=np.uint8);frame_sse=[]
                for k in range(3):
                    diff=a[cuts[k]:cuts[k+1]].astype(np.int32)-b[cuts[k]:cuts[k+1]]
                    value=int(np.sum(diff*diff,dtype=np.int64));sums[k]+=value;frame_sse.append(value)
                per_frame.append(frame_sse)
            assert proc.stdout.read(1)==b'','Extra decoded frames'
            assert proc.wait()==0,'Strict decoder failure'
        except BaseException:
            proc.kill();proc.wait();raise
    samples=[pixels*info['frames'],pixels*info['frames']//4,pixels*info['frames']//4]
    psnr=[10*math.log10(65025*n/s) if s else None for n,s in zip(samples,sums)]
    return dict(sse_yuv=sums,samples_yuv=samples,psnr_yuv=psnr,psnr_y=psnr[0],
                decoded_sha256=digest.hexdigest(),per_frame_sse_yuv=per_frame,decode_command=command)
