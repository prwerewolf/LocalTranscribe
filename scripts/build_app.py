"""Build a movable Mac app containing the existing offline transcription engine."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import urllib.request
import json
import tempfile
import bundle_runtime

ROOT = Path(__file__).resolve().parents[1]


def build(contents, compiler, python):
    resources = contents / 'Resources'
    (contents / 'MacOS').mkdir(parents=True)
    resources.mkdir()
    info = plistlib.loads((ROOT / 'native/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != 'org.localtranscribe.app':
        raise ValueError('App identifier must be the neutral project identifier')
    shutil.copy2(ROOT / 'native/Info.plist', contents / 'Info.plist')
    subprocess.run(compiler + ['-O', '-target', 'arm64-apple-macosx14.0', 'native/main.swift',
                   '-o', str(contents / 'MacOS/LocalTranscribe'), '-framework', 'Cocoa', '-framework', 'WebKit'],
                   cwd=ROOT, check=True)
    shutil.copy2(ROOT / 'assets/AppIcon.icns', resources / 'AppIcon.icns')
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY.md'):
        shutil.copy2(ROOT / name, resources / name)
    application = resources / 'app'
    application.mkdir()
    for name in ('app.py', 'local_transcribe.py', 'local_runtime.py'):
        shutil.copy2(ROOT / name, application / name)
    shutil.copytree(ROOT / 'ui', application / 'ui')
    print('Bundling the existing Python runtime and dependencies…', flush=True)
    python_info = bundle_runtime.copy_python(python, resources / 'python')
    print('Bundling FFmpeg and the existing Whisper model…', flush=True)
    ffmpeg = bundle_runtime.copy_tools(resources)
    model = ROOT / 'models/whisper-turbo'
    if not (model / 'config.json').is_file() or not any((model / name).is_file() for name in ('weights.npz', 'weights.safetensors')):
        raise ValueError('Run setup first to download the pinned local Whisper model')
    destination = resources / 'models/whisper-turbo'
    destination.mkdir(parents=True)
    for name in ('config.json', 'weights.npz', 'weights.safetensors', 'model-source.json', 'README.md'):
        if (model / name).is_file():
            shutil.copy2(model / name, destination / name)
    manifest = {'app_version': info['CFBundleShortVersionString'], 'python': python_info,
                'ffmpeg': ffmpeg, 'model': json.loads((model / 'model-source.json').read_text())}
    (resources / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    launcher = resources / 'local-transcribe'
    launcher.write_text('''#!/bin/sh
bundle_resources=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
export PYTHONHOME="$bundle_resources/python"
export PYTHONDONTWRITEBYTECODE=1
unset PYTHONPATH
exec "$bundle_resources/python/bin/python3" -s "$bundle_resources/app/local_transcribe.py" "$@"
''')
    launcher.chmod(0o755)
    print('Relocating and signing native libraries…', flush=True)
    native_files = bundle_runtime.relocate_libraries(contents)
    info['LSMinimumSystemVersion'] = bundle_runtime.minimum_macos(native_files, info['LSMinimumSystemVersion'])
    (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
    manifest['minimum_macos'] = info['LSMinimumSystemVersion']
    (resources / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    bundle_runtime.sign(contents, native_files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Type-check Swift without rebuilding the app bundle')
    parser.add_argument('--python', type=Path, default=ROOT / '.venv/bin/python', help='Existing transcription environment to bundle')
    args = parser.parse_args()
    if sys.platform != 'darwin' or not shutil.which('xcrun'):
        raise SystemExit('macOS and Xcode Command Line Tools are required')
    cache = ROOT / '.build/module-cache'
    cache.mkdir(parents=True, exist_ok=True)
    compiler = ['xcrun', 'swiftc', '-swift-version', '5', '-module-cache-path', str(cache),
                '-file-prefix-map', str(ROOT) + '=.', '-debug-prefix-map', str(ROOT) + '=.']
    if args.check_only:
        subprocess.run(compiler + ['-typecheck', 'native/main.swift'], cwd=ROOT, check=True)
        print('Native source check passed.')
        return
    if not args.python.is_file():
        raise SystemExit('Run setup first to install the pinned transcription dependencies')
    try:
        with urllib.request.urlopen('http://127.0.0.1:8789/health', timeout=1) as response:
            state = json.load(response)
        if state.get('app') == 'LocalTranscribe':
            raise SystemExit('Close LocalTranscribe before rebuilding its app bundle.')
    except OSError:
        pass
    with tempfile.TemporaryDirectory(prefix='app-build-', dir=ROOT / '.build') as temporary:
        staged = Path(temporary) / 'LocalTranscribe.app'
        build(staged / 'Contents', compiler, args.python)
        target = ROOT / 'LocalTranscribe.app'
        previous = ROOT / '.build/previous-LocalTranscribe.app'
        if previous.exists():
            shutil.rmtree(previous)
        if target.exists():
            target.replace(previous)
        staged.replace(target)
    print('Self-contained LocalTranscribe.app built and verified. It can be moved into Applications.')


if __name__ == '__main__':
    main()
