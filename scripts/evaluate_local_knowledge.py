"""Measure real embeddings on approved local sources; keep failed modes disabled."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from build_local_help import CASES
from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.embedding_adapter import LocalOnnxEmbeddings
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.application.retrieve_policy import RetrievePolicy
from smartevent_ai.domain.knowledge import digest, eligible_chunks, fingerprint
from smartevent_ai.infrastructure.knowledge_config import ReviewedRagConfig, SystemClock
from smartevent_ai.infrastructure.knowledge_runtime import RuntimeArtifacts

HELD_OUT = (
    ("Hỏi cách tải ảnh JPG lên sự kiện", "HELP-05"),
    ("Người tổ chức chỉnh sửa ảnh khi sự kiện ở trạng thái nào", "HELP-05"),
    ("Muốn xem đơn hàng và vé đã mua cần đăng nhập ở đâu", "HELP-04"),
    ("Chatbot có cung cấp vé của tài khoản khác không", "HELP-04"),
    ("Các bước đặt vé trên SmartEvent", "HELP-02"),
    ("Bot có giữ chỗ và đặt vé thay người mua không", "HELP-02"),
    ("Tìm sự kiện đã công bố ở thành phố khác", "HELP-03"),
    ("Sự kiện nháp có được hiển thị công khai không", "HELP-03"),
    ("Có dùng PayPal hoặc chuyển khoản trên SmartEvent được không", "HELP-01"),
    ("SmartEvent hiện tích hợp cổng VNPay phải không", "HELP-01"),
)
NEGATIVE_DEV = (
    "Thiên hà lượng tử ở hành tinh nào",
    "Công thức nấu phở bò",
    "Dự báo thời tiết bão biển",
    "Giải phương trình vi phân",
)
NEGATIVE_TEST = (
    "Vắc xin sốt xuất huyết",
    "Cấu tạo phân tử nước",
    "Lập trình bộ điều khiển robot",
    "Động cơ tàu vũ trụ",
)


def evaluate(config: Path, models: Path, output: Path) -> None:
    profile = json.loads((models / "profile.json").read_text())
    counter = LocalTokenizer(
        models / "tokenizer.json",
        profile["tokenizer_sha256"],
        profile["tokenizer_model_id"],
        profile["tokenizer_revision"],
        profile["context_window"],
    )
    encoder = LocalOnnxEmbeddings(
        models / "onnx/model_quantized.onnx",
        profile["model_sha256"],
        profile["model_id"],
        profile["revision"],
        counter,
        384,
    )
    store = ArtifactKnowledgeStore(RuntimeArtifacts(ReviewedRagConfig(config)))
    clock = SystemClock()
    snapshot = store.snapshot(clock.now())
    chunks = eligible_chunks(snapshot, clock.now())
    vectors = np.asarray([encoder.embed(c.context + c.text) for c in chunks])
    queries = (
        [q for q, _, _ in CASES] + [q for q, _ in HELD_OUT] + list(NEGATIVE_DEV + NEGATIVE_TEST)
    )
    scores = {q: vectors @ np.asarray(encoder.embed(q, query=True)) for q in queries}
    # Calibrate on development negatives only; held-out queries are not used here.
    threshold = min(1.0, max(float(max(scores[q])) for q in NEGATIVE_DEV) + 0.005)

    class Retriever:
        def __init__(self, mode):
            self.mode = mode

        def rank(self, query, eligible, limit):
            lexical = BM25Retriever().rank(query, eligible, max(limit, 5))
            if self.mode == "bm25":
                return lexical[:limit]
            allowed = {c.chunk_id for c in eligible}
            dense = [
                chunks[i]
                for i in np.argsort(-scores[query])
                if chunks[i].chunk_id in allowed and scores[query][i] >= threshold
            ][:20]
            if self.mode == "vector":
                return tuple(dense[:limit])
            weights = {}
            dense_ids = {chunk.chunk_id for chunk in dense}
            for ranking in (tuple(c for c in lexical if c.chunk_id in dense_ids), dense):
                for rank, chunk in enumerate(ranking, 1):
                    weights[chunk.chunk_id] = weights.get(chunk.chunk_id, 0) + 1 / (60 + rank)
            order = sorted(weights, key=lambda key: (-weights[key], key))
            by_id = {c.chunk_id: c for c in eligible}
            return tuple(by_id[key] for key in order[:limit])

    metrics = {}
    for mode in ("bm25", "vector", "hybrid"):
        reader = RetrievePolicy(store, Retriever(mode), clock, limit=1)
        rows = []
        for query, expected in [(q, source) for q, source, _ in CASES] + list(HELD_OUT):
            answer = reader.answer(query)
            actual = answer.citations[0].source_id if answer.citations else None
            rows.append(
                {
                    "query": query,
                    "expected": expected,
                    "actual": actual,
                    "passed": actual == expected,
                }
            )
        negatives = [not reader.answer(q).citations for q in NEGATIVE_TEST]
        negative_dev = [not reader.answer(q).citations for q in NEGATIVE_DEV]
        metrics[mode] = {
            "dev_pass": sum(r["passed"] for r in rows[: len(CASES)]),
            "dev_total": len(CASES),
            "held_out_pass": sum(r["passed"] for r in rows[len(CASES) :]),
            "held_out_total": len(HELD_OUT),
            "held_out_negative_pass": sum(negatives),
            "held_out_negative_total": len(negatives),
            "dev_negative_pass": sum(negative_dev),
            "dev_negative_total": len(negative_dev),
            "cases": rows,
        }
    hybrid = metrics["hybrid"]
    passed = (
        hybrid["held_out_pass"] >= 9
        and hybrid["held_out_negative_pass"] == 4
        and hybrid["dev_negative_pass"] == 4
        and hybrid["dev_pass"] >= metrics["bm25"]["dev_pass"]
    )
    record = {
        "status": "PASS" if passed else "NOT_PASSED",
        "scope": "owner-approved-local-demo-only",
        "release_id": snapshot.release_id,
        "embedding_profile": fingerprint(encoder.profile),
        "mode": "hybrid",
        "retriever_contract": "dense-qualified-rrf-v1",
        "minimum_similarity": threshold,
        "evidence": "REAL_ONNX_APPROVED_CORPUS_RETRIEVAL",
        "limitations": "17 development and 10 held-out positive questions; 4 held-out negatives. Not production or general semantic quality acceptance.",
        "cases_sha256": fingerprint(
            {
                "dev": CASES,
                "held_out": HELD_OUT,
                "negative_dev": NEGATIVE_DEV,
                "negative_test": NEGATIVE_TEST,
            }
        ),
        "metrics": metrics,
    }
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {
                "status": record["status"],
                "threshold": threshold,
                "metrics": {
                    k: {key: value for key, value in v.items() if key != "cases"}
                    for k, v in metrics.items()
                },
                "record_sha256": digest(output.read_bytes()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.config, args.models, args.output)
