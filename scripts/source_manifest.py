"""Compatibility CLI/import shim (1 release): use scripts/verify/source_manifest."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "verify" / "source_manifest.py"), run_name="__main__"
    )
else:
    from scripts.verify.source_manifest import *  # noqa: F401,F403
