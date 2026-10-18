import math
from pathlib import Path

import numpy as np
import pytest
from knowledge_helpers import FIXTURES, NOW, make_bundle, tokenizer
from onnx import TensorProto, helper

from smartevent_ai.adapters.outbound.knowledge.embedding_adapter import LocalOnnxEmbeddings
from smartevent_ai.domain.knowledge import KnowledgeError, digest
from smartevent_ai.tooling.knowledge.benchmark_semantic import benchmark


def tiny_model(path: Path) -> Path:
    # Actual ONNX execution, not an SDK mock: shape [1,T] -> [1,T,3].
    inputs = [
        helper.make_tensor_value_info(name, TensorProto.INT64, [1, "T"])
        for name in ("input_ids", "attention_mask", "token_type_ids")
    ]
    nodes = [
        helper.make_node("Cast", ["input_ids"], ["float_ids"], to=TensorProto.FLOAT),
        helper.make_node("Unsqueeze", ["float_ids"], ["expanded"], axes=[2]),
        helper.make_node("Concat", ["expanded"] * 3, ["last_hidden_state"], axis=2),
    ]
    graph = helper.make_graph(
        nodes,
        "TEST_ONLY_embedding",
        inputs,
        [helper.make_tensor_value_info("last_hidden_state", TensorProto.FLOAT, [1, "T", 3])],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 11)], ir_version=8)
    path.write_bytes(model.SerializeToString())
    return path


def test_actual_onnx_inference_pooling_normalization_and_input_bounds(tmp_path) -> None:
    path = tiny_model(tmp_path / "model.onnx")
    embedding = LocalOnnxEmbeddings(
        path, digest(path.read_bytes()), "TEST_ONLY/tiny", "v1", tokenizer(), 3
    )
    vector = embedding.embed("chính sách hoàn tiền")
    assert len(vector) == 3 and math.isclose(sum(x * x for x in vector), 1, rel_tol=1e-6)
    assert vector == embedding.embed("chính sách hoàn tiền", query=True)
    with pytest.raises(KnowledgeError):
        embedding.embed("chính sách hoàn tiền " * 1000)
    with pytest.raises(KnowledgeError):
        LocalOnnxEmbeddings(path, "0" * 64, "test", "rev", tokenizer(), 3)
    with pytest.raises(KnowledgeError):
        LocalOnnxEmbeddings(path, digest(path.read_bytes()), "", "rev", tokenizer(), 3)
    bad = tmp_path / "bad.onnx"
    bad.write_bytes(b"not onnx")
    with pytest.raises(KnowledgeError):
        LocalOnnxEmbeddings(bad, digest(bad.read_bytes()), "test", "rev", tokenizer(), 3)
    wrong = LocalOnnxEmbeddings(path, digest(path.read_bytes()), "test", "rev", tokenizer(), 2)
    with pytest.raises(KnowledgeError):
        wrong.embed("hoàn tiền")


def test_onnx_invalid_numbers_shape_and_failures(tmp_path) -> None:
    path = tiny_model(tmp_path / "model.onnx")
    embedding = LocalOnnxEmbeddings(
        path, digest(path.read_bytes()), "TEST_ONLY/tiny", "v1", tokenizer(), 3
    )
    length = len(tokenizer().encode("test", "passage: "))

    class FakeSession:
        def __init__(self, result):
            self.result = result

        def run(self, *_):
            if isinstance(self.result, Exception):
                raise self.result
            return [self.result]

    for bad in (np.zeros((1, length, 3)), np.full((1, length, 3), np.nan), ValueError("failure")):
        embedding._session = FakeSession(bad)
        with pytest.raises(KnowledgeError):
            embedding.embed("test")


def test_dense_and_hybrid_benchmark_is_offline_and_filters_private_chunks(tmp_path) -> None:
    _, _, _, artifacts = make_bundle(tmp_path)
    path = tiny_model(tmp_path / "model.onnx")
    embedding = LocalOnnxEmbeddings(
        path, digest(path.read_bytes()), "TEST_ONLY/tiny", "v1", tokenizer(), 3
    )
    result = benchmark(artifacts, FIXTURES / "questions.jsonl", NOW, embedding)
    assert result["runtime_enable_authorized"] is False
    assert result["dimension"] == 3
    assert result["dense_abstention_calibrated"] is False
    assert all(
        "TEST-STAFF@1.0.0" not in r for row in result["results"] for r in row["rankings"].values()
    )


def test_offline_cli_entrypoints(tmp_path, monkeypatch, capsys) -> None:
    import sys
    from smartevent_ai.tooling.knowledge import build_index, evaluate, publish

    catalog, _, _, _ = make_bundle(tmp_path)
    output = tmp_path / "cli-build"
    tok = FIXTURES / "tokenizer.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build",
            "--corpus-root",
            str(FIXTURES),
            "--catalog",
            str(catalog),
            "--catalog-sha256",
            digest(catalog.read_bytes()),
            "--output",
            str(output),
            "--tokenizer",
            str(tok),
            "--tokenizer-sha256",
            digest(tok.read_bytes()),
            "--tokenizer-model",
            "TEST_ONLY/byte-bpe-vi",
            "--tokenizer-revision",
            "fixture-v1",
            "--context-window",
            "512",
            "--source-revision",
            "TEST_ONLY_revision",
        ],
    )
    build_index.main()
    release = output / "release.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--catalog",
            str(catalog),
            "--catalog-sha256",
            digest(catalog.read_bytes()),
            "--release",
            str(release),
            "--release-sha256",
            digest(release.read_bytes()),
            "--cases",
            str(FIXTURES / "questions.jsonl"),
            "--output",
            str(tmp_path / "evaluation.json"),
            "--at",
            NOW.isoformat(),
        ],
    )
    evaluate.main()
    with pytest.raises(KnowledgeError):
        evaluate.main()
    monkeypatch.setattr(sys, "argv", ["publish", str(output), str(tmp_path / "pub")])
    publish.main()
    assert (tmp_path / "pub/CURRENT.json").exists()
    assert "TEST_ONLY" in capsys.readouterr().out
