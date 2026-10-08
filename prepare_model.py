"""Download public Whisper weights, recording the exact model revision."""
import argparse
import hashlib
import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repo", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--revision", help="Pin a model revision for reproducible setup")
    args = parser.parse_args()
    args.destination.mkdir(parents=True, exist_ok=True)
    revision = args.revision or HfApi(token=False).model_info(args.repo).sha
    print(json.dumps({"event": "download", "repo": args.repo, "revision": revision}), flush=True)
    snapshot_download(
        args.repo,
        revision=revision,
        local_dir=args.destination,
        allow_patterns=["*.json", "*.npz", "*.safetensors", "README.md"],
        token=False,
    )
    files = {}
    for path in sorted(args.destination.iterdir()):
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
                    digest.update(block)
            files[path.name] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    record = {"repo": args.repo, "revision": revision, "files": files}
    (args.destination / "model-source.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"event": "ready", "destination": str(args.destination), **record}), flush=True)


if __name__ == "__main__":
    main()
