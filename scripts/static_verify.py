"""Compatibility CLI/import shim (1 release): use scripts/verify/static_verify."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(str(Path(__file__).parent / "verify" / "static_verify.py"), run_name="__main__")
else:
    from scripts.verify.static_verify import *  # noqa: F401,F403
