# Project status

## Delivered

- Offline MLX Whisper transcription with file/folder inputs and large-file chunking.
- Checkpoint/resume, checksum checks, original-file preservation, and partial/final export separation.
- TXT, timed TXT, SRT, VTT, structured JSON, and review-region exports.
- Native Mac UI with file/folder selection, drag/drop, output selection, manual Start/Stop, and a persistent local queue.
- App icon, reproducible setup/build helpers, neutral bundle identity, noncommercial licensing, and publication privacy checks.
- Front-page AI-assisted setup instructions for local, machine-aware configuration with private settings and explicit recording controls.
- Self-contained app packaging with the existing Python/MLX engine, pinned model, FFmpeg/ffprobe and native libraries, bundle-relative command-line launcher, and signatures.
- External writable app state, non-overwriting source-queue migration, and preserved checkpoint/model identities for existing stopped jobs.
- Live inference-window progress, named processing stages, elapsed time, and approximate active-recording/batch time remaining with warm-up and stale-estimate handling.
- Saved/live progress separation, explicit stopping/resume presentation, and stable UI rows during one-second refreshes.

## Verification

- The engine completed a real recording validation and a small excerpt with chunk boundaries. Word accuracy was not independently measured.
- Automated tests cover interrupted/resumed chunks, checkpoint corruption, locking, subtitle rounding, and publication privacy rules.
- Automated controller/runtime checks also cover Stop signaling/progress preservation, bundle-relative runtime/model paths, external state, source-queue preservation, and universal-binary dependency parsing.
- A bundle moved outside the checkout completed real MLX inference on locally generated speech, stopped after a checkpoint, and resumed without rewriting completed checkpoint files. Bundled native imports/FFmpeg and signatures passed with a clean executable search path.
- The final native window and file picker opened successfully; first-launch migration preserved the existing queue and output selection without starting personal recordings. Nine automated tests passed locally.
- Progress-update tests cover measured-window estimates, exclusion of initial model-load/preparation delays, fresh Resume estimates, checkpoint-only saved progress, stale estimate suppression, and reporting-namespace restoration on interruption.
- Sixteen automated tests passed, including recovery of the saved percentage when interruption arrives before a chunk-complete message. The updated bundle also passed real generated-speech Stop/Resume after moving outside the checkout.
- A generated three-minute speech fixture produced eight intermediate updates and five measured estimates before its first checkpoint with unchanged decoder options. Synthetic UI states passed at 1020×780 and 740×600, including Stop, saved-progress rollback, long names, keyboard focus, and no console errors.
- The mechanical UI scan flags pre-existing small/muted labels and a shadow warning outside the progress change; added progress text is 12px with a contrasting foreground. The existing visual identity is retained.
- The native window, file picker, and manual selection controls were inspected. No automatic recording batch is part of setup or CI.
- CI runs Python tests/privacy checks and native source validation. Models and recordings remain local.

## Decisions and environment

- Apple Silicon/macOS is the supported runtime; Intel/Windows/Linux inference backends are not implemented.
- The built app is self-contained and movable. Source setup still needs build prerequisites; running/copying a completed app does not. Signing is ad-hoc and GitHub releases remain source-only; Developer ID/notarization and public binary redistribution are separate future work.
- Bundled app state uses Application Support; source commands keep `.data/`. First launch beside the checkout imports an existing queue only when the destination is empty. `LOCALTRANSCRIBE_DATA_DIR` isolates verification and suppresses import.
- The checkpoint format version remains 0.1.1 while the app version is 0.3.0, preserving existing resume settings. Bundled model files and provenance are copied unchanged.
- Progress observes the pinned engine's existing tqdm reporting namespace only during a transcription call and restores it on every exit. Decoder options and installed engine files are unchanged; implementations without this reporting interface fall back to stages/completed checkpoints.
- Estimates use recent completed-window measurements (or actual completed chunk timings for short/silent chunks), exclude initial model loading from window speed, reset per run, and remain transient. A 99% display cap reserves the final completion state for successful exports.
- The builder detects native-library macOS deployment targets, relocates non-system dylib links, keeps installed notices, and stages/signs before replacing the previous generated app.
- The pinned MLX 0.32.3 native libraries require macOS 26.2. The Swift window's macOS 14 target must not be advertised as the whole app's minimum; older systems need a compatible inference/runtime environment.
- The native UI uses loopback port 8789. Another process on that port can prevent startup; the app reports a local server error.
- GUI transcription uses English defaults. CLI flags expose other language/excerpt/settings options.
- No Codex skill is installed by the project or setup.

## Next useful work

- Expose language and decoding options in the GUI.
- Improve automatic handling of port conflicts and dependency/setup errors.
- Prepare Developer ID signing/notarization and complete third-party source compliance before offering public binary downloads.
- Add further synthetic UI-controller tests when changing queue/start/stop behavior.
