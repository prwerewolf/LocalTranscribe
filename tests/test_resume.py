"""Exercise interrupted jobs and checkpoint integrity without GPU inference."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_transcribe as tool


class ResumeTests(unittest.TestCase):
    def test_interruption_resumes_only_remaining_chunks_and_detects_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "original.mp4"
            source.write_bytes(b"source preserved")
            model = root / "model"
            model.mkdir()
            (model / "config.json").write_text("{}")
            (model / "weights.npz").write_bytes(b"test fixture")
            args = argparse.Namespace(model=model, start_seconds=0, duration_seconds=None,
                    language="en", chunk_seconds=45, overlap_seconds=5, initial_prompt="")
            output = root / "output"
            calls = []

            def decoding(_path, **_kwargs):
                calls.append(1)
                if len(calls) == 2:
                    raise RuntimeError("simulated inference interruption")
                return {"segments": [{"start": 10, "end": 11, "text": " words",
                        "words": [{"start": 10, "end": 11, "word": " words"}]}]}

            fixture = {"source": tool.source_identity(source), "duration_seconds": 100, "audio": [{}]}
            with patch.object(tool, "probe", return_value=fixture), \
                 patch.object(tool.subprocess, "run"), \
                 patch.dict(sys.modules, {"mlx_whisper": types.SimpleNamespace(transcribe=decoding)}), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "simulated inference interruption"):
                    tool.transcribe_file(source, output, args)
                job = output / source.stem
                state = json.loads((job / "state.json").read_text())
                self.assertEqual(state["processed_seconds"], 45)
                self.assertEqual(state["status"], "failed")
                first = job / state["chunks"][0]["file"]
                first_bytes = first.read_bytes()
                self.assertFalse((job / "original.txt").exists())
                self.assertTrue((job / "original.partial.txt").exists())

                complete = tool.transcribe_file(source, output, args)
                self.assertEqual(len(calls), 4)
                self.assertEqual(complete["status"], "complete")
                self.assertEqual(complete["processed_seconds"], 100)
                self.assertEqual(first.read_bytes(), first_bytes)
                self.assertFalse(list(job.glob("*.partial.*")))
                self.assertFalse(list(job.glob("audio-*")))
                self.assertEqual(source.read_bytes(), b"source preserved")

                # Completed export regeneration must not invoke inference again.
                tool.transcribe_file(source, output, args)
                self.assertEqual(len(calls), 4)
                first.write_text("corrupted checkpoint")
                with self.assertRaisesRegex(ValueError, "Checkpoint changed"):
                    tool.transcribe_file(source, output, args)
                self.assertEqual(json.loads((job / "state.json").read_text())["status"], "failed")
                self.assertEqual(len(calls), 4)

    def test_subtitle_hour_rounding_and_lock(self):
        self.assertEqual(tool.timestamp(3599.9996), "01:00:00,000")
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".lock"
            with tool.job_lock(lock):
                with self.assertRaisesRegex(ValueError, "Another process"):
                    with tool.job_lock(lock):
                        pass


if __name__ == "__main__":
    unittest.main()
