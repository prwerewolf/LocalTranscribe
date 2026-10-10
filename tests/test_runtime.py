"""Verify bundled paths and preservation of an existing recording queue."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import local_runtime as runtime
from scripts import bundle_runtime


class RuntimeTests(unittest.TestCase):
    def test_source_layout_keeps_existing_state_and_model_paths(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            root = Path(temporary).resolve()
            with patch.object(runtime, 'ROOT', root):
                self.assertIsNone(runtime.bundle_resources())
                self.assertEqual(runtime.data_directory(), root / '.data')
                self.assertEqual(runtime.model_directory(), root / 'models/whisper-turbo')

    def test_moved_bundle_uses_its_own_runtime_and_external_state(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            root = Path(temporary).resolve()
            resources = root / 'Moved App/LocalTranscribe.app/Contents/Resources'
            python = resources / 'python/bin/python3'
            python.parent.mkdir(parents=True)
            python.write_text('fixture')
            with patch.object(runtime, 'ROOT', resources / 'app'):
                self.assertEqual(runtime.python_executable(), python)
                self.assertEqual(runtime.model_directory(), resources / 'models/whisper-turbo')
                self.assertEqual(runtime.data_directory(), Path.home() / 'Library/Application Support/LocalTranscribe')
                os.environ['LOCALTRANSCRIBE_DATA_DIR'] = str(root / 'private-state')
                runtime.configure_environment()
                self.assertEqual(runtime.data_directory(), root / 'private-state')
                self.assertEqual(os.environ['PYTHONHOME'], str(resources / 'python'))
                self.assertTrue(os.environ['PATH'].startswith(str(resources / 'tools/bin')))
                self.assertEqual(os.environ['NUMBA_CACHE_DIR'], str(root / 'private-state/cache/numba'))
                self.assertFalse((resources / '.data').exists())

    def test_queue_migration_preserves_source_and_never_overwrites_destination(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {}, clear=True):
            project = Path(temporary)
            resources = project / 'LocalTranscribe.app/Contents/Resources'
            python = resources / 'python/bin/python3'
            python.parent.mkdir(parents=True)
            python.write_text('fixture')
            (project / 'app.py').write_text('fixture')
            legacy = project / '.data/queue.json'
            legacy.parent.mkdir()
            saved = {'output': str(project / 'outputs'), 'jobs': [{'id': 'existing', 'status': 'Stopped'}]}
            legacy.write_text(json.dumps(saved))
            original = legacy.read_bytes()
            destination = project / 'application-support'
            destination.mkdir()
            with patch.object(runtime, 'ROOT', resources / 'app'):
                self.assertTrue(runtime.migrate_legacy_queue(destination))
                self.assertEqual(json.loads((destination / 'queue.json').read_text()), saved)
                self.assertEqual(legacy.read_bytes(), original)
                legacy.write_text(json.dumps({**saved, 'jobs': []}))
                self.assertFalse(runtime.migrate_legacy_queue(destination))
                self.assertEqual(json.loads((destination / 'queue.json').read_text()), saved)
            self.assertNotEqual(legacy.read_bytes(), original)

    def test_universal_library_headers_are_not_dependencies(self):
        text = ('binary (architecture arm64):\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)\n'
                'binary (architecture x86_64):\n\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0, current version 1.0.0)\n')
        with patch.object(bundle_runtime, 'output', return_value=text):
            self.assertEqual(bundle_runtime.dependencies(Path('binary')), ['/usr/lib/libSystem.B.dylib'])
        with patch.object(bundle_runtime, 'output', return_value='binary (architecture arm64):\nbinary (architecture x86_64):\n'):
            self.assertIsNone(bundle_runtime.install_id(Path('binary')))


if __name__ == '__main__':
    unittest.main()
