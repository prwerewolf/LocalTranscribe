"""Exercise Stop and worker selection without transcribing personal recordings."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest.mock import patch


class ControllerTests(unittest.TestCase):
    def test_interruption_reports_a_saved_checkpoint_even_before_chunk_complete_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / 'state'
            state.mkdir()
            saved = {'output': str(root / 'outputs'), 'jobs': [{'id': 'fixture', 'path': str(root / 'fixture.wav'),
                     'name': 'fixture.wav', 'duration': 100, 'status': 'Ready', 'progress': 0,
                     'error': None, 'output_folder': None}]}
            (state / 'queue.json').write_text(json.dumps(saved))
            with patch.dict(os.environ, {'LOCALTRANSCRIBE_DATA_DIR': str(state)}):
                spec = importlib.util.spec_from_file_location('controller_fixture', Path(__file__).resolve().parents[1] / 'app.py')
                app = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(app)

                class Process:
                    stdout = iter([json.dumps({'event': 'progress', 'phase': 'saving_progress',
                                              'percent': 50, 'saved_percent': 0, 'total_seconds': 100}) + '\n',
                                   json.dumps({'event': 'interrupted', 'processed_seconds': 50}) + '\n'])

                    def wait(self):
                        return 130

                with patch.object(app.subprocess, 'Popen', return_value=Process()):
                    app.controller.start(['fixture'])
                    app.controller.worker.join(5)
                    self.assertFalse(app.controller.worker.is_alive())
                result = app.controller.snapshot()['jobs'][0]
                self.assertEqual(result['status'], 'Stopped')
                self.assertEqual(result['progress'], 50)
                self.assertNotIn('eta_seconds', result)

    def test_stop_preserves_progress_and_uses_selected_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = root / 'state'
            state.mkdir()
            saved = {'output': str(root / 'outputs'), 'jobs': [{'id': 'fixture', 'path': str(root / 'fixture.wav'),
                     'name': 'fixture.wav', 'status': 'Ready', 'progress': 0, 'error': None, 'output_folder': None}]}
            (state / 'queue.json').write_text(json.dumps(saved))
            with patch.dict(os.environ, {'LOCALTRANSCRIBE_DATA_DIR': str(state)}):
                spec = importlib.util.spec_from_file_location('controller_fixture', Path(__file__).resolve().parents[1] / 'app.py')
                app = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(app)
                controller = app.controller
                ready, stopped = threading.Event(), threading.Event()

                class Process:
                    pid = 123456

                    @property
                    def stdout(self):
                        yield json.dumps({'event': 'chunk_complete', 'percent': 50}) + '\n'
                        yield json.dumps({'event': 'progress', 'phase': 'transcribing', 'percent': 70,
                                         'saved_percent': 50, 'eta_seconds': 30,
                                         'seconds_per_audio': 0.5, 'estimate_interval_seconds': 2,
                                         'total_seconds': 100}) + '\n'
                        ready.set()
                        if not stopped.wait(5):
                            raise RuntimeError('Stop was not delivered')

                    def wait(self):
                        return 130

                    def poll(self):
                        return None

                bundled_python = root / 'Moved App/Contents/Resources/python/bin/python3'
                with patch.object(app.runtime, 'python_executable', return_value=bundled_python), \
                     patch.object(app.subprocess, 'Popen', return_value=Process()) as launch, \
                     patch.object(app.os, 'killpg', side_effect=lambda *_args: stopped.set()) as stop:
                    controller.start(['fixture'])
                    self.assertTrue(ready.wait(5))
                    live = controller.snapshot()['jobs'][0]
                    self.assertEqual(live['live_progress'], 70)
                    self.assertEqual(live['progress'], 50)
                    self.assertGreater(live['eta_seconds'], 0)
                    with patch.object(app.time, 'monotonic', return_value=controller.live['fixture']['updated_at'] + 20):
                        stalled = controller.snapshot()['jobs'][0]
                        self.assertIsNone(stalled['eta_seconds'])
                        self.assertEqual(stalled['live_progress'], 70)
                    self.assertNotIn('eta_seconds', json.loads((state / 'queue.json').read_text())['jobs'][0])
                    controller.cancel()
                    controller.worker.join(5)
                    self.assertFalse(controller.worker.is_alive())
                    self.assertEqual(launch.call_args.args[0][2], str(bundled_python))
                    stop.assert_called_once_with(Process.pid, signal.SIGINT)
                result = json.loads((state / 'queue.json').read_text())
                self.assertEqual(result['jobs'][0]['status'], 'Stopped')
                self.assertEqual(result['jobs'][0]['progress'], 50)
                self.assertFalse(controller.snapshot()['active'])
                self.assertIsNone(controller.snapshot()['batch'])


if __name__ == '__main__':
    unittest.main()
