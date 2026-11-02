"""Verify setup's platform checks without installing dependencies."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SetupTests(unittest.TestCase):
    def run_setup(self, version):
        with tempfile.TemporaryDirectory() as temporary:
            tools = Path(temporary)
            stubs = {
                'uname': 'if [ "$1" = -s ]; then echo Darwin; else echo arm64; fi',
                'sw_vers': f'echo {version}',
                'uv': 'echo dependency installation reached; exit 3',
                'ffmpeg': 'exit 0', 'ffprobe': 'exit 0', 'xcrun': 'exit 0',
            }
            for name, body in stubs.items():
                (tools / name).write_text('#!/bin/sh\n' + body + '\n')
                (tools / name).chmod(0o755)
            return subprocess.run(['/bin/bash', str(ROOT / 'setup.command')],
                                  env={'PATH': f'{tools}:/usr/bin:/bin'},
                                  capture_output=True, text=True, timeout=30)

    def test_supported_macos_versions_reach_dependency_installation(self):
        for version in ('14.0', '15.5', '26.0', '26.2'):
            with self.subTest(version=version):
                result = self.run_setup(version)
                self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
                self.assertIn('dependency installation reached', result.stdout)

    def test_unsupported_macos_stops_before_installing(self):
        result = self.run_setup('13.7')
        self.assertEqual(result.returncode, 1)
        self.assertIn('requires macOS 14 or later', result.stdout)
        self.assertNotIn('dependency installation reached', result.stdout)


if __name__ == '__main__':
    unittest.main()
