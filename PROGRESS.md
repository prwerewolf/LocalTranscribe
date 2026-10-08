# Project status

## Delivered

- Offline MLX Whisper transcription with file/folder inputs and large-file chunking.
- Checkpoint/resume, checksum checks, original-file preservation, and partial/final export separation.
- TXT, timed TXT, SRT, VTT, structured JSON, and review-region exports.
- Native Mac UI with file/folder selection, drag/drop, output selection, manual Start/Stop, and a persistent local queue.
- App icon, reproducible setup/build helpers, neutral bundle identity, noncommercial licensing, and publication privacy checks.
- Front-page AI-assisted setup instructions for local, machine-aware configuration with private settings and explicit recording controls.

## Verification

- The engine completed a real recording validation and a small excerpt with chunk boundaries. Word accuracy was not independently measured.
- Automated tests cover interrupted/resumed chunks, checkpoint corruption, locking, subtitle rounding, and publication privacy rules.
- The native window, file picker, and manual selection controls were inspected. No automatic recording batch is part of setup or CI.
- CI runs Python tests/privacy checks and native source validation. Models and recordings remain local.

## Decisions and environment

- Apple Silicon/macOS is the supported runtime; Intel/Windows/Linux inference backends are not implemented.
- The app stays beside its project-local runtime and model. It is not a standalone notarized bundle.
- The native UI uses loopback port 8789. Another process on that port can prevent startup; the app reports a local server error.
- GUI transcription uses English defaults. CLI flags expose other language/excerpt/settings options.
- No Codex skill is installed by the project or setup.

## Next useful work

- Expose language and decoding options in the GUI.
- Improve automatic handling of port conflicts and dependency/setup errors.
- Consider a standalone signed/notarized distribution after the source release is established.
- Add further synthetic UI-controller tests when changing queue/start/stop behavior.
