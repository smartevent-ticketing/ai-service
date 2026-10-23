"""Importing the inbound adapter must not build the app or touch the filesystem."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run_child(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv, no shell, test-only probe
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=120,
    )


def test_import_http_api_has_no_app_or_filesystem_side_effects() -> None:
    probe = (
        "import sys; sys.path.insert(0, 'src'); "
        "import smartevent_ai.adapters.inbound.http_api as m; "
        "assert not hasattr(m, 'app'), 'import-time app still exists'; "
        "assert 'smartevent_ai.infrastructure.bootstrap' not in sys.modules; "
        "assert 'tokenizers' not in sys.modules; "
        "assert 'onnxruntime' not in sys.modules; "
        "print('no-import-side-effects OK')"
    )
    result = _run_child(probe)
    assert result.returncode == 0, result.stderr
    assert "no-import-side-effects OK" in result.stdout
