import json
import os
from pathlib import Path
import resource
import shutil
import signal
import struct
import subprocess
import sys

from .storage import read_json


def limits():
    resource.setrlimit(resource.RLIMIT_CPU,(600,600))
    resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,512*1024**2))
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def sandbox_command(settings,directory,quality,duration):
    if os.uname().machine!='x86_64':
        raise RuntimeError('The renderer seccomp profile currently supports Linux x86_64')
    # BPF checks syscall numbers; sockets/connect/send/recv are denied. File
    # access is separately limited to mounted runtime dependencies and this job.
    records=[(0x20,0,0,0)]
    for number in (41,42,43,44,45,46,47,49,50,53,288):
        records += [(0x15,0,1,number),(0x06,0,0,0x00050001)]
    records += [(0x06,0,0,0x7fff0000)]
    profile=Path(directory)/'render.seccomp'
    profile.write_bytes(b''.join(struct.pack('HBBI',*r) for r in records))
    fd=os.open(profile,os.O_RDONLY)
    command=['bwrap','--die-with-parent','--new-session','--unshare-pid','--clearenv']
    mounts=['/usr','/lib','/lib64',settings.python_base,str(Path(settings.manim_python).resolve().parents[1]),
            str(Path(settings.manim_python).parent.parent)]
    for path in dict.fromkeys(mounts):
        if Path(path).exists():command+=['--ro-bind',path,path]
    for path in ['/etc/fonts','/etc/ld.so.cache','/etc/localtime']:
        if Path(path).exists():command+=['--ro-bind',path,path]
    command+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--bind',str(Path(directory).resolve()),'/work',
              '--dir','/work/home','--dir','/work/cache','--setenv','HOME','/work/home',
              '--setenv','XDG_CACHE_HOME','/work/cache','--setenv','PATH','/usr/bin:/bin',
              '--setenv','OPENBLAS_NUM_THREADS','2','--setenv','OMP_NUM_THREADS','2',
              '--setenv','PYTHONPATH','/work','--chdir','/work','--seccomp',str(fd),
              settings.manim_python,'/work/render_entry.py','/work/scene.py',quality,str(duration)]
    return command,fd


def render(settings,directory,code,quality,duration):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    (directory/'scene.py').write_text(code)
    for file in ['lesson_runtime.py','render_entry.py']:
        shutil.copy2(Path(__file__).parent/file,directory/file)
    shutil.copy2(Path(__file__).parent/'validation.py',directory/'scene_validation.py')
    command,fd=sandbox_command(settings,directory,quality,duration)
    try:
        with (directory/'render.log').open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,pass_fds=(fd,),
                                  preexec_fn=limits,timeout=settings.render_timeout)
    finally:
        os.close(fd)
    if result.returncode:
        detail=(directory/'render.log').read_text()[-6500:]
        if "No module named 'scene_validation'" in detail or "No module named 'lesson_runtime'" in detail:
            raise RuntimeError('Render infrastructure is incomplete:\n'+detail)
        raise ValueError('Manim render failed:\n'+detail)
    geometry=read_json(directory/'geometry.json')
    output=directory/Path(geometry['output']).relative_to('/work')
    if not output.is_file():
        raise ValueError('Renderer did not produce an MP4')
    return output,geometry


def checkpoints(video,directory,duration):
    paths=[]
    for i,fraction in enumerate((.2,.4,.65,.82)):
        path=Path(directory)/f'checkpoint-{i+1}.png'
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(duration*fraction),'-i',str(video),
                        '-frames:v','1','-vf','scale=1280:-1',str(path)],check=True,timeout=40)
        paths.append(path)
    return paths


def join_and_check(clips,output,quality):
    output=Path(output)
    listing=output.parent/'concat.txt'
    # Clip paths come only from server-generated UUID job directories.
    listing.write_text(''.join("file '"+str(Path(p).resolve()).replace("'","'\\''")+"'\n" for p in clips))
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),
                    '-c','copy','-an','-movflags','+faststart',str(output)],check=True,timeout=180)
    metadata=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(output)],timeout=30))
    streams=metadata['streams']
    width,height=(854,480) if quality=='preview' else (1920,1080)
    video=next(s for s in streams if s['codec_type']=='video')
    if video['codec_name']!='h264' or (video['width'],video['height'])!=(width,height) or any(s['codec_type']=='audio' for s in streams):
        raise ValueError('Final MP4 does not match the requested silent H.264 output')
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True,timeout=180)
    return {'duration_seconds':float(metadata['format']['duration']),'width':width,'height':height,
            'fps':video['avg_frame_rate'],'codec':'h264','audio':False,'full_decode':'passed'}
