"""Verify every historical source hash and internal runtime-doc relative links."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs/contexts/v1.2"
expected = json.loads((ROOT / "docs/contexts/V1_2_FILE_HASHES.json").read_text(encoding="utf-8"))
actual = {
    p.relative_to(SRC).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in SRC.rglob("*")
    if p.is_file()
    and p.name != "SOURCE_SHA256.txt"
    and "__pycache__" not in p.parts
    and p.suffix != ".pyc"
}
if actual != expected or len(actual) != 49:
    raise SystemExit("Historical v1.2 snapshot changed or incomplete")
for path in [ROOT / "README.md", ROOT / "AGENTS.md", *ROOT.glob("docs/architecture/*.md")]:
    raw = path.read_text(encoding="utf-8")
    for link in re.findall(r"(?<!!)\[[^]]+\]\(([^)]+)\)", raw):
        if link.startswith(("https://", "http://", "#")):
            continue
        if not (path.parent / link.split("#", 1)[0]).exists():
            raise SystemExit(f"Broken link in {path}: {link}")
print(f"Immutable v1.2 SHA-256 verified: {len(actual)} files; authored links OK")
