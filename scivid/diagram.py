"""Diagram chapters: the trusted spec renderer, run in a bubblewrap sandbox (no network, LaTeX available)."""
import json
import os
from pathlib import Path
import resource
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent


def seccomp_profile(path):
    records = [(0x20, 0, 0, 0)]
    for number in (41, 42, 43, 44, 45, 46, 47, 49, 50, 53, 288):  # socket family syscalls denied
        records += [(0x15, 0, 1, number), (0x06, 0, 0, 0x00050001)]
    records += [(0x06, 0, 0, 0x7fff0000)]
    path.write_bytes(b''.join(struct.pack('HBBI', *r) for r in records))


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (900, 900))
    resource.setrlimit(resource.RLIMIT_AS, (8 * 1024 ** 3, 8 * 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def render_spec(settings, work, spec, cues, duration, title, quality):
    """Render a declarative diagram spec with the trusted renderer, sandboxed (LaTeX available, no network)."""
    work = Path(work)
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    h, w, fps = (480, 854, 15) if quality == 'preview' else (settings.height, settings.width, settings.fps)
    (work / 'payload.json').write_text(json.dumps({'spec': spec, 'cues': cues, 'duration': duration, 'title': title,
                                                   'resolution': [h, w, fps]}))
    for name in ('diagram_render.py', 'diagram_spec.py'):
        shutil.copy2(HERE / name, work / name)
    seccomp_profile(work / 'render.seccomp')
    fd = os.open(work / 'render.seccomp', os.O_RDONLY)
    venv = Path(settings.manim_python).parent.parent
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid', '--clearenv']
    for path in dict.fromkeys(['/usr', '/lib', '/lib64', settings.python_base, str(venv),
                               str(Path(settings.manim_python).resolve().parents[1]), '/etc/fonts', '/etc/ld.so.cache',
                               '/etc/localtime', '/etc/texmf', '/var/lib/texmf']):
        if Path(path).exists():
            cmd += ['--ro-bind', path, path]
    cmd += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp', '--bind', str(work.resolve()), '/work',
            '--dir', '/work/home', '--setenv', 'HOME', '/work/home', '--setenv', 'PATH', '/usr/bin:/bin',
            '--setenv', 'PYTHONPATH', '/work', '--setenv', 'OMP_NUM_THREADS', '2', '--chdir', '/work',
            '--seccomp', str(fd), settings.manim_python, '/work/diagram_render.py', '/work/payload.json']
    try:
        with (work / 'render.log').open('w') as log:
            result = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, pass_fds=(fd,), preexec_fn=limits,
                                    timeout=settings.render_timeout)
    finally:
        os.close(fd)
    if result.returncode:
        raise ValueError('Diagram render failed:\n' + (work / 'render.log').read_text()[-3000:])
    out = json.loads((work / 'result.json').read_text())
    return work / Path(out['output']).relative_to('/work')


def frames(video, times, out_dir):
    paths = []
    for i, t in enumerate(times):
        path = Path(out_dir) / f'review-{i + 1}.jpg'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t:.2f}', '-i', str(video), '-frames:v', '1',
                        '-q:v', '3', str(path)], check=True, timeout=60)
        paths.append(path)
    return paths
