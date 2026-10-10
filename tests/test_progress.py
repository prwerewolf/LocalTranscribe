"""Check honest estimates and reporting-only adaptation of the pinned engine."""
import types
import unittest

from transcription_progress import ProgressReporter, observe_windows


class ProgressTests(unittest.TestCase):
    def reporter(self, total=3600, resumed=0):
        clock = [0.0]
        events = []
        progress = ProgressReporter(lambda **data: events.append(data), clock=lambda: clock[0])
        progress.configure(total, resumed)
        progress.stage('transcribing')
        return progress, clock, events

    def test_estimate_uses_measured_windows_and_excludes_initial_model_load(self):
        progress, clock, events = self.reporter()
        clock[0] = 100
        progress.advance(30)
        self.assertIsNone(events[-1]['eta_seconds'])
        clock[0] = 102
        progress.advance(60)
        self.assertIsNone(events[-1]['eta_seconds'])
        clock[0] = 104
        progress.advance(90)
        self.assertAlmostEqual(events[-1]['eta_seconds'], 234)
        self.assertEqual(events[-1]['saved_percent'], 0)
        self.assertEqual(events[-1]['percent'], 2.5)

    def test_resume_does_not_reuse_another_runs_speed_or_save_live_progress(self):
        progress, clock, events = self.reporter(resumed=1800)
        self.assertIsNone(events[-1]['eta_seconds'])
        self.assertEqual(events[-1]['saved_percent'], 50)
        for index, audio in enumerate((1830, 1860, 1890)):
            clock[0] = 10 + index * 2
            progress.advance(audio)
        self.assertEqual(events[-1]['saved_percent'], 50)
        self.assertGreater(events[-1]['percent'], 50)
        self.assertAlmostEqual(events[-1]['eta_seconds'], 114)

    def test_preparation_delays_do_not_pollute_inference_rate(self):
        progress, clock, events = self.reporter()
        for index, audio in enumerate((30, 60, 90)):
            clock[0] = 10 + index * 2
            progress.advance(audio)
        progress.stage('preparing_audio')
        clock[0] = 1000
        progress.stage('transcribing')
        clock[0] = 1002
        progress.advance(120)
        clock[0] = 1004
        progress.advance(150)
        self.assertAlmostEqual(events[-1]['seconds_per_audio'], 2 / 30)

    def test_short_chunks_provide_estimates_from_actual_completed_work(self):
        progress, clock, events = self.reporter(total=20)
        progress.stage('saving_progress')
        progress.commit(4, 4, 2)
        self.assertIsNone(events[-1]['eta_seconds'])
        progress.commit(8, 4, 2)
        self.assertEqual(events[-1]['eta_seconds'], 6)
        self.assertEqual(events[-1]['saved_percent'], 40)

    def test_finishing_never_claims_complete_or_zero_time_before_exports_finish(self):
        progress, clock, events = self.reporter(total=100)
        progress.advance(100)
        self.assertEqual(events[-1]['percent'], 99)
        progress.stage('finishing')
        self.assertIsNone(events[-1]['eta_seconds'])
        self.assertEqual(events[-1]['saved_percent'], 0)

    def test_window_observer_preserves_options_result_and_namespace_on_stop(self):
        calls, bars, fractions = [], [], []

        class Bar:
            def __init__(self, **kwargs):
                bars.append(kwargs)

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def update(self, _amount):
                pass

        original = types.SimpleNamespace(tqdm=Bar)
        namespace = {'tqdm': original, 'calls': calls}
        exec('''def transcribe(audio, **options):
    calls.append((audio, options))
    with tqdm.tqdm(total=100, disable=True) as bar:
        bar.update(30)
        bar.update(40)
        if audio == "stop":
            raise KeyboardInterrupt
    return {"text": "unchanged"}
''', namespace)
        decode = namespace['transcribe']
        options = {'verbose': None, 'word_timestamps': True, 'condition_on_previous_text': False}
        with observe_windows(decode, fractions.append):
            result = decode('fixture', **options)
        self.assertEqual(result, {'text': 'unchanged'})
        self.assertEqual(calls[0], ('fixture', options))
        self.assertEqual(bars[0], {'total': 100, 'disable': True})
        self.assertEqual(fractions, [0.3, 0.7])
        self.assertIs(namespace['tqdm'], original)
        with self.assertRaises(KeyboardInterrupt):
            with observe_windows(decode, fractions.append):
                decode('stop', **options)
        self.assertIs(namespace['tqdm'], original)


if __name__ == '__main__':
    unittest.main()
