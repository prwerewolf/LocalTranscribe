"""Copy the existing Python environment and relocate its native dependencies."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

MACHO_MAGICS = {b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca'}
SYSTEM_PREFIXES = ('/usr/lib/', '/System/Library/')


def output(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'{command[0]} failed with status {result.returncode}')
    return result.stdout


def is_macho(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open('rb') as handle:
        return handle.read(4) in MACHO_MAGICS


def copy_python(python, destination):
    description = json.loads(output([str(python), '-I', '-c',
        'import json, sys, sysconfig; print(json.dumps({"base": sys.base_prefix, '
        '"stdlib": sysconfig.get_path("stdlib"), "site": sysconfig.get_path("purelib"), '
        '"executable": sys._base_executable, "version": sys.version.split()[0], '
        '"minor": "%s.%s" % sys.version_info[:2]}))']))
    minor = description['minor']
    library = destination / 'lib' / ('python' + minor)
    shutil.copytree(description['stdlib'], library,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'site-packages'), symlinks=False)
    shutil.copytree(description['site'], library / 'site-packages',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc', 'uv_cache.json', 'direct_url.json'),
                    symlinks=False)
    binary = destination / 'bin' / ('python' + minor)
    binary.parent.mkdir(parents=True)
    shutil.copy2(Path(description['executable']).resolve(), binary)
    (binary.parent / 'python3').symlink_to(binary.name)
    for path in (Path(description['base']) / 'lib').glob('libpython*.dylib'):
        if not path.is_symlink():
            shutil.copy2(path, destination / 'lib' / path.name)
    return {'version': description['version'], 'executable': 'bin/python3'}


def dependencies(path):
    lines = output(['otool', '-L', str(path)]).splitlines()
    # Universal binaries have an extra unindented header for each architecture.
    return list(dict.fromkeys(line.strip().split(' (compatibility version', 1)[0]
                              for line in lines if line.startswith('\t')))


def install_id(path):
    lines = output(['otool', '-D', str(path)]).splitlines()
    return next((line.strip() for line in lines if line.strip() and not line.rstrip().endswith(':')), None)


def rpaths(path):
    lines = output(['otool', '-l', str(path)]).splitlines()
    return list(dict.fromkeys(lines[index + 2].strip().split(' (offset', 1)[0].removeprefix('path ')
                             for index, line in enumerate(lines) if line.strip() == 'cmd LC_RPATH'))


def relocate_libraries(contents):
    """Replace machine-local absolute dylib links with bundle-relative links."""
    frameworks = contents / 'Frameworks'
    frameworks.mkdir()
    pending = [path for path in contents.rglob('*') if is_macho(path)]
    originals, names, visited = {}, {}, set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        own_id = install_id(path)
        changes = []
        for reference in dependencies(path):
            if reference == own_id or not reference.startswith('/') or reference.startswith(SYSTEM_PREFIXES):
                continue
            source = Path(reference).resolve(strict=True)
            if source not in originals:
                name = source.name
                if name in names and names[name] != source:
                    name = source.stem + '-' + hashlib.sha256(source.read_bytes()).hexdigest()[:12] + source.suffix
                names[name] = source
                target = frameworks / name
                shutil.copy2(source, target)
                originals[source] = target
                pending.append(target)
            replacement = '@loader_path/' + os.path.relpath(originals[source], path.parent)
            changes.extend(['-change', reference, replacement])
        if own_id:
            changes.extend(['-id', '@rpath/' + path.name])
        for value in rpaths(path):
            if value.startswith('/') and not value.startswith(SYSTEM_PREFIXES):
                changes.extend(['-delete_rpath', value])
        if changes:
            output(['install_name_tool', *changes, str(path)])
    for path in visited:
        for reference in dependencies(path):
            if reference.startswith('/') and not reference.startswith(SYSTEM_PREFIXES):
                raise ValueError(f'Unbundled native dependency in {path.name}')
    return sorted(visited)


def copy_tools(resources):
    destination = resources / 'tools/bin'
    destination.mkdir(parents=True)
    for name in ('ffmpeg', 'ffprobe'):
        supplied = shutil.which(name)
        if not supplied:
            raise ValueError(f'{name} is required to build the app')
        shutil.copy2(Path(supplied).resolve(), destination / name)
    notices = resources / 'ThirdPartyNotices'
    notices.mkdir()
    version = output([str(destination / 'ffmpeg'), '-version'])
    (notices / 'FFmpeg.txt').write_text(version + '\n' + output([str(destination / 'ffmpeg'), '-L']))
    installations = set()
    for name in ('ffmpeg', 'ffprobe'):
        supplied = Path(shutil.which(name)).resolve()
        for reference in [str(supplied), *dependencies(destination / name)]:
            parts = Path(reference).parts
            if 'Cellar' in parts:
                index = parts.index('Cellar')
                installations.add(Path(*parts[:index + 3]))
    for installation in installations:
        component = installation.parent.name + '-' + installation.name
        for source in installation.rglob('*'):
            if source.is_file() and (source.name.upper().startswith(('LICENSE', 'COPYING', 'NOTICE'))
                                     or source.parent.name == '.brew'):
                target = notices / component / source.relative_to(installation)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    return version.splitlines()[0]


def minimum_macos(native_files, baseline='14.0'):
    minimum = tuple(int(part) for part in baseline.split('.'))
    for path in native_files:
        lines = output(['otool', '-arch', 'arm64', '-l', str(path)]).splitlines()
        for index, line in enumerate(lines):
            if line.strip() in ('cmd LC_BUILD_VERSION', 'cmd LC_VERSION_MIN_MACOSX'):
                for value in lines[index + 1:index + 6]:
                    fields = value.split()
                    if len(fields) == 2 and fields[0] in ('minos', 'version'):
                        version = tuple(int(part) for part in fields[1].split('.'))
                        minimum = max(minimum, version)
                        break
    return '.'.join(str(part) for part in minimum)


def sign(contents, native_files):
    for path in sorted(native_files, key=lambda item: len(item.parts), reverse=True):
        if path == contents / 'MacOS/LocalTranscribe':
            continue
        output(['codesign', '--force', '--sign', '-', str(path)])
    output(['codesign', '--force', '--sign', '-', str(contents.parent)])
    output(['codesign', '--verify', '--deep', '--strict', str(contents.parent)])
