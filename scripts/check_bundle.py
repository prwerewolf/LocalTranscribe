"""Check a built/moved app; optional speech fixture verifies real stop/resume."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import tempfile

import bundle_runtime

ROOT = Path(__file__).resolve().parents[1]


def check(app, transcribe_fixture=False):
    app = app.resolve(strict=True)
    resources = app / 'Contents/Resources'
    bundle_runtime.output(['codesign', '--verify', '--deep', '--strict', str(app)])
    for path in app.rglob('*'):
        if path.is_symlink() and not path.resolve().is_relative_to(app):
            raise ValueError('The app contains a symlink to an external file')
        if bundle_runtime.is_macho(path):
            if any(value.startswith('/') and not value.startswith(bundle_runtime.SYSTEM_PREFIXES)
                   for value in bundle_runtime.dependencies(path)):
                raise ValueError(f'External native dependency in {path.name}')
    directory = ROOT / '.build'
    directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bundle-check-', dir=directory) as temporary:
        work = Path(temporary).resolve()
        environment = dict(os.environ)
        environment.pop('PYTHONPATH', None)
        environment['PYTHONHOME'] = str(resources / 'python')
        environment['PYTHONNOUSERSITE'] = '1'
        environment['PYTHONDONTWRITEBYTECODE'] = '1'
        environment['LOCALTRANSCRIBE_DATA_DIR'] = str(work / 'state')
        environment['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
        environment['HF_HUB_OFFLINE'] = '1'
        environment['HF_HUB_DISABLE_TELEMETRY'] = '1'
        environment['HF_HUB_DISABLE_IMPLICIT_TOKEN'] = '1'
        python = resources / 'python/bin/python3'
        code = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import local_runtime
local_runtime.configure_environment()
import mlx_whisper, numpy, scipy, torch
import mlx.core as mx
root = Path(sys.argv[2]).resolve()
assert Path(sys.prefix).resolve().is_relative_to(root)
for module in (mlx_whisper, numpy, scipy, torch):
    assert Path(module.__file__).resolve().is_relative_to(root)
assert mx.array([1]).item() == 1
print('Bundled Python, MLX, model assets, and native imports passed.')
'''
        subprocess.run([str(python), '-s', '-B', '-c', code, str(resources / 'app'), str(app)],
                       cwd=work, env=environment, check=True)
        command = [str(resources / 'local-transcribe')]
        subprocess.run(command + ['--version'], cwd=work, env=environment, check=True)
        for name in ('ffmpeg', 'ffprobe'):
            subprocess.run([str(resources / 'tools/bin' / name), '-version'], env=environment,
                           check=True, capture_output=True)
        if transcribe_fixture:
            audio = work / 'synthetic.aiff'
            subprocess.run(['/usr/bin/say', '-r', '130', '-o', str(audio),
                            'This is a synthetic recording for Local Transcribe. '
                            'Completed checkpoints must remain intact when processing is stopped. '
                            'Restarting should finish the remaining audio and create the transcript.'], check=True)
            output = work / 'outputs'
            args = command + ['run', str(audio), '--output', str(output), '--chunk-seconds', '4', '--overlap-seconds', '1']
            process = subprocess.Popen(args, cwd=work, env=environment, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, start_new_session=True)
            interrupted = False
            try:
                for line in process.stdout:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if item.get('event') == 'chunk_complete':
                        os.killpg(process.pid, signal.SIGINT)
                        interrupted = True
                        break
                code = process.wait(timeout=30)
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
            if not interrupted or code != 130:
                raise ValueError('The bundled engine did not stop after its first checkpoint')
            job = output / audio.stem
            saved = json.loads((job / 'state.json').read_text())
            checkpoints = {item['file']: (job / item['file']).read_bytes() for item in saved['chunks']}
            assert checkpoints and saved['status'] == 'interrupted'
            subprocess.run(args, cwd=work, env=environment, check=True, capture_output=True, timeout=180)
            complete = json.loads((job / 'state.json').read_text())
            assert complete['status'] == 'complete'
            assert all((job / name).read_bytes() == data for name, data in checkpoints.items())
            assert (job / 'synthetic.txt').read_text().strip()
            assert not list(job.glob('*.partial.*'))
            print('Real bundled MLX transcription, Stop, checkpoint preservation, and Resume passed.')
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    print('Moved app verification passed; minimum macOS ' + info['LSMinimumSystemVersion'] + '.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, default=ROOT / 'LocalTranscribe.app')
    parser.add_argument('--transcribe-fixture', action='store_true', help='Generate local synthetic speech and exercise real GPU stop/resume')
    args = parser.parse_args()
    check(args.app, args.transcribe_fixture)


if __name__ == '__main__':
    main()
