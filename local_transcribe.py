#!/usr/bin/env python3
"""Offline, resumable file transcription using Whisper on Apple Silicon."""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
import local_runtime as runtime
from transcription_progress import ProgressReporter, observe_windows

VERSION = "0.3.0"
# Keep existing checkpoint settings comparable across packaging-only releases.
CHECKPOINT_VERSION = "0.1.1"
ROOT = Path(__file__).resolve().parent
MEDIA_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".m4a", ".mp3", ".wav", ".flac", ".aac"}


def now():
    return datetime.now(timezone.utc).isoformat()


def event(kind, **fields):
    print(json.dumps({"event": kind, "time": now(), **fields}, ensure_ascii=False), flush=True)


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def write_atomic(path, content):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def source_identity(path):
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=index,codec_type,codec_name,sample_rate,channels,duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    audio = [s for s in data["streams"] if s.get("codec_type") == "audio"]
    if not audio:
        raise ValueError(f"No audio track: {path}")
    duration = float(audio[0].get("duration", data["format"]["duration"]))
    if duration <= 0:
        raise ValueError(f"Empty audio: {path}")
    return {"source": source_identity(path), "duration_seconds": duration, "audio": audio}


def timestamp(seconds, separator=","):
    milliseconds = max(0, round(seconds * 1000))
    whole, fraction = divmod(milliseconds, 1000)
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{fraction:03d}"


def owned_segments(result, extraction_start, owned_start, owned_end):
    """Assign overlapping audio to one chunk, keeping word timestamps global."""
    segments = []
    for source in result.get("segments", []):
        words = []
        for original in source.get("words", []):
            start = float(original["start"]) + extraction_start
            end = float(original["end"]) + extraction_start
            if owned_start <= (start + end) / 2 < owned_end:
                words.append({**original, "start": max(owned_start, start), "end": min(owned_end, end)})
        if words:
            start, end = words[0]["start"], words[-1]["end"]
            text = "".join(word["word"] for word in words).strip()
        elif not source.get("words"):
            start = float(source["start"]) + extraction_start
            end = float(source["end"]) + extraction_start
            if not owned_start <= (start + end) / 2 < owned_end:
                continue
            start, end = max(owned_start, start), min(owned_end, end)
            text = source.get("text", "").strip()
        else:
            continue
        if text and end > start:
            segments.append({"start": start, "end": end, "text": text, "words": words,
                             "avg_logprob": source.get("avg_logprob"),
                             "compression_ratio": source.get("compression_ratio"),
                             "no_speech_prob": source.get("no_speech_prob")})
    return segments


def combine(records):
    segments = []
    for record in records:
        for original in record["segments"]:
            segment = dict(original)
            if segments:
                previous = segments[-1]
                # Suppress exact repeat segments whose timing agrees at a seam.
                if segment["text"] == previous["text"] and abs(segment["start"] - previous["start"]) < 0.5:
                    continue
                segment["start"] = max(segment["start"], previous["end"])
            if segment["end"] > segment["start"]:
                segments.append(segment)
    return segments


def export(job, state, records, complete):
    segments = combine(records)
    suffix = "" if complete else ".partial"
    base = job / (state["name"] + suffix)
    text = "\n\n".join(s["text"] for s in segments) + "\n"
    timed = "\n".join(f'[{timestamp(s["start"]).split(",")[0]}] {s["text"]}' for s in segments) + "\n"
    srt, vtt = [], ["WEBVTT\n"]
    for index, segment in enumerate(segments, 1):
        srt.append(f'{index}\n{timestamp(segment["start"])} --> {timestamp(segment["end"])}\n{segment["text"]}\n')
        vtt.append(f'{timestamp(segment["start"], ".")} --> {timestamp(segment["end"], ".")}\n{segment["text"]}\n')
    write_atomic(Path(str(base) + ".txt"), text)
    write_atomic(Path(str(base) + ".timed.txt"), timed)
    write_atomic(Path(str(base) + ".srt"), "\n".join(srt))
    write_atomic(Path(str(base) + ".vtt"), "\n".join(vtt))
    review = [{"start": s["start"], "end": s["end"], "text": s["text"],
               "avg_logprob": s.get("avg_logprob"), "compression_ratio": s.get("compression_ratio")}
              for s in segments if (s.get("avg_logprob") is not None and s["avg_logprob"] < -1.0)
              or (s.get("compression_ratio") is not None and s["compression_ratio"] > 2.4)]
    save_json(Path(str(base) + ".review.json"), {"note": "These model signals identify places to listen to; they do not prove errors or measure overall accuracy.", "regions": review})
    save_json(Path(str(base) + ".json"), {"complete": complete, "source": state["source"],
              "config": state["config"], "processed_seconds": state["processed_seconds"],
              "segments": segments, "review_regions": len(review), "note": "Machine transcription; names, technical terms, and chunk seams have not been manually verified."})
    if complete:
        for extension in (".txt", ".timed.txt", ".srt", ".vtt", ".json", ".review.json"):
            (job / (state["name"] + ".partial" + extension)).unlink(missing_ok=True)
    return len(segments)


@contextlib.contextmanager
def job_lock(path):
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError(f"Another process is already working on {path.parent}") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def model_identity(path):
    path = path.expanduser().resolve(strict=True)
    if not (path / "config.json").is_file() or not any((path / name).is_file() for name in ("weights.npz", "weights.safetensors")):
        raise ValueError(f"Not a local MLX Whisper model: {path}")
    source = path / "model-source.json"
    # Model identity is content-based so a copied model can resume a moved job.
    files = {}
    for name in ("config.json", "weights.npz", "weights.safetensors"):
        candidate = path / name
        if candidate.is_file():
            digest = hashlib.sha256()
            with candidate.open("rb") as handle:
                for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            files[name] = {"bytes": candidate.stat().st_size, "sha256": digest.hexdigest()}
    return {"files": files, "source": json.loads(source.read_text()) if source.is_file() else None}


def transcribe_file(path, output, args):
    progress = ProgressReporter(lambda **fields: event('progress', file=path.name, **fields))
    details = probe(path)
    duration = details["duration_seconds"]
    start = args.start_seconds
    end = min(duration, start + args.duration_seconds) if args.duration_seconds else duration
    if start >= end:
        raise ValueError(f"Requested start is beyond the audio duration: {path}")
    progress.stage('checking_model')
    config = {"tool_version": CHECKPOINT_VERSION, "model": model_identity(args.model), "language": args.language,
              "chunk_seconds": args.chunk_seconds, "overlap_seconds": args.overlap_seconds,
              "start_seconds": start, "end_seconds": end, "initial_prompt": args.initial_prompt,
              "word_timestamps": True, "condition_on_previous_text": False,
              "hallucination_silence_threshold": 2.0}
    job = output / path.stem
    job.mkdir(parents=True, exist_ok=True)
    state_path = job / "state.json"
    with job_lock(job / ".lock"):
        progress.stage('checking_saved_progress')
        if state_path.exists():
            state = json.loads(state_path.read_text())
            if state["source"] != details["source"] or state["config"] != config:
                raise ValueError(f"Source or settings changed; choose a new output folder for {path.name}")
        else:
            if any(p.name != ".lock" for p in job.iterdir()):
                raise ValueError(f"Refusing to overwrite an existing output folder: {job}")
            state = {"name": path.stem, "source": details["source"], "config": config,
                     "duration_seconds": end - start, "processed_seconds": 0.0,
                     "status": "pending", "created_at": now(), "chunks": []}
            save_json(state_path, state)
        progress.configure(end - start, state['processed_seconds'])
        try:
            records = load_records(job, state)
        except Exception as error:
            state.update(status="failed", error=str(error), updated_at=now())
            save_json(state_path, state)
            raise
        if state["status"] == "complete":
            progress.stage('finishing')
            count = export(job, state, records, True)
            event("already_complete", file=path.name, output=str(job), segments=count)
            return state
        state.update(status="running", updated_at=now(), process_id=os.getpid(), error=None)
        save_json(state_path, state)
        event("file_started", file=path.name, duration_seconds=end - start, resumed_seconds=state["processed_seconds"])
        cursor = start + state["processed_seconds"]
        try:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
            progress.stage('loading_engine')
            import mlx_whisper
            while cursor < end - 0.001:
                if source_identity(path) != state["source"]:
                    raise ValueError(f"Source changed during processing: {path}")
                owned_end = min(end, cursor + args.chunk_seconds)
                extraction_start = max(start, cursor - args.overlap_seconds)
                extraction_end = min(end, owned_end + args.overlap_seconds)
                chunk_start = time.monotonic()
                progress.stage('preparing_audio')
                with tempfile.TemporaryDirectory(prefix="audio-", dir=job) as temporary:
                    wav = Path(temporary) / "chunk.wav"
                    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                                    "-ss", str(extraction_start), "-i", str(path), "-t", str(extraction_end - extraction_start),
                                    "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
                                   check=True, capture_output=True, text=True)
                    progress.stage('transcribing')
                    def completed_window(fraction):
                        absolute = extraction_start + fraction * (extraction_end - extraction_start)
                        progress.advance(min(owned_end, max(cursor, absolute)) - start)
                    with observe_windows(mlx_whisper.transcribe, completed_window):
                        raw = mlx_whisper.transcribe(str(wav), path_or_hf_repo=str(args.model.resolve()),
                                language=args.language, word_timestamps=True,
                                condition_on_previous_text=False, initial_prompt=args.initial_prompt,
                                hallucination_silence_threshold=2.0, verbose=None)
                record = {"owned_start": cursor, "owned_end": owned_end, "extraction_start": extraction_start,
                          "elapsed_seconds": time.monotonic() - chunk_start,
                          "segments": owned_segments(raw, extraction_start, cursor, owned_end), "raw": raw}
                progress.stage('saving_progress')
                chunk_path = job / ".checkpoints" / f"{len(records):05d}.json"
                save_json(chunk_path, record)
                digest = hashlib.sha256(chunk_path.read_bytes()).hexdigest()
                records.append(record)
                state["chunks"].append({"file": str(chunk_path.relative_to(job)), "sha256": digest})
                state.update(processed_seconds=owned_end - start, updated_at=now())
                save_json(state_path, state)
                count = export(job, state, records, False)
                progress.commit(owned_end - start, owned_end - cursor, record['elapsed_seconds'])
                event("chunk_complete", file=path.name, processed_seconds=state["processed_seconds"],
                      total_seconds=end - start, percent=round(100 * state["processed_seconds"] / (end - start), 2),
                      elapsed_seconds=round(record["elapsed_seconds"], 2), segments=count)
                cursor = owned_end
            progress.stage('finishing')
            state.update(status="complete", updated_at=now(), completed_at=now())
            count = export(job, state, records, True)
            save_json(state_path, state)
            event("file_complete", file=path.name, output=str(job), segments=count)
        except BaseException as error:
            state.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                         error=str(error), updated_at=now())
            save_json(state_path, state)
            event(state["status"], file=path.name, error=str(error), processed_seconds=state["processed_seconds"])
            raise
        return state


def load_records(job, state):
    records = []
    for checkpoint in state["chunks"]:
        path = job / checkpoint["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != checkpoint["sha256"]:
            raise ValueError(f"Checkpoint changed: {path}")
        records.append(json.loads(path.read_text()))
    return records


def resolve_inputs(args):
    paths = list(args.inputs)
    if args.input_list:
        values = json.loads(args.input_list.read_text())
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            raise ValueError("Input list must be a JSON array of file paths")
        paths.extend(Path(value) for value in values)
    expanded = []
    for path in paths:
        path = path.expanduser().resolve(strict=True)
        expanded.extend(sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS)
                        if path.is_dir() else [path])
    result = list(dict.fromkeys(expanded))
    if not result:
        raise ValueError("No input files supplied")
    stems = [path.stem for path in result]
    if len(stems) != len(set(stems)):
        raise ValueError("Input files share a filename stem; process them into separate output folders")
    return result


def main(argv=None):
    runtime.configure_environment()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect_parser = commands.add_parser("probe", help="Inspect selected files without loading Whisper")
    run = commands.add_parser("run", help="Transcribe locally; rerun the same command to resume")
    for child in (inspect_parser, run):
        child.add_argument("inputs", nargs="*", type=Path)
        child.add_argument("--input-list", type=Path, help="JSON array of selected file paths")
    run.add_argument("--output", required=True, type=Path)
    run.add_argument("--model", type=Path, default=runtime.model_directory())
    run.add_argument("--language", default="en")
    run.add_argument("--chunk-seconds", type=float, default=900)
    run.add_argument("--overlap-seconds", type=float, default=5)
    run.add_argument("--start-seconds", type=float, default=0)
    run.add_argument("--duration-seconds", type=float)
    run.add_argument("--initial-prompt", default="")
    status = commands.add_parser("status", help="Read checkpoints without loading Whisper")
    status.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            states = [json.loads(path.read_text()) for path in sorted(args.output.glob("*/state.json"))]
            text = [{key: state.get(key) for key in ("name", "status", "processed_seconds", "duration_seconds", "error", "updated_at")}
                    for state in states]
            print(json.dumps(text, indent=2, ensure_ascii=False))
            return 0
        if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
            raise ValueError("FFmpeg and ffprobe are required on PATH")
        paths = resolve_inputs(args)
        if args.command == "probe":
            for path in paths:
                print(json.dumps(probe(path), ensure_ascii=False))
            return 0
        if args.chunk_seconds <= 0 or args.overlap_seconds < 0 or args.start_seconds < 0:
            raise ValueError("Chunk length must be positive; overlap and start must be nonnegative")
        if args.duration_seconds is not None and args.duration_seconds <= 0:
            raise ValueError("Requested duration must be positive")
        args.output = args.output.expanduser().resolve()
        args.output.mkdir(parents=True, exist_ok=True)
        failures = []
        for path in paths:
            try:
                transcribe_file(path, args.output, args)
            except Exception as error:
                failures.append({"file": str(path), "error": str(error)})
                event("file_error", file=path.name, error=str(error))
        save_json(args.output / "run-summary.json", {"finished_at": now(), "inputs": [str(path) for path in paths], "failures": failures})
        return 1 if failures else 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
