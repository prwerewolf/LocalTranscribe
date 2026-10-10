# Privacy and publication

## Runtime

- Recordings and extracted audio stay on the local computer.
- Whisper inference uses a downloaded local model with Hugging Face offline mode enabled and telemetry disabled.
- Initial setup downloads packages and public model weights. No recording is part of those requests.
- The UI server binds to loopback only. Mutating requests require its ephemeral app token.
- Queue state and logs can contain local file paths. The bundled app keeps them in `~/Library/Application Support/LocalTranscribe`; source-mode commands use ignored `.data/`. Neither is packaged inside the app or published.
- First launch beside a source checkout can copy its existing queue into Application Support when no queue is already present. The original queue and transcript/checkpoint folders are preserved. `LOCALTRANSCRIBE_DATA_DIR` selects isolated state and disables that import.
- The app bundles the interpreter, dependencies, decoder, and pinned public model. Build inputs exclude local queues, recordings, transcripts, Hugging Face caches, and development records. Python bytecode writing is disabled for bundled launches; other caches go into the private state folder.
- Transcript and checkpoint files can contain the recording's content and source path. Keep them in a private output folder and review them before sharing.

## Public releases

Git contains only the application source, generic documentation, license/notice, build/check helpers, tests, CI definition, and icon assets. It excludes runtime environments, model downloads, recordings, transcripts, logs, screenshots of real recordings, local run records, unregistered skill drafts, environment files, and Finder metadata.

`scripts/check_release.py` checks tracked content for user-home paths, private temporary paths, environment/key files, common embedded credential formats, non-neutral bundle metadata, and descriptive image metadata. Maintainers can supply additional private blocked terms through an untracked file for a local publication audit; that file and its contents must never be committed.

The app build remaps compilation paths and uses a project identifier rather than a personal developer identifier. Public commits should use a project maintainer identity and a non-personal email; GitHub repository ownership remains visible.

Do not add personal machine inventories, usernames, email addresses, raw local run records, or production recordings to public tests or documentation. Use synthetic test fixtures.
