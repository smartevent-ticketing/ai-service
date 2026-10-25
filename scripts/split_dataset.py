"""Compatibility CLI/import shim (1 release): use scripts/knowledge/split_dataset."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "knowledge" / "split_dataset.py"), run_name="__main__"
    )
else:
    from scripts.knowledge.split_dataset import *  # noqa: F401,F403
