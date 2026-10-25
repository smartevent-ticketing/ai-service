"""Compatibility CLI/import shim (1 release): use scripts/knowledge/export_knowledge_schemas."""

if __name__ == "__main__":
    import runpy
    from pathlib import Path

    runpy.run_path(
        str(Path(__file__).parent / "knowledge" / "export_knowledge_schemas.py"),
        run_name="__main__",
    )
else:
    from scripts.knowledge.export_knowledge_schemas import *  # noqa: F401,F403
