"""Compatibility CLI/import shim (1 release): use scripts/verify/verify_dependency_locks."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "verify" / "verify_dependency_locks.py"), run_name="__main__"
    )
else:
    from scripts.verify.verify_dependency_locks import *  # noqa: F401,F403
