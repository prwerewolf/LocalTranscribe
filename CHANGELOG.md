# Changelog

## Unreleased

## 0.3.0

- Report live progress from the current MLX engine's completed audio windows, plus checking/preparing/transcribing/saving/finishing stages and elapsed time.
- Show approximate time remaining for the active recording and selected batch after measured processing speed is available; reset estimates on Resume and hide stale estimates.
- Keep live progress separate from saved checkpoints, show the saved percentage on Stop, and preserve decoding settings, checkpoint compatibility, model identity, and exports.
- Refresh progress once per second while preserving row/control identity and keyboard focus; show an explicit stopping state.

## 0.2.0

- Build a self-contained movable Mac app containing Python, the existing MLX Whisper engine, its pinned model, FFmpeg/ffprobe, and native dependency libraries.
- Keep bundled queue state/logs/caches in Application Support and import an existing source-build queue without overwriting either copy.
- Preserve the existing engine/checkpoint format, model identity, Stop/Resume behavior, and exports; include a movable command-line launcher.
- Verify native dependency relocation, ad-hoc signatures, runtime state isolation, queue preservation, and packaged synthetic-speech stop/resume. Detect the minimum macOS required by bundled libraries.

- Added prominent optional AI-assisted setup instructions and a copyable prompt for configuring a supported computer without publishing machine details or starting recording jobs.

## 0.1.1

Initial public source release:

- Local Whisper transcription and resumable large-recording processing.
- Native Mac queue UI with manual controls and file/folder selection.
- Text/subtitle exports and review-region notes.
- App icon, setup/build instructions, noncommercial license, and privacy-safe publication checks.
