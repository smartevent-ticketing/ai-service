"""Publish pinned, byte-verified base weights as split GitHub Release assets."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import urlopen

REPOSITORY = "smartevent-ticketing/ai-service"
TAG = "qwen25-base-models-20261030"
MARKER = "SmartEvent pinned Qwen base-model mirror"
PART_BYTES = 1_500_000_000  # Less than GitHub's 2 GiB per-asset limit.
BLOCK = 8 * 1024 * 1024
ALLOWED_MODELS = {"nlu": "Qwen/Qwen2.5-1.5B-Instruct", "rag": "Qwen/Qwen2.5-3B-Instruct"}
PUBLICATION_BRANCH = "publish/base-models-qwen25-20261030"
PUBLICATION_FILES = (
    "scripts/release/publish_base_models.py",
    "scripts/release/download_base_models.py",
    "models/base-models-source.json",
    ".github/workflows/publish-base-models.yml",
    "docs/architecture/BASE_MODEL_DISTRIBUTION.md",
    "tests/release/test_base_model_release.py",
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_name(name: str) -> str:
    if (
        not isinstance(name, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name)
        or name in (".", "..")
    ):
        raise ValueError("Unsafe model/asset filename")
    return name


def validate_source(source: dict) -> None:
    if source.get("format_version") != 1 or {m["key"] for m in source["models"]} != set(
        ALLOWED_MODELS
    ):
        raise ValueError("Unexpected source manifest")
    for model in source["models"]:
        if model["repo_id"] != ALLOWED_MODELS[model["key"]] or not re.fullmatch(
            r"[a-f0-9]{40}", model["revision"]
        ):
            raise ValueError("Only pinned official Qwen revisions may be mirrored")
        for file in model["files"]:
            safe_name(file["path"])
            if file["path"] != "LICENSE" and (
                not re.fullmatch(r"[a-f0-9]{64}", file.get("sha256", ""))
                or type(file.get("size")) is not int
                or file["size"] <= 0
            ):
                raise ValueError("Model files must have pinned sizes and SHA-256")


def split_file(path: Path, prefix: str, directory: Path, part_bytes: int = PART_BYTES):
    """Bounded-memory splitting; caller may upload and remove each completed part."""
    if part_bytes <= 0 or part_bytes >= 2**31:
        raise ValueError("Invalid release part size")
    safe_name(prefix)
    with path.open("rb") as source:
        index = 0
        while block := source.read(min(BLOCK, part_bytes)):
            index += 1
            part = directory / f"{prefix}.part{index:04d}"
            checksum = hashlib.sha256()
            size = 0
            with part.open("xb") as output:
                while block:
                    output.write(block)
                    checksum.update(block)
                    size += len(block)
                    if size == part_bytes:
                        break
                    block = source.read(min(BLOCK, part_bytes - size))
            yield part, {"name": part.name, "size": size, "sha256": checksum.hexdigest()}


def gh(*arguments: str, allow_not_found: bool = False):
    result = subprocess.run(["gh", *arguments], capture_output=True, text=True, check=False)  # noqa: S603,S607
    if result.returncode:
        if allow_not_found and "HTTP 404" in result.stderr:
            return None
        raise RuntimeError("GitHub operation failed: " + result.stderr[-1500:])
    return result.stdout


def api(path: str, allow_not_found: bool = False):
    response = gh("api", path, allow_not_found=allow_not_found)
    return None if response is None else json.loads(response)


def post_api(path: str, body: dict) -> dict:
    result = subprocess.run(  # noqa: S603,S607 -- fixed GitHub CLI, no shell
        ["gh", "api", "--method", "POST", path, "--input", "-"],  # noqa: S607
        input=json.dumps(body),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError("GitHub write failed: " + result.stderr[-1500:])
    return json.loads(result.stdout)


def start_workflow(root: Path) -> str:
    """Publish only mirror tooling on a new branch; do not touch local Git state."""
    prefix = f"repos/{REPOSITORY}"
    existing = api(f"{prefix}/git/ref/heads/{PUBLICATION_BRANCH}", allow_not_found=True)
    if existing:
        raise ValueError(
            "Publication branch already exists; open Actions and rerun its publication job"
        )
    main = api(f"{prefix}/git/ref/heads/main")["object"]["sha"]
    base_tree = api(f"{prefix}/git/commits/{main}")["tree"]["sha"]
    remote_manifest = api(f"{prefix}/contents/MANIFEST_SHA256.json?ref={main}")
    manifest = json.loads(base64.b64decode(remote_manifest["content"]))
    validate_source(json.loads((root / "models/base-models-source.json").read_text("utf-8")))
    entries = []
    for path in PUBLICATION_FILES:
        content = (root / path).read_text("utf-8")
        entries.append({"path": path, "mode": "100644", "type": "blob", "content": content})
        if not path.startswith("models/"):
            manifest[path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    entries.append(
        {
            "path": "MANIFEST_SHA256.json",
            "mode": "100644",
            "type": "blob",
            "content": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        }
    )
    tree = post_api(f"{prefix}/git/trees", {"base_tree": base_tree, "tree": entries})
    commit = post_api(
        f"{prefix}/git/commits",
        {
            "message": "Thêm quy trình phát hành hai mô hình nền Qwen có kiểm tra toàn vẹn",
            "tree": tree["sha"],
            "parents": [main],
        },
    )
    post_api(
        f"{prefix}/git/refs", {"ref": "refs/heads/" + PUBLICATION_BRANCH, "sha": commit["sha"]}
    )
    return f"https://github.com/{REPOSITORY}/actions?query=branch%3A{PUBLICATION_BRANCH}"


def fetch_source(model: dict, file: dict, destination: Path) -> None:
    url = f"https://huggingface.co/{model['repo_id']}/resolve/{model['revision']}/{file['path']}?download=true"
    print(f"Downloading pinned source: {model['key']}/{file['path']}", flush=True)
    for attempt in range(3):
        try:
            with urlopen(url, timeout=180) as response, destination.open("wb") as output:  # noqa: S310 -- validated fixed HTTPS source
                while block := response.read(BLOCK):
                    output.write(block)
            break
        except (HTTPError, OSError):
            if attempt == 2:
                raise
            time.sleep(3)
    if file["path"] == "LICENSE":
        text = destination.read_text("utf-8")
        expected = "Apache License" if model["key"] == "nlu" else "Qwen RESEARCH LICENSE AGREEMENT"
        if expected not in text or destination.stat().st_size > 100_000:
            raise ValueError("Unexpected upstream license")
    elif destination.stat().st_size != file["size"] or digest(destination) != file["sha256"]:
        raise ValueError("Upstream bytes differ from the locally tested model: " + file["path"])


def release(tag: str, target: str, work: Path) -> dict:
    current = api(f"repos/{REPOSITORY}/releases/tags/{tag}", allow_not_found=True)
    if current is None:
        notes = work / "release-notes.md"
        notes.write_text(
            f"{MARKER}\n\nBuilt with Qwen.\n\n"
            "Two unmodified upstream base models, split into assets below 2 GiB. "
            "Each original file has SHA-256 and size checks. Adapter weights are separate.\n\n"
            "NLU: Apache-2.0. RAG 3B: Qwen Research License, non-commercial research/evaluation only. "
            "Upstream LICENSE files and required attribution are included.\n\n"
            "Download download_base_models.py and run it to reconstruct the base models. "
            "See BASE_MODEL_DISTRIBUTION.md for instructions.\n",
            encoding="utf-8",
        )
        gh(
            "release",
            "create",
            tag,
            "--repo",
            REPOSITORY,
            "--target",
            target,
            "--draft",
            "--title",
            "Qwen2.5 base models for SmartEvent demo",
            "--notes-file",
            str(notes),
        )
        current = api(f"repos/{REPOSITORY}/releases/tags/{tag}")
    if MARKER not in current.get("body", ""):
        raise ValueError("Release tag belongs to a different publication")
    if not current["draft"]:
        raise ValueError("Release is already public; refusing to alter its assets")
    return current


def upload(path: Path, tag: str, release_id: int) -> dict:
    expected = {"name": path.name, "size": path.stat().st_size, "sha256": digest(path)}
    existing = {
        a["name"]: a for a in api(f"repos/{REPOSITORY}/releases/{release_id}/assets?per_page=100")
    }
    if path.name not in existing:
        print(f"Uploading {path.name}: {expected['size']} bytes", flush=True)
        gh("release", "upload", tag, str(path), "--repo", REPOSITORY)
    for attempt in range(5):
        assets = {
            a["name"]: a
            for a in api(f"repos/{REPOSITORY}/releases/{release_id}/assets?per_page=100")
        }
        asset = assets.get(path.name, {})
        if (
            asset.get("size") == expected["size"]
            and asset.get("digest") == "sha256:" + expected["sha256"]
        ):
            return {**expected, "url": asset["browser_download_url"]}
        if path.name in existing:
            break
        if attempt < 4:
            time.sleep(2)
    raise ValueError(
        "Remote asset failed digest verification; release remains a draft: " + path.name
    )


def publish(source_path: Path, work: Path, tag: str, target: str) -> str:
    if os.environ.get("GITHUB_REPOSITORY", REPOSITORY) != REPOSITORY:
        raise ValueError("Publication is restricted to the project repository")
    source = json.loads(source_path.read_text("utf-8"))
    validate_source(source)
    safe_name(tag)
    work.mkdir(parents=True, exist_ok=False)
    current = release(tag, target, work)
    manifest = {
        "format_version": 1,
        "scope": "smartevent-base-model-mirror",
        "repository": REPOSITORY,
        "tag": tag,
        "models": [],
        "support_files": [],
    }
    for model in source["models"]:
        output_model = {key: model[key] for key in ("key", "repo_id", "revision", "license")}
        output_model["files"] = []
        for file in model["files"]:
            downloaded = work / (model["key"] + "__source__" + file["path"])
            fetch_source(model, file, downloaded)
            record = {
                "path": file["path"],
                "size": downloaded.stat().st_size,
                "sha256": digest(downloaded),
                "parts": [],
            }
            for part, _ in split_file(downloaded, model["key"] + "__" + file["path"], work):
                record["parts"].append(upload(part, tag, current["id"]))
                part.unlink()  # Only this completed, verified staging file is removed.
            output_model["files"].append(record)
            downloaded.unlink()
        manifest["models"].append(output_model)
    notice = work / "NOTICE.txt"
    notice.write_text(
        "Built with Qwen. Unmodified base weights redistributed for the SmartEvent research demo.\n"
        "Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) Alibaba Cloud. All Rights Reserved.\n"
        "Qwen2.5-1.5B-Instruct: Apache-2.0, Copyright 2024 Alibaba Cloud.\n"
        "Qwen2.5-3B-Instruct: non-commercial research/evaluation only under its included LICENSE.\n",
        encoding="utf-8",
    )
    root = Path(__file__).resolve().parents[2]
    for support in (notice, root / "docs/architecture/BASE_MODEL_DISTRIBUTION.md"):
        manifest["support_files"].append(upload(support, tag, current["id"]))
    upload(Path(__file__).with_name("download_base_models.py"), tag, current["id"])
    manifest_path = work / "base-models-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    upload(manifest_path, tag, current["id"])
    gh("release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--latest=false")
    return f"https://github.com/{REPOSITORY}/releases/tag/{tag}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest", type=Path, default=Path("models/base-models-source.json")
    )
    parser.add_argument("--workdir", type=Path)
    parser.add_argument(
        "--start-workflow",
        action="store_true",
        help="Use your gh login to start server-side publication",
    )
    parser.add_argument("--tag", default=TAG)
    parser.add_argument("--target", default=os.environ.get("GITHUB_SHA", "main"))
    args = parser.parse_args()
    if args.start_workflow:
        print(start_workflow(Path(__file__).resolve().parents[2]), flush=True)
    elif args.workdir is None:
        parser.error("--workdir is required unless --start-workflow is selected")
    else:
        print(publish(args.source_manifest, args.workdir, args.tag, args.target), flush=True)
