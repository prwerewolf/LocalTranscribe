"""Check tracked release files without printing matched private data."""
import argparse
import json
from pathlib import Path
import plistlib
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BLOCKED_PREFIXES = ('.venv/', 'models/', 'hf-cache/', 'uv-cache/', '.data/', '.build/',
                    'samples/', 'transcripts/', 'validation/', 'drafts/', 'LocalTranscribe.app/')
PATTERNS = [
    ('personal home path', re.compile(rb'/(?:Users|home)/[^/\s]+/')),
    ('private temporary path', re.compile(rb'/private/(?:tmp|var)/')),
    ('private key', re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')),
    ('embedded credential', re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[A-Z0-9]{16})\b')),
]
PNG_METADATA = {b'tEXt', b'zTXt', b'iTXt', b'eXIf'}


def png_metadata(data):
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        return False
    cursor = 8
    while cursor + 12 <= len(data):
        size = struct.unpack('>I', data[cursor:cursor + 4])[0]
        kind = data[cursor + 4:cursor + 8]
        if kind in PNG_METADATA:
            return True
        cursor += size + 12
    return False


def findings(name, data, denied=()):
    errors = []
    filename = Path(name).name
    if name.startswith(BLOCKED_PREFIXES) or filename == '.DS_Store' or filename.startswith('.env') \
       or filename.endswith('.log') or filename.startswith(('application-', 'app-validation-', '.private-')) \
       or name in ('validation.md', 'assets/icon-generation.json', 'assets/icon-prompt.txt'):
        errors.append('private/local-only file')
    for label, pattern in PATTERNS:
        if pattern.search(data):
            errors.append(label)
    for term in denied:
        if term.encode().lower() in data.lower() or term.lower() in name.lower():
            errors.append('private blocked term')
    if png_metadata(data):
        errors.append('descriptive image metadata')
    if name.endswith('.icns') and data.startswith(b'icns'):
        cursor = 8
        while cursor + 8 <= len(data):
            size = struct.unpack('>I', data[cursor + 4:cursor + 8])[0]
            if size < 8:
                errors.append('invalid icon container')
                break
            if png_metadata(data[cursor + 8:cursor + size]):
                errors.append('descriptive icon metadata')
            cursor += size
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--denylist', type=Path, help='Optional private JSON list of blocked terms; never commit it')
    args = parser.parse_args()
    denied = json.loads(args.denylist.read_text()) if args.denylist else []
    result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, check=True, capture_output=True)
    names = [name for name in result.stdout.decode().split('\0') if name]
    if not names:
        raise SystemExit('No tracked release files to check')
    failures = []
    for name in names:
        data = (ROOT / name).read_bytes()
        for label in findings(name, data, denied):
            failures.append(f'{name}: {label}')
        if name == 'native/Info.plist' and plistlib.loads(data).get('CFBundleIdentifier') != 'org.localtranscribe.app':
            failures.append(f'{name}: non-neutral app identifier')
    if failures:
        raise SystemExit('\n'.join(failures))
    print(f'Public-file privacy check passed ({len(names)} files).')


if __name__ == '__main__':
    main()
