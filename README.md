# LocalTranscribe

<img src="assets/localtranscribe-icon.png" width="128" alt="LocalTranscribe icon">

Turn audio and video recordings into text on your Mac. LocalTranscribe uses Whisper locally, with a native Mac window, a recording queue, and resumable processing for large files.

**Free for noncommercial use.** No transcription subscription or API key. Source is available under the [PolyForm Noncommercial License 1.0.0](LICENSE); commercial use and commercial resale are not permitted by that license. Noncommercial sharing and modifications are allowed with the required notices.

## Set up for your computer

Choose [AI-assisted setup](#ai-assisted-setup-optional) for help configuring your computer, or follow the [standard setup](#standard-setup) yourself. The current pinned MLX runtime requires **Apple Silicon and macOS 26.2 or later**. The native window targets macOS 14, but that alone does not establish inference-library compatibility. The builder detects and records the actual minimum macOS version of all bundled native libraries. Intel Macs, Windows, and Linux require additional backend/native-app work; older macOS versions require compatible runtime dependencies.

### AI-assisted setup (optional)

1. Download or clone this GitHub repository into a local folder.
2. Open that folder in a coding assistant with access to files and a terminal **on the computer where you will run the app**. Providing only the GitHub URL to a cloud chat does not give it access to your machine.
3. Paste this prompt:

```text
Set up LocalTranscribe for this computer. Check its CPU architecture, OS version,
available RAM, disk space, and installed dependencies. Follow the repository's
setup and build instructions. Choose a compatible local Whisper model and suitable
settings, making only the changes needed for this computer.

Keep machine-specific settings in ignored local files. Do not commit personal
names, home paths, hardware inventories, model downloads, logs, or recordings.
Preserve the license and required notices, and keep existing recordings and
transcripts intact. Use local inference without a paid API or recording uploads.

Run the existing small checks and verify the app opens. Do not process recordings
or start performance experiments unless I request them. If this computer is not
supported, explain the required porting work before modifying the app.
```

AI assistance is optional; the standard setup below works without a coding assistant. Keep any local customization private unless you intentionally prepare and review a contribution.

## Standard setup

Requirements:

- An Apple Silicon Mac with macOS 26.2 or later for the current pinned runtime.
- [Homebrew](https://brew.sh), `uv`, and FFmpeg.
- Xcode Command Line Tools for building the native window.
- Several GB of free disk space for the build environment and the self-contained app, including its model.
- An internet connection for initial dependency/model downloads. Transcription then runs offline.

Install the prerequisites if needed:

```sh
brew install uv ffmpeg
xcode-select --install
```

Download or clone this repository, then run setup from its folder:

```sh
git clone https://github.com/prwerewolf/LocalTranscribe.git
cd LocalTranscribe
./setup.command
open LocalTranscribe.app
```

You can also double-click `setup.command` in Finder. Setup creates a project-local Python environment, installs the pinned dependencies, downloads the pinned public model, and builds the native app. The app contains its own Python interpreter, dependencies, FFmpeg/ffprobe and their libraries, interface, and model. It does not install a Codex skill or change global Git/Python settings.

Open `LocalTranscribe.app` once beside the project to import an existing source-build queue, quit it, then move it into Applications or another folder. After building, it runs without the project folder, Homebrew, `uv`, or a separate Python installation. You can copy the complete app to another compatible Apple Silicon Mac; personal queues and transcripts stay on their original computer.

The builder preserves the previous generated app under `.build/previous-LocalTranscribe.app` until the next build. This is a self-contained local build with ad-hoc signing. GitHub releases provide source; they do not provide a Developer ID-signed, notarized app download.

## Transcribe

1. Add files or a folder, or drag recordings into the app.
2. Select the recordings you want to process.
3. Choose the output folder.
4. Press **Transcribe selected**.

Nothing starts automatically. **Stop** preserves completed checkpoints. Select a stopped recording and start again with the same source/settings/output folder to resume. Closing the app stops its active work.

While a recording runs, the app shows its current stage, elapsed time, live progress, and the percentage saved to checkpoints. Progress updates as the existing engine finishes smaller audio windows, rather than waiting for a whole 15-minute chunk. The estimated time remaining appears after enough processing speed has been measured, adapts as work proceeds, and is approximate. The bottom bar also estimates the remaining time for the selected batch, using the current speed and remaining audio.

The estimate is recalculated from fresh measurements on each run/resume and is hidden when recent progress is too stale to support it. Finishing exports and stopping use explicit status messages. On Stop, the bar returns to the last saved percentage; the unfinished portion of a chunk is processed again on Resume. Live progress and estimates are not saved as checkpoints.

Each recording gets its own output folder:

| File | Contents |
| --- | --- |
| `.txt` | Plain transcript |
| `.timed.txt` | Transcript with timestamps |
| `.srt`, `.vtt` | Timed subtitles |
| `.json` | Structured transcript and word timings |
| `.review.json` | Regions flagged for listening review |
| `state.json`, `.checkpoints/` | Resume state and original model output |

Large videos are read directly from disk. FFmpeg extracts manageable audio chunks; recordings are not uploaded to a transcription service. Original files are preserved.

Transcripts are machine output. Names, technical terms, and chunk seams can need correction. Review flags do not establish accuracy. Whisper does not provide reliable speaker identification here.

## Command line

```sh
./local-transcribe probe '/path/to/video.mp4'
./local-transcribe run '/path/to/video.mp4' --output '/path/to/transcripts'
./local-transcribe run '/path/to/videos' --output '/path/to/transcripts'
./local-transcribe status '/path/to/transcripts'
```

Use `--input-list selected-files.json` for a JSON array of exact paths. Folder inputs include supported media directly inside that folder. Defaults are English, 15-minute chunks, and 5-second overlap. `--language` changes the transcription language; `--initial-prompt` supplies relevant spellings. `--start-seconds` and `--duration-seconds` select an excerpt. Changing a source or decoding settings requires a new output folder.

Use `./local-transcribe run --help` for all options. The GUI currently uses the English defaults. The movable app also includes a command-line launcher:

```sh
'/Applications/LocalTranscribe.app/Contents/Resources/local-transcribe' run '/path/to/video.mp4' --output '/path/to/transcripts'
```

## Privacy and local state

The native window talks only to a loopback server at `127.0.0.1:8789`. Whisper inference runs with offline mode and telemetry disabled. No hosted inference service or API billing is used. The initial public model download connects to Hugging Face; dependency installation connects to package registries.

The bundled app stores queue state, logs, and caches in `~/Library/Application Support/LocalTranscribe`, outside the app. Source-mode commands keep the existing `.data/` layout. First launch beside the project copies an existing queue only when the destination queue is absent, preserving its original copy. Existing transcript/checkpoint folders and the engine's checkpoint format are preserved, including when the model is copied into the app.

`LOCALTRANSCRIBE_DATA_DIR` optionally selects an alternate private state folder for isolated verification. It also disables automatic source-queue import. Dependencies, models, recordings, transcripts, generated app bundles, and local development records are excluded from Git. See [PRIVACY.md](PRIVACY.md).

## Development

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
python3 scripts/build_app.py --check-only
python3 scripts/build_app.py
python3 scripts/check_bundle.py --app '/path/to/moved/LocalTranscribe.app'
```

The builder copies the current transcription environment, resolves native dependency links into the bundle, records versions/model identity in `Contents/Resources/bundle-manifest.json`, and signs the resulting app. `--python` selects an existing compatible transcription environment. Writable files are kept outside the signed bundle, including Python/Numba caches.

`check_bundle.py` checks signatures, external native links and symlinks, bundled imports, FFmpeg, and the bundled CLI using a clean executable search path. Add `--transcribe-fixture` to generate local synthetic speech and verify real MLX transcription, Stop, checkpoint preservation, and Resume. No personal recording is used. Run that optional GPU check only when requested as part of development/release verification.

CI checks Python behavior, live/saved progress separation, estimate warm-up/resume behavior, Stop signaling, runtime paths/queue migration, the public-file privacy rules, and the native Swift source. It does not download models, build the full runtime, or transcribe recordings.

## License

LocalTranscribe's original code, documentation, and artwork use [PolyForm Noncommercial 1.0.0](LICENSE). Preserve [NOTICE](NOTICE) when sharing copies or modifications. This is source-available software with commercial restrictions, rather than an OSI-approved open-source license.

Third-party libraries, system tools, and model weights retain their own licenses. See [THIRD_PARTY.md](THIRD_PARTY.md). This project does not change their licensing or confer rights in input recordings.
