"""Download/reconstruct the published Qwen base models using only Python 3.11+."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.request import urlopen
from uuid import uuid4

REPOSITORY = "smartevent-ticketing/ai-service"
TAG = "qwen25-base-models-20261030"
BLOCK = 8 * 1024 * 1024


def safe_name(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("Unsafe filename in release manifest")
    return value


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_manifest(manifest: dict, tag: str) -> str:
    safe_name(tag)
    if (
        manifest.get("format_version") != 1
        or manifest.get("scope") != "smartevent-base-model-mirror"
        or manifest.get("repository") != REPOSITORY
        or manifest.get("tag") != tag
    ):
        raise ValueError("Unexpected model release manifest")
    models = manifest.get("models", [])
    if len(models) != 2 or {m["key"] for m in models} != {"nlu", "rag"}:
        raise ValueError("Release must contain exactly the NLU and RAG bases")
    prefix = f"https://github.com/{REPOSITORY}/releases/download/{tag}/"
    for model in models:
        paths = set()
        for file in model["files"]:
            name = safe_name(file["path"])
            if (
                name in paths
                or not file.get("parts")
                or sum(p["size"] for p in file["parts"]) != file["size"]
            ):
                raise ValueError("Duplicate file or invalid release part sizes")
            paths.add(name)
            validate_hash(file["sha256"])
            for part in file["parts"]:
                validate_asset(part, prefix)
        if "LICENSE" not in paths or "config.json" not in paths:
            raise ValueError("Base model is missing its license or configuration")
    for asset in manifest.get("support_files", []):
        validate_asset(asset, prefix)
    return prefix


def validate_hash(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ValueError("Invalid release SHA-256")


def validate_asset(asset: dict, prefix: str) -> None:
    name = safe_name(asset["name"])
    validate_hash(asset["sha256"])
    if (
        asset["url"] != prefix + name
        or type(asset["size"]) is not int
        or not 0 < asset["size"] < 2**31
    ):
        raise ValueError("Asset URL or size is outside the fixed release")


def restore_file(record: dict, destination: Path, assets_dir: Path | None = None) -> None:
    if destination.exists():
        if (
            destination.is_file()
            and destination.stat().st_size == record["size"]
            and sha256_file(destination) == record["sha256"]
        ):
            print(f"Already verified: {destination}", flush=True)
            return
        raise ValueError("Refusing to overwrite a different file: " + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".partial-" + uuid4().hex)
    whole = hashlib.sha256()
    total = 0
    try:
        with temporary.open("xb") as output:
            for part in record["parts"]:
                print(f"Reading {part['name']} ({part['size']} bytes)", flush=True)
                stream = (
                    (assets_dir / part["name"]).open("rb")
                    if assets_dir
                    else urlopen(part["url"], timeout=180)  # noqa: S310 -- validated fixed release
                )
                checksum = hashlib.sha256()
                length = 0
                with stream:
                    while block := stream.read(BLOCK):
                        length += len(block)
                        if length > part["size"]:
                            raise ValueError("Release part exceeds declared length")
                        output.write(block)
                        checksum.update(block)
                        whole.update(block)
                if length != part["size"] or checksum.hexdigest() != part["sha256"]:
                    raise ValueError("Release part failed SHA-256 verification")
                total += length
        if total != record["size"] or whole.hexdigest() != record["sha256"]:
            raise ValueError("Reconstructed model failed SHA-256 verification")
        # Another process must not silently replace a model during reconstruction.
        if destination.exists():
            raise ValueError("Destination appeared during reconstruction")
        temporary.rename(destination)
        print(f"Verified original file: {destination}", flush=True)
    finally:
        if temporary.exists():
            temporary.unlink()  # Only our uniquely named partial file, never the target directory.


def download(output: Path, tag: str = TAG, assets_dir: Path | None = None) -> None:
    safe_name(tag)
    if assets_dir:
        manifest = json.loads((assets_dir / "base-models-manifest.json").read_text("utf-8"))
    else:
        url = f"https://github.com/{REPOSITORY}/releases/download/{tag}/base-models-manifest.json"
        with urlopen(url, timeout=30) as response:  # noqa: S310 -- fixed GitHub HTTPS origin
            manifest = json.loads(response.read(1024 * 1024))
    validate_manifest(manifest, tag)
    output = output.expanduser().resolve()
    for model in manifest["models"]:
        for file in model["files"]:
            restore_file(file, output / model["key"] / file["path"], assets_dir)
    for support in manifest["support_files"]:
        restore_file({**support, "parts": [support]}, output / support["name"], assets_dir)
    print(f"BASE_MODELS_READY: {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(".models/base"))
    parser.add_argument("--tag", default=TAG)
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Optional folder already downloaded using gh release download",
    )
    args = parser.parse_args()
    download(args.output, args.tag, args.assets_dir)
