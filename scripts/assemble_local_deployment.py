"""Assemble verified search and an unchanged approved corpus without reminting it."""

import argparse
import asyncio
import json
import shutil
from pathlib import Path

import yaml

from build_local_help import evaluate, dump_yaml
from public_price_search_deployment import PRICE_PROOFS, expected_visibility_requests
from public_search_deployment import source_fingerprint


def assemble(search: Path, help_config: Path, output: Path) -> None:
    report = json.loads((search / "public_search_evidence.json").read_text("utf-8"))
    if (
        report.get("source_sha256") != source_fingerprint()
        or report.get("feature") != "public-price-search"
        or any(report.get("proofs", {}).get(p) is not True for p in PRICE_PROOFS)
        or report.get("child_visibility_requests") != expected_visibility_requests()
        or not report.get("database_snapshot_before")
        or report.get("database_snapshot_before") != report.get("database_snapshot_after")
    ):
        raise ValueError("Search evidence is incomplete or stale")
    if output.exists():
        raise ValueError("Use a new deployment directory")
    shutil.copytree(search, output)
    shutil.copytree(help_config / "knowledge", output / "knowledge")
    shutil.copyfile(help_config / "rag.yaml", output / "rag.yaml")
    gates = yaml.safe_load((output / "implementation_gates.yaml").read_text("utf-8"))
    help_gates = yaml.safe_load((help_config / "implementation_gates.yaml").read_text("utf-8"))
    for name in ("RAG-APPROVED-CORPUS", "RAG-READONLY"):
        gates["gates"][name] = help_gates["gates"][name]
    dump_yaml(output / "implementation_gates.yaml", gates)
    try:
        help_evidence = asyncio.run(evaluate(output))
    except BaseException:
        rag = yaml.safe_load((output / "rag.yaml").read_text("utf-8"))
        rag["enabled"] = False
        dump_yaml(output / "rag.yaml", rag)
        for name in ("RAG-APPROVED-CORPUS", "RAG-READONLY"):
            gates["gates"][name]["status"] = "BLOCKED"
        dump_yaml(output / "implementation_gates.yaml", gates)
        raise
    (output / "help_evidence.json").write_text(
        json.dumps(help_evidence, ensure_ascii=False, indent=2)
    )
    (output / "local_activation.json").write_text(
        json.dumps(
            {
                "scope": "approved-local-demo-only",
                "source_sha256": source_fingerprint(),
                "search": "public-price-search",
                "help_verified": True,
                "business_tools": ["search_events"],
            },
            indent=2,
        )
    )
    print(f"Verified local deployment: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", type=Path, required=True)
    parser.add_argument("--help-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assemble(args.search, args.help_config, args.output)
