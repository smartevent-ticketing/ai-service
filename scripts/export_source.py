"""Export exactly the verified source manifest into a new directory."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from source_manifest import MANIFEST, ROOT, verify_manifest


def export_source(destination: Path) -> None:
    verify_manifest()
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Source export must use a new directory")
    manifest: dict[str, str] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    destination.mkdir(parents=True)
    for name, expected in manifest.items():
        source = (ROOT / name).resolve(strict=True)
        target = (destination / name).resolve()
        if not source.is_relative_to(ROOT) or not target.is_relative_to(destination):
            raise ValueError("Manifest paths must stay inside source and export roots")
        data = source.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("Source changed during export")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / MANIFEST.name).write_bytes(MANIFEST.read_bytes())
    print(f"Verified source exported: {len(manifest)} files")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    export_source(parser.parse_args().destination)
