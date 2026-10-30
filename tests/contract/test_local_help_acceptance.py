"""All local help acceptance queries against freshly rebuilt TEST_ONLY artifacts."""

import importlib.util
from pathlib import Path

import pytest

from knowledge_helpers import NOW, catalog_bytes, source
from smartevent_ai.adapters.outbound.knowledge.artifact_reader import ArtifactKnowledgeStore
from smartevent_ai.adapters.outbound.knowledge.lexical_reader import BM25Retriever
from smartevent_ai.adapters.outbound.knowledge.structure_chunker import StructureChunker
from smartevent_ai.adapters.outbound.knowledge.tokenizer import LocalTokenizer
from smartevent_ai.application.retrieve_policy import RetrievePolicy
from smartevent_ai.application.chat import ChatUseCase
from smartevent_ai.application.models import ChatCommand
from smartevent_ai.adapters.outbound.rule_nlu import RuleBasedVietnameseNLU
from smartevent_ai.domain.errors import ToolUnavailable
from smartevent_ai.domain.knowledge import ChunkingPolicy, digest
from smartevent_ai.tooling.offline_jobs.build_index import build_index
from smartevent_ai.tooling.offline_jobs.evaluate import FrozenArtifacts, FrozenClock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "local_help_builder", ROOT / "scripts/build_local_help.py"
)
assert spec and spec.loader
HELP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(HELP)


@pytest.fixture(scope="module")
def reader(tmp_path_factory):
    from tokenizers import Tokenizer, models, normalizers, pre_tokenizers, trainers

    root = tmp_path_factory.mktemp("help-acceptance")
    texts = [(HELP.SOURCE_ROOT / name).read_text("utf-8") for name in HELP.FILES]
    tokenizer = Tokenizer(models.WordLevel(unk_token="[UNK]"))
    tokenizer.normalizer = normalizers.NFKC()
    tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
    tokenizer.train_from_iterator(texts, trainers.WordLevelTrainer(special_tokens=["[UNK]"]))
    tokenizer_path = root / "tokenizer.json"
    tokenizer.save(str(tokenizer_path))
    records = [
        (
            name,
            source(
                source_id=f"HELP-{index:02d}",
                title=text.splitlines()[0].lstrip("# "),
                content_sha256=digest((HELP.SOURCE_ROOT / name).read_bytes()),
                canonical_uri=f"approved://test/help/{index}",
            ),
        )
        for index, (name, text) in enumerate(zip(HELP.FILES, texts, strict=True), 1)
    ]
    raw_catalog = catalog_bytes(records)
    catalog = root / "catalog.json"
    catalog.write_bytes(raw_catalog)
    output = root / "build"
    manifest = build_index(
        HELP.SOURCE_ROOT,
        catalog,
        digest(raw_catalog),
        output,
        StructureChunker(
            LocalTokenizer(
                tokenizer_path,
                digest(tokenizer_path.read_bytes()),
                "TEST_ONLY/help-wordlevel",
                "fixture-v1",
                512,
            ),
            ChunkingPolicy(256, 32),
        ),
        "TEST_ONLY_help_regression",
        NOW,
    )
    artifacts = FrozenArtifacts(
        raw_catalog,
        digest(raw_catalog),
        (output / "release.json").read_bytes(),
        manifest["release_sha256"],
    )
    return RetrievePolicy(
        ArtifactKnowledgeStore(artifacts, allow_test=True),
        BM25Retriever(),
        FrozenClock(NOW),
        limit=1,
    )


@pytest.mark.parametrize("query,source_id,expected", HELP.CASES)
def test_every_prepare_query_has_expected_source_and_content(reader, query, source_id, expected):
    answer = reader.answer(query)
    assert answer.citations and answer.citations[0].source_id == source_id
    assert expected.casefold() in answer.answer.casefold()


@pytest.mark.parametrize(
    "query",
    [
        "Còn blockchain lượng tử thì sao?",
        "Còn ApplePay thì sao?",
        "Làm thế nào để thanh toán bằng ApplePay?",
    ],
)
def test_question_scaffolding_cannot_make_absent_topics_answerable(reader, query):
    assert not reader.answer(query).citations


@pytest.mark.parametrize("query,source_id,expected", HELP.CASES)
def test_prepare_queries_route_to_the_right_corpus_source(
    reader, monkeypatch, query, source_id, expected
):
    import asyncio

    class Policies:
        async def answer(self, question):
            return reader.answer(question)

    class DisabledTools:
        async def execute(self, *_):
            raise ToolUnavailable("No live business tools in acceptance fixture")

    async def inline(function, *args):
        return function(*args)

    async def inline_deadline(coroutine, **_):
        return await coroutine

    # Exercise application routing without replacing retrieval or evidence checks.
    # Only thread/deadline scheduling is stubbed, so this is not an HTTP test.
    monkeypatch.setattr(asyncio, "to_thread", inline)
    monkeypatch.setattr(asyncio, "wait_for", inline_deadline)
    coroutine = ChatUseCase(RuleBasedVietnameseNLU(), DisabledTools(), policies=Policies()).handle(
        ChatCommand(message=query)
    )
    with pytest.raises(StopIteration) as result:
        coroutine.send(None)
    answer = result.value.value
    assert answer.grounding.value == "APPROVED_CORPUS"
    assert answer.citations and answer.citations[0].source_id == source_id
    assert expected.casefold() in answer.answer.casefold()
