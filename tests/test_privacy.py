import importlib.util
from pathlib import Path
import struct
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/check_release.py'
spec = importlib.util.spec_from_file_location('privacy_check', path)
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class PrivacyTests(unittest.TestCase):
    def test_local_data_and_user_paths_are_rejected_without_echoing_values(self):
        private_path = '/' + 'Users/' + 'synthetic_account/' + 'recording.wav'
        self.assertIn('personal home path', privacy.findings('example.py', private_path.encode()))
        self.assertIn('private/local-only file', privacy.findings('.data/queue.json', b'{}'))
        self.assertIn('private/local-only file', privacy.findings('application-local.json', b'{}'))
        self.assertEqual(privacy.findings('app.py', b'/usr/bin/caffeinate'), [])

    def test_image_metadata_and_private_terms_are_detected(self):
        image = b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 4) + b'tEXt' + b'test' + b'\0' * 4
        self.assertIn('descriptive image metadata', privacy.findings('assets/icon.png', image))
        self.assertIn('private blocked term', privacy.findings('README.md', b'a synthetic secret marker', ['secret marker']))


if __name__ == '__main__':
    unittest.main()
