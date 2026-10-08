"""Build the native wrapper beside the local project runtime."""
import argparse
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import urllib.request
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true', help='Type-check Swift without changing the app bundle')
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
    try:
        with urllib.request.urlopen('http://127.0.0.1:8789/health', timeout=1) as response:
            state = json.load(response)
        if state.get('root') == str(ROOT):
            raise SystemExit('Close LocalTranscribe before rebuilding its app bundle.')
    except OSError:
        pass
    info = plistlib.loads((ROOT / 'native/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != 'org.localtranscribe.app':
        raise SystemExit('App identifier must be the neutral project identifier')
    binary = ROOT / '.build/LocalTranscribe'
    subprocess.run(compiler + ['-O', '-target', 'arm64-apple-macosx14.0', 'native/main.swift',
                   '-o', str(binary), '-framework', 'Cocoa', '-framework', 'WebKit'], cwd=ROOT, check=True)
    contents = ROOT / 'LocalTranscribe.app/Contents'
    (contents / 'MacOS').mkdir(parents=True, exist_ok=True)
    (contents / 'Resources').mkdir(exist_ok=True)
    shutil.copy2(binary, contents / 'MacOS/LocalTranscribe')
    shutil.copy2(ROOT / 'native/Info.plist', contents / 'Info.plist')
    shutil.copy2(ROOT / 'assets/AppIcon.icns', contents / 'Resources/AppIcon.icns')
    for name in ('LICENSE', 'NOTICE', 'THIRD_PARTY.md'):
        shutil.copy2(ROOT / name, contents / 'Resources' / name)
    subprocess.run(['codesign', '--force', '--sign', '-', str(ROOT / 'LocalTranscribe.app')], check=True)
    subprocess.run(['codesign', '--verify', '--deep', '--strict', str(ROOT / 'LocalTranscribe.app')], check=True)
    print('LocalTranscribe.app built and verified.')


if __name__ == '__main__':
    main()
