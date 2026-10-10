"""Observe completed inference windows without changing decoding or checkpoints."""
from collections import deque
from contextlib import contextmanager
import math
import time


class ProgressReporter:
    def __init__(self, emit, clock=time.monotonic):
        self.emit = emit
        self.clock = clock
        self.phase = 'checking_recording'
        self.total = None
        self.processed = 0.0
        self.saved = 0.0
        self.rates = deque(maxlen=6)
        self.previous = None
        self.window_samples = 0
        self.send()

    def configure(self, total, resumed=0):
        self.total = float(total)
        self.processed = self.saved = float(resumed)
        self.previous = None
        self.send()

    def stage(self, phase):
        self.phase = phase
        self.previous = None
        if phase == 'transcribing':
            self.window_samples = 0
        self.send()

    def advance(self, processed):
        if self.total is None or not math.isfinite(processed):
            return
        processed = min(self.total, max(self.processed, float(processed)))
        now = self.clock()
        if self.previous:
            audio = processed - self.previous[0]
            elapsed = now - self.previous[1]
            if audio > 0 and elapsed > 0:
                self.rates.append((audio, elapsed))
                self.window_samples += 1
        if self.previous is None or processed > self.previous[0]:
            self.previous = (processed, now)
        self.processed = processed
        self.send()

    def commit(self, processed, chunk_audio, elapsed):
        self.processed = max(self.processed, float(processed))
        self.saved = float(processed)
        # Short chunks and all-silence windows may provide no intermediate
        # measurements. Their actual extraction/inference time remains useful.
        if self.window_samples < 2 and chunk_audio > 0 and elapsed > 0:
            self.rates.append((float(chunk_audio), float(elapsed)))
        self.previous = None
        self.send()

    def send(self):
        total = self.total
        remaining = max(0, total - self.processed) if total is not None else None
        rate = interval = eta = None
        # Do not estimate from the initial model load or a single measurement.
        if len(self.rates) >= 2 and sum(audio for audio, _ in self.rates) >= 5:
            audio = sum(audio for audio, _ in self.rates)
            elapsed = sum(elapsed for _, elapsed in self.rates)
            rate = elapsed / audio
            interval = max(elapsed for _, elapsed in self.rates)
            if remaining and self.phase in ('transcribing', 'preparing_audio', 'saving_progress'):
                eta = max(1, remaining * rate)
        self.emit(phase=self.phase,
                  percent=min(99.0, 100 * self.processed / total) if total else None,
                  saved_percent=100 * self.saved / total if total else None,
                  processed_seconds=self.processed, total_seconds=total,
                  eta_seconds=eta, seconds_per_audio=rate, estimate_interval_seconds=interval)


@contextmanager
def observe_windows(transcribe, callback):
    """Adapt MLX Whisper's existing tqdm reporting, leaving options unchanged.

    The pinned engine uses a module-local tqdm namespace. Substitute only that
    reporting namespace during this call, then restore it even on Stop/error.
    Other implementations safely fall back to stage/checkpoint progress.
    """
    namespace = getattr(transcribe, '__globals__', {})
    original = namespace.get('tqdm')
    factory = getattr(original, 'tqdm', None)
    if factory is None:
        yield
        return

    class ObservedBar:
        def __init__(self, *args, **kwargs):
            self.bar = factory(*args, **kwargs)
            self.total = kwargs.get('total')
            self.completed = 0

        def __enter__(self):
            self.bar.__enter__()
            return self

        def __exit__(self, *args):
            return self.bar.__exit__(*args)

        def __getattr__(self, name):
            return getattr(self.bar, name)

        def update(self, amount=1):
            result = self.bar.update(amount)
            self.completed += amount
            if self.total and self.completed >= 0:
                callback(min(1.0, self.completed / self.total))
            return result

    class ReportingNamespace:
        tqdm = ObservedBar

        def __getattr__(self, name):
            return getattr(original, name)

    namespace['tqdm'] = ReportingNamespace()
    try:
        yield
    finally:
        namespace['tqdm'] = original
