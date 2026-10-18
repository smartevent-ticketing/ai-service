"""Install a wheel with hashed runtime dependencies in an isolated environment."""

from __future__ import annotations

import argparse
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(wheel: Path) -> None:
    wheel = wheel.resolve(strict=True)
    if wheel.is_dir():
        wheels = list(wheel.glob("*.whl"))
        if len(wheels) != 1:
            raise ValueError("Smoke directory must contain exactly one wheel")
        wheel = wheels[0]
    with tempfile.TemporaryDirectory(prefix="smartevent-wheel-") as temporary:
        base = Path(temporary)
        environment = base / "environment"
        working = base / "empty-cwd"
        working.mkdir()
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / (
            "Scripts/python.exe" if (environment / "Scripts").exists() else "bin/python"
        )
        for args in (
            ["--require-hashes", "-r", str(ROOT / "requirements/runtime.lock")],
            ["--no-deps", str(wheel)],
        ):
            subprocess.run(  # noqa: S603 -- fixed interpreter, argument list, trusted local artifact
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", *args],
                check=True,
                timeout=180,
            )
        code = """
from pathlib import Path
import sys
import smartevent_ai
from fastapi.testclient import TestClient
from smartevent_ai.main import app
assert Path(smartevent_ai.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert not Path('configs').exists()
client = TestClient(app)
assert client.get('/health/live').status_code == 200
ready = client.get('/health/ready').json()
assert ready['status'] == 'degraded' and ready['business_tools_enabled'] == []
response = client.post('/api/v1/chat', json={'message': '3 vé dưới 2000 triệu tổng'})
assert response.status_code == 200
assert response.json()['grounding'] == 'NO_LIVE_DATA'
print('Clean-wheel health/readiness/chat smoke PASS')
"""
        subprocess.run([str(python), "-I", "-c", code], cwd=working, check=True, timeout=30)  # noqa: S603


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wheel", type=Path)
    smoke(parser.parse_args().wheel)
