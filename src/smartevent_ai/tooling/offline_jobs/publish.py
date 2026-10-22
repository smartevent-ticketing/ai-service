"""Publish verified immutable builds; never edit runtime gates/configuration."""

import argparse
import json
import os
import tempfile
from pathlib import Path

from smartevent_ai.adapters.outbound.knowledge.contracts import (
    canonical_json,
    decode_json,
    parse_release,
    read_bytes,
)
from smartevent_ai.domain.knowledge import KnowledgeError, digest


def publish(build: Path, root: Path) -> dict[str, str]:
    manifest = decode_json(read_bytes(build / "BUILD_MANIFEST.json", 32768))
    release = read_bytes(build / "release.json", 16000000)
    chunks = read_bytes(build / "chunks.jsonl", 16000000)
    if manifest.get("release_sha256") != digest(release) or manifest.get("chunks_sha256") != digest(
        chunks
    ):
        raise KnowledgeError("Build checksum mismatch")
    record = parse_release(release)
    if record.purpose != manifest.get("purpose"):
        raise KnowledgeError("Build purpose mismatch")
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / digest(release)
    if target.exists():
        if read_bytes(target / "release.json", 16000000) != release:
            raise KnowledgeError("Immutable publication collision")
    else:
        with tempfile.TemporaryDirectory(prefix=".publish-stage-", dir=root) as staging:
            staged = Path(staging) / "release"
            staged.mkdir()
            (staged / "release.json").write_bytes(release)
            (staged / "BUILD_MANIFEST.json").write_bytes(canonical_json(manifest))
            staged.rename(target)
    pointer = dict(
        release_path=f"{target.name}/release.json",
        release_sha256=digest(release),
        purpose=record.purpose,
    )
    with tempfile.NamedTemporaryFile(
        prefix=".current-", suffix=".json", dir=root, delete=False
    ) as f:
        temporary = Path(f.name)
        f.write(canonical_json(pointer))
    try:
        os.replace(temporary, root / "CURRENT.json")
    finally:
        temporary.unlink(missing_ok=True)
    return pointer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(publish(args.build, args.root), sort_keys=True))


if __name__ == "__main__":
    main()
