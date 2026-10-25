"""Compatibility CLI/import shim (1 release): use scripts/knowledge/knowledge_smoke."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "knowledge" / "knowledge_smoke.py"), run_name="__main__"
    )
else:
    from scripts.knowledge.knowledge_smoke import *  # noqa: F401,F403
