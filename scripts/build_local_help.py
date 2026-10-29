"""Build and verify the explicitly owner-approved local help corpus, with pinned artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from smartevent_ai.adapters.outbound.knowledge.contracts import canonical_json
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.domain.knowledge import ChunkingPolicy, digest
from smartevent_ai.infrastructure.knowledge_config import ReviewedRagConfig
from smartevent_ai.infrastructure.knowledge_runtime import RuntimePolicyReader
from smartevent_ai.tooling.knowledge.build_index import build_index

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "datasets/help_review_2026_10_30"
FILES = (
    "01_payment_methods.md",
    "02_booking_guide.md",
    "03_event_search.md",
    "04_ticket_account_help.md",
    "05_organizer_images.md",
)
CASES = (
    ("Có những cách thanh toán nào", "HELP-01", "VNPay"),
    ("Co nhung cach thanh toan nao", "HELP-01", "VNPay"),
    ("Thanh toán bằng gì", "HELP-01", "VNPay"),
    ("Làm thế nào để thanh toán", "HELP-01", "VNPay"),
    ("Cho mình hỏi có những phương thức thanh toán nào vậy", "HELP-01", "VNPay"),
    ("Có hỗ trợ MoMo không", "HELP-01", "Chưa"),
    ("Còn MoMo thì sao?", "HELP-01", "Chưa"),
    ("ZaloPay có dùng được không?", "HELP-01", "Chưa"),
    ("SmartEvent có hỗ trợ ZaloPay không", "HELP-01", "Chưa"),
    ("Hướng dẫn đặt vé", "HELP-02", "Mở trang sự kiện"),
    ("Tôi đặt vé như thế nào", "HELP-02", "Mở trang sự kiện"),
    ("Làm sao tìm được sự kiện phù hợp", "HELP-03", "thành phố"),
    ("Vì sao sự kiện nháp không xuất hiện", "HELP-03", "nháp"),
    ("Tôi xem đơn hàng và vé đã mua ở đâu", "HELP-04", "Đăng nhập"),
    ("Có chính sách hoàn tiền chung cho mọi vé không", "HELP-04", "không quy định"),
    ("Có thể tải ảnh định dạng nào", "HELP-05", "10 MB"),
    ("Ảnh bìa kích thước bao nhiêu", "HELP-05", "1080"),
)


def dump_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


async def evaluate(config: Path) -> dict:
    from fastapi.testclient import TestClient
    from smartevent_ai.adapters.inbound.http_api import create_app
    from smartevent_ai.infrastructure.settings import Settings

    reader = RuntimePolicyReader(ReviewedRagConfig(config))
    assert reader.status() == "ready"
    checks = []
    for query, expected_source, expected_text in CASES:
        answer = await reader.answer(query)
        assert answer.citations and answer.citations[0].source_id == expected_source, (
            query,
            [c.source_id for c in answer.citations],
            answer.answer,
        )
        assert expected_text.casefold() in answer.answer.casefold(), (query, answer.answer)
        checks.append({"query": query, "source": expected_source, "passed": True})
    assert not (await reader.answer("blockchain lượng tử liên hành tinh")).citations
    with TestClient(
        create_app(Settings(config_dir=config, app_env="development", _env_file=None))
    ) as client:
        for query, expected_source, _ in CASES:
            reply = client.post("/api/v1/chat", json={"message": query}).json()
            assert reply["grounding"] == "APPROVED_CORPUS", (query, reply)
            assert reply["citations"][0]["source_id"] == expected_source
        for query in ("Đơn của tôi đã thanh toán chưa", "Xem vé của tôi", "Xem đơn hàng của tôi"):
            reply = client.post("/api/v1/chat", json={"message": query}).json()
            assert reply["grounding"] == "NO_LIVE_DATA" and not reply["citations"]
    # Independent copied configurations exercise failure paths without changing deployment files.
    with tempfile.TemporaryDirectory() as temporary:
        clone = Path(temporary) / "config"
        shutil.copytree(config, clone)
        rag = yaml.safe_load((clone / "rag.yaml").read_text("utf-8"))
        catalog_path = clone / rag["catalog_path"]
        original_catalog = catalog_path.read_bytes()
        catalog = json.loads(original_catalog)
        for item in catalog["sources"]:
            item["metadata"]["status"] = "revoked"
        catalog_path.write_bytes(canonical_json(catalog))
        rag["catalog_sha256"] = digest(catalog_path.read_bytes())
        dump_yaml(clone / "rag.yaml", rag)
        denied = RuntimePolicyReader(ReviewedRagConfig(clone))
        assert denied.status() == "unavailable"
        assert not (await denied.answer("thanh toán")).citations
        catalog_path.write_bytes(original_catalog)
        rag["catalog_sha256"] = digest(original_catalog)
        dump_yaml(clone / "rag.yaml", rag)
        expired = json.loads(original_catalog)
        expired["issued_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        expired["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        catalog_path.write_bytes(canonical_json(expired))
        rag["catalog_sha256"] = digest(catalog_path.read_bytes())
        dump_yaml(clone / "rag.yaml", rag)
        assert denied.status() == "unavailable"
        assert not (await denied.answer("thanh toán")).citations
        catalog_path.write_bytes(original_catalog)
        rag["catalog_sha256"] = digest(original_catalog)
        dump_yaml(clone / "rag.yaml", rag)
        gate_path = clone / "implementation_gates.yaml"
        gates = yaml.safe_load(gate_path.read_text("utf-8"))
        gates["gates"]["RAG-READONLY"]["status"] = "BLOCKED"
        dump_yaml(gate_path, gates)
        assert denied.status() == "unavailable"
        assert not (await denied.answer("thanh toán")).citations
        gates["gates"]["RAG-READONLY"]["status"] = "PASS"
        dump_yaml(gate_path, gates)
        release_path = clone / rag["release_path"]
        release_path.write_bytes(release_path.read_bytes() + b" ")
        assert denied.status() == "unavailable"
        assert not (await denied.answer("thanh toán")).citations
    return {
        "cases": checks,
        "no_match": True,
        "revocation": True,
        "blocked_gate": True,
        "tampered_release": True,
        "expired_catalog": True,
        "http_routing": True,
        "private_queries_not_retrieved": True,
    }


def build(output: Path, search_config: Path | None = None) -> None:
    from public_search_deployment import source_fingerprint
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, trainers

    approval_bytes = (SOURCE_ROOT / "approval.json").read_bytes()
    approval = json.loads(approval_bytes)
    now = datetime.now(UTC)
    approved_at = datetime.fromisoformat(approval["approved_at"])
    review_due = datetime.fromisoformat(approval["review_due_at"])
    if (
        approval["status"] != "approved"
        or approval["scope"] != "local-demo-help-only"
        or approval["user_confirmation"] != "Duyệt dùng cho demo local"
        or not approved_at <= now < review_due
        or {s["path"] for s in approval["sources"]} != set(FILES)
    ):
        raise ValueError("Missing or expired owner approval")
    approved_hashes = {s["path"]: s["sha256"] for s in approval["sources"]}
    texts = []
    for filename in FILES:
        raw = (SOURCE_ROOT / filename).read_bytes()
        if digest(raw) != approved_hashes[filename]:
            raise ValueError("Reviewed source changed; new owner review required")
        texts.append(raw.decode("utf-8"))
    if output.exists():
        raise ValueError("Output directory must be new")
    if search_config:
        search_evidence = json.loads(
            (search_config / "public_search_evidence.json").read_text("utf-8")
        )
        if search_evidence["source_sha256"] != source_fingerprint():
            raise ValueError("Search deployment evidence is stale; run the live verifier first")
    shutil.copytree(search_config or ROOT / "configs", output / "configs")
    config = output / "configs"
    knowledge = config / "knowledge"
    knowledge.mkdir()
    tokenizer = Tokenizer(models.WordLevel(unk_token="[UNK]"))  # noqa: S106 - vocabulary sentinel
    tokenizer.normalizer = normalizers.NFKC()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.train_from_iterator(texts, trainers.WordLevelTrainer(special_tokens=["[UNK]"]))
    tokenizer_path = knowledge / "tokenizer.json"
    tokenizer.save(str(tokenizer_path))
    sources = []
    for index, (filename, text) in enumerate(zip(FILES, texts, strict=True), 1):
        sources.append(
            {
                "path": filename,
                "metadata": {
                    "source_id": f"HELP-{index:02d}",
                    "version": "1.0.0-local",
                    "title": text.splitlines()[0].lstrip("# "),
                    "canonical_uri": f"approved://smartevent/local-help/{filename[:-3]}",
                    "content_sha256": approved_hashes[filename],
                    "status": "approved",
                    "audience": "customer_public",
                    "approved_at": approval["approved_at"],
                    "effective_from": approval["approved_at"],
                    "effective_until": review_due.isoformat(),
                    "review_due_at": review_due.isoformat(),
                    "owner": approval["owner"],
                    "reviewer": approval["reviewer"],
                    "approval_id": approval["approval_id"],
                    "locale": "vi-VN",
                },
            }
        )
    catalog = {
        "format_version": 1,
        "purpose": "PRODUCTION",
        "issued_at": now.isoformat(),
        "expires_at": min(now + timedelta(days=7), review_due).isoformat(),
        "approval_ref": approval["approval_id"],
        "sources": sources,
    }
    catalog_path = knowledge / "catalog.json"
    catalog_path.write_bytes(canonical_json(catalog))
    counter = LocalTokenizer(
        tokenizer_path,
        digest(tokenizer_path.read_bytes()),
        "smartevent-local-help-wordlevel",
        "owner-reviewed-v1",
        512,
    )
    manifest = build_index(
        SOURCE_ROOT,
        catalog_path,
        digest(catalog_path.read_bytes()),
        knowledge / "build",
        StructureChunker(counter, ChunkingPolicy(256, 32)),
        source_fingerprint(),
        now,
    )
    rag = yaml.safe_load((config / "rag.yaml").read_text("utf-8"))
    rag.update(
        enabled=True,
        catalog_path="knowledge/catalog.json",
        catalog_sha256=digest(catalog_path.read_bytes()),
        release_path="knowledge/build/release.json",
        release_sha256=manifest["release_sha256"],
        max_catalog_age_seconds=604800,
        max_results=1,
    )
    dump_yaml(config / "rag.yaml", rag)
    gates = yaml.safe_load((config / "implementation_gates.yaml").read_text("utf-8"))
    for name in ("RAG-APPROVED-CORPUS", "RAG-READONLY"):
        gates["gates"][name]["status"] = "PASS"
        gates["gates"][name]["scope"] = (
            "Owner-approved local help corpus only; not production release"
        )
        gates["gates"][name]["approval_id"] = approval["approval_id"]
    dump_yaml(config / "implementation_gates.yaml", gates)
    try:
        before = (
            digest(catalog_path.read_bytes()),
            digest((knowledge / "build/release.json").read_bytes()),
        )
        report = asyncio.run(evaluate(config))
        after = (
            digest(catalog_path.read_bytes()),
            digest((knowledge / "build/release.json").read_bytes()),
        )
        assert before == after
    except BaseException:
        rag["enabled"] = False
        dump_yaml(config / "rag.yaml", rag)
        for name in ("RAG-APPROVED-CORPUS", "RAG-READONLY"):
            gates["gates"][name]["status"] = "BLOCKED"
        dump_yaml(config / "implementation_gates.yaml", gates)
        raise
    report.update(
        scope="local-demo-help-only",
        approval_sha256=digest(approval_bytes),
        source_sha256=source_fingerprint(),
        corpus_readonly=True,
        retrieval_backend="bm25",
        vector_store=None,
        expires_at=catalog["expires_at"],
        evaluated_at=now.isoformat(),
    )
    (config / "help_evidence.json").write_bytes(canonical_json(report))
    (knowledge / "approval.json").write_bytes(approval_bytes)
    print(
        f"Verified owner-approved local help: {len(CASES)} questions plus negative cases. Config: {config}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--search-config", type=Path)
    arguments = parser.parse_args()
    build(arguments.output, arguments.search_config)
