"""Compatibility CLI/import shim (1 release): use scripts/verify/verify_runtime_config_sync."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "verify" / "verify_runtime_config_sync.py"), run_name="__main__"
    )
else:
    from scripts.verify.verify_runtime_config_sync import *  # noqa: F401,F403
