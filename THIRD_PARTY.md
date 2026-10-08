# Third-party components

The project's noncommercial license applies to its original source, documentation, and artwork. It does not replace the licenses of dependencies, system tools, or model weights.

LocalTranscribe downloads or uses these components separately; their files are not vendored in this repository:

- [MLX and MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper): Apple Silicon inference and Whisper integration, under the MIT license.
- [OpenAI Whisper](https://github.com/openai/whisper): the underlying model family, under the upstream MIT license. The selected model is an [MLX-format conversion](https://huggingface.co/mlx-community/whisper-large-v3-turbo).
- [FFmpeg](https://ffmpeg.org/legal.html): audio extraction, under the LGPL or GPL depending on the build. The user installs FFmpeg separately.
- [Python](https://docs.python.org/3/license.html), PyTorch, NumPy, and other Python dependencies: their respective upstream licenses. Package versions are pinned in `requirements.lock`, and installed distributions contain the applicable notices.
- Apple system frameworks: provided by macOS and the development tools; not redistributed by this repository.

Redistributors who bundle third-party dependencies or model weights are responsible for retaining and complying with their upstream terms. The source setup in this repository installs them separately.
