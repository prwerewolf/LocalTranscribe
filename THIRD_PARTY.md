# Third-party components

The project's noncommercial license applies to its original source, documentation, and artwork. It does not replace the licenses of dependencies, system tools, or model weights.

The source setup downloads or uses these components separately; their files are not vendored in this repository. The self-contained local app bundles the installed runtime, Python dependencies, decoder libraries, and selected model:

- [MLX and MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper): Apple Silicon inference and Whisper integration, under the MIT license.
- [OpenAI Whisper](https://github.com/openai/whisper): the underlying model family, under the upstream MIT license. The selected model is an [MLX-format conversion](https://huggingface.co/mlx-community/whisper-large-v3-turbo).
- [FFmpeg](https://ffmpeg.org/legal.html): audio extraction, under the LGPL or GPL depending on the installed build. The app builder copies FFmpeg/ffprobe and their non-system dynamic dependencies. Its version/build flags and license text, plus available installed Homebrew license files/build recipes, are retained under `Contents/Resources/ThirdPartyNotices`.
- [Python](https://docs.python.org/3/license.html), PyTorch, NumPy, and other Python dependencies: their respective upstream licenses. Package versions are pinned in `requirements.lock`, and installed distributions contain the applicable notices.
- Apple system frameworks: provided by macOS and the development tools; not redistributed by this repository.

Python package notices remain in the bundled `site-packages` distribution metadata, and the Python standard-library license is retained with that library. `bundle-manifest.json` records the copied Python version, FFmpeg build, model revision/checksums, and actual minimum macOS version.

GitHub releases remain source-only. Redistributing a built app requires complying with every bundled component's terms, including applicable FFmpeg/dependency corresponding-source obligations; the included notices do not replace those obligations. The app's original noncommercial license does not relicense its separate third-party components.
