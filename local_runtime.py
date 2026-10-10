"""Locate read-only bundled assets and writable local state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def bundle_resources():
    candidate = ROOT.parent
    if ROOT.name == 'app' and candidate.name == 'Resources' and (candidate / 'python/bin/python3').is_file():
        return candidate
    return None


def data_directory():
    override = os.environ.get('LOCALTRANSCRIBE_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if bundle_resources():
        return Path.home() / 'Library/Application Support/LocalTranscribe'
    return ROOT / '.data'


def model_directory():
    return (bundle_resources() or ROOT) / 'models/whisper-turbo'


def python_executable():
    resources = bundle_resources()
    if resources:
        return resources / 'python/bin/python3'
    environment = ROOT / '.venv/bin/python'
    return environment if environment.is_file() else Path(sys.executable)


def configure_environment():
    resources = bundle_resources()
    if resources:
        os.environ['PATH'] = str(resources / 'tools/bin') + os.pathsep + os.environ.get('PATH', '/usr/bin:/bin')
        os.environ['PYTHONHOME'] = str(resources / 'python')
        os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
        cache = data_directory() / 'cache'
        os.environ['HF_HOME'] = str(cache / 'huggingface')
        os.environ['NUMBA_CACHE_DIR'] = str(cache / 'numba')
        os.environ['XDG_CACHE_HOME'] = str(cache)


def migrate_legacy_queue(destination):
    """Copy a source-build queue on first launch; never overwrite either copy."""
    resources = bundle_resources()
    if not resources or os.environ.get('LOCALTRANSCRIBE_DATA_DIR'):
        return False
    project = resources.parents[2]
    legacy = project / '.data/queue.json'
    target = destination / 'queue.json'
    if target.exists() or not legacy.is_file() or not (project / 'app.py').is_file():
        return False
    saved = json.loads(legacy.read_text())
    if not isinstance(saved, dict) or not isinstance(saved.get('jobs'), list) or not isinstance(saved.get('output'), str):
        raise ValueError('The previous recording queue could not be read. Its original copy is preserved.')
    try:
        with target.open('x', encoding='utf-8') as handle:
            json.dump(saved, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
    except FileExistsError:
        return False
    return True
