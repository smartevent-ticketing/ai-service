# Thiết kế kiến trúc SmartEvent AI Service — In-place hardening + pattern offline

- Ngày: 2026-10-23
- Phạm vi đã duyệt: cấu trúc + pattern offline (không gọi SaaS live, không thêm capability runtime mới)
- Hướng đã chọn: In-place hardening — giữ nguyên tên layer và chiều phụ thuộc
- Nguồn: map 6 vùng local + survey 5 repo (`aifabrice/jev-rag`, `ajanm007/jevrag`, `breaker364/jev-rag-gate`, `pinecone-io/using-typesafe-and-pinecone`, `spring-ai-community/spring-ai-typesafe`)

> [!CAUTION]
> File dirty `docs/contexts/v1.2/schemas/training_sample.schema.json` (thêm `synthetic_unreviewed`)
> là vi phạm P0, xử lý revert riêng — KHÔNG thuộc spec này, KHÔNG commit cùng.

## 1. Mục tiêu, ràng buộc bất biến, tiêu chí thành công

### 1.1. Mục tiêu

Sửa 9 điểm cấu trúc đã phát hiện tại chỗ, cộng 3 pattern offline-safe từ 5 repo mẫu,
tất cả triển khai sau ports hiện có. Không gọi SaaS live, không thêm capability runtime mới.

### 1.2. Ràng buộc bất biến (không thương lượng)

1. `docs/contexts/v1.2/` bất biến — mọi đính chính sang `docs/architecture/`.
2. Clean Architecture giữ nguyên: `domain` stdlib-only; `application` chỉ phụ thuộc
   domain + ports; `adapters`/`infrastructure` ôm FastAPI/Pydantic/HTTPX/YAML
   (do `scripts/static_verify.py` enforce).
3. Business HTTP GET-only trên named registry paths; tool mặc định tắt;
   `SPEC_TEST_ONLY`/`BLOCKED`/`NOT_RUN` không phải `PASS`.
4. Không đưa raw backend JSON, QR/token, PII vào model context hoặc log.
5. `configs/` là source of truth; fallback `src/smartevent_ai/resources/`
   phải byte-identical; `scripts/verify_runtime_config_sync.py` vẫn pass.
6. Mọi thay đổi behavior kèm test cập nhật + regen source manifest
   (`python scripts/source_manifest.py` rồi `--verify`).

### 1.3. Tiêu chí thành công

`static_verify.py`, `verify_runtime_config_sync.py`, `verify_contexts.py`,
`source_manifest.py --verify`, `ruff check`, `ruff format --check`, `mypy`,
`pytest --cov-fail-under=90`, wheel smoke, Docker smoke đều pass; không còn
dual-validation drift (chunking); không còn import-time IO trong `adapters`;
`scripts/` + `tests/` chia package map được với CI gates; 3 pattern mới chỉ chạy
offline sau ports, có negative tests.

## 2. Components (sửa tại chỗ, tới từng file)

### C1. Chunking single-source — hết drift `ChunkingPolicy` vs `ChunkProfile`

- `src/smartevent_ai/domain/knowledge.py:122` — `ChunkingPolicy` là single source
  of truth cho bound (`max_tokens` 32..4096, `overlap < max_tokens//2`,
  `max_chunks`, `algorithm`).
- `src/smartevent_ai/adapters/outbound/knowledge/contracts.py:120` — `ChunkProfile`
  chuyển thành view dẫn xuất: bỏ bound check riêng, thêm
  `ChunkProfile.from_policy(policy, normalization, tokenizer_profile)`;
  `TokenizerProfile` giữ nguyên.
- `src/smartevent_ai/adapters/outbound/knowledge/structure_chunker.py:69` —
  property `profile` gọi `from_policy`, bỏ dựng dict thủ công
  `{**asdict(policy), ...}`.
- `src/smartevent_ai/adapters/outbound/knowledge/artifact_reader.py:62` — bỏ
  reconstruct + re-validate rời rạc; gọi cùng một `from_policy` rồi so `fingerprint`.
- `src/smartevent_ai/tooling/knowledge/build_index.py:67,82` (sau rename: xem C5) —
  CLI args `max_tokens`/`overlap` chỉ feed vào `ChunkingPolicy(...)`, không tự check bound.
- Dedupe kèm theo: `canonical_json` (`contracts.py:213`) vs `fingerprint`
  (`domain/knowledge.py:35`) — giữ một hàm duy nhất ở domain, adapter reuse;
  `build_index.py:53+56` bỏ double-load (`loader.load` 2 lần/source).

### C2. Config sync — hết dual-edit thủ công, vẫn byte-identical

- `configs/` giữ là source of truth duy nhất cho tay người sửa.
- Thêm `scripts/sync_configs_to_resources.py` copy một chiều
  `configs/` → `src/smartevent_ai/resources/` (chạy trong dev setup + build hook,
  mặc định `--check` chỉ báo diff, chỉ `--write` khi gọi rõ).
  `scripts/verify_runtime_config_sync.py` giữ nguyên làm gate CI (CI chỉ verify,
  không auto-write).
- `pyproject.toml` `[tool.setuptools.package-data]` giữ nguyên; không sửa tay
  `resources/` nữa.

### C3. Import-time app — factory thuần, IO dồn về entrypoint

- `src/smartevent_ai/adapters/inbound/http_api.py:179` — xóa
  `app = create_app()` ở import-time, chỉ giữ `def create_app(settings=None)`.
- `src/smartevent_ai/main.py` — thành nơi duy nhất gọi `app = create_app()`
  (composition tại entrypoint; `uvicorn smartevent_ai.main:app` không đổi).
- `tests/test_http.py:5`, `tests/conftest.py` — chuyển sang fixture `create_app()`
  thay vì build ở collection-time; inbound không import
  `infrastructure.bootstrap` lúc module load (inject qua tham số factory).

### C4. Unused tool surface — khóa thay vì xóa registry

- `configs/runtime_tool_registry.yaml` (14 tools) giữ nguyên làm hợp đồng;
  không thêm caller mới.
- `src/smartevent_ai/application/chat.py:75` — giữ explicit call duy nhất
  `search_events`; `pure_operations` (`retrieve_policy`, `optimize_ticket_selection`)
  và `ui_actions` ghi rõ "chưa có caller" trong comment + docs.
- Thêm negative test: mọi tool không có caller trong `src/` bắt buộc
  `enabled: false` (chống bật nhầm); `recommend()` trong
  `domain/recommendation.py` (hiện zero caller) hoặc nối vào use-case sau, hoặc
  đánh dấu explicit-dead — không để hàm ranking treo không ai gọi.
- Dedupe kèm: `is_side_effect_route` chỉ sống ở `route_policy.py`,
  `safe_transport.py:44` và `read_only_gateway.py:274` reuse;
  visibility `PUBLISHED`-filter chỉ một nơi (gateway `_project_row`), bỏ bản trùng
  ở `project()`; JSON depth/nonfinite check thống nhất một bound
  (hiện 64 vs 24 ở `safe_transport` vs `contracts.decode_json`).

### C5. Flat `scripts/` + `tests/` — chia package, đổi tên cây knowledge trùng

- `scripts/` → `scripts/verify/` (`static_verify`, `verify_contexts`,
  `verify_runtime_config_sync`, `verify_dependency_locks`), `scripts/knowledge/`
  (`split_dataset`, `knowledge_smoke`, `export_knowledge_schemas`),
  `scripts/release/` (`export_source`, `source_manifest`, `wheel_smoke`).
  Giữ shim file cũ re-export 1 dòng trong 1 release để
  `.github/workflows/ci.yml` không vỡ ngay.
- `tests/` → `tests/unit/` (chat, domain, nlu, split), `tests/contract/` (http,
  gateway, transport, all_tool_contracts, knowledge_*), `tests/security/`
  (telemetry, regressions, distribution, policy_chat). `conftest.py` +
  `knowledge_helpers.py` lên `tests/support/`.
- `src/smartevent_ai/tooling/knowledge/` → `src/smartevent_ai/tooling/offline_jobs/`
  (`build_index`, `evaluate`, `publish`, `benchmark_semantic`);
  `adapters/outbound/knowledge/` giữ nguyên tên (runtime readers) — hết nhầm
  writer vào runtime. Cập nhật `static_verify.py` allowlist `tooling` theo path mới.

### C6. Lockfile + docs — một nguồn, không pin tay 3 nơi

- `uv.lock` là single source; `requirements/runtime.lock`, `dev.lock`, `rag.lock`
  chỉ là output của `uv export` (đã có `verify_dependency_locks.py` enforce) —
  cấm sửa tay; xóa `requirements/dev.txt` hoặc gen tự động từ cùng nguồn.
- `pyproject.toml` — `tokenizers`/`numpy`/`onnxruntime` đang pin lặp ở `rag-ingest` +
  `rag-semantic` + `dev` group (+ `onnx` chỉ dev dùng): gom về một chỗ khai báo
  version, các extra/group reference lại.
- `README.md` mục "Cấu trúc repository" — viết lại cây thư mục phản ánh
  `tooling/offline_jobs` + `scripts/`/`tests/` package mới
  (hiện vẫn ghi `tooling/` chỉ chia dataset, đã lỗi thời).

## 3. Data flow

### 3.1. Sơ đồ (giữ nguyên hướng offline → artifact bất biến → runtime chỉ đọc)

```text
                OFFLINE (tooling/offline_jobs, không vào HTTP)
corpus drafts ──▶ LocalDocumentLoader ──▶ StructureChunker ──▶ build_index
(datasets/)        (bounded, NFC/LF)      (single-source         (release.json +
                                        ChunkingPolicy)          chunks.jsonl +
                                                                 BUILD_MANIFEST)
      │                                                        │
      │ evaluate (recall/mrr/ndcg/abstain/latency)              │ publish
      │ evidence = OFFLINE_ONLY                                │ (content-addressed
      ▼                                                        │  root/<sha>/ + CURRENT)
benchmark_semantic ◀── (BM25 vs dense vs RRF, ONNX CPU) ──────┘

                RUNTIME (adapters + infrastructure, chỉ đọc)
POST /api/v1/chat ──▶ ChatUseCase ──┬──▶ RuleBasedNLU (LanguageUnderstanding port)
                                    ├──▶ ReadOnlyToolGateway ──▶ SafeBackendTransport
                                    │    (search_events duy nhất;                  GET cố định
                                    │     13 tool còn lại disabled)                 registry
                                    └──▶ RuntimePolicyReader ──▶ ArtifactKnowledgeStore
                                         (status/answer,             (re-hash, expiry,
                                          timeout-bounded)            TEST_ONLY gate,
                                                                      provenance check)
                                                                ──▶ BM25Retriever.rank()
                                                                      (wide pool)
                                                                          │
                                                          ┌── Pattern P1 ───┘
                                                          ▼
                                                    kept / conflicts
                                                    (extractive, cite
                                                     source/version/chunk/
                                                     char-range)
```

### 3.2. Ba pattern offline-safe và vị trí cắm

| Pattern (nguồn) | Cắm sau port nào | Hành vi |
|---|---|---|
| **P1. kept/conflicts split + atomic typed checks** (jev-rag-gate + spring-ai-typesafe: injection/premise-challenge trước relevance/evidence; conflicts giữ làm undercutting evidence có citation) | `EvidenceRetriever` mới trong `application/knowledge_ports.py`; implement stdlib-only ở `domain` (pure functions), gọi từ `retrieve_policy.py` | 4 check nguyên tử theo thứ tự: injection → premise-contradiction → relevance → evidence; verdict `kept`/`conflicts`/`dropped`; conflicts vẫn trích dẫn như bằng chứng phản biện |
| **P2. retrieve-wide → judge-narrow + preset negative groups** (pinecone demo: wide ~200, snippet-only judging, negation/near-empty presets) | Mở rộng `evaluate.py` + `benchmark_semantic.py` offline; runtime `lexical_reader.py` giữ BM25-wide, catalog recheck + parent-context extract như cũ | Thêm preset câu hỏi phủ định/gần-rỗng tiếng Việt vào `tests/fixtures/rag/questions.jsonl`; snippet char-cap + opening-paragraph rule tuân thủ "không cắt điều kiện/ngoại lệ" |
| **P3. execution/scoring split + calibration reporting** (jevrag: ghi JSONL records → eval offline; AURC/ECE/Brier/EM/F1; conformal alpha→threshold chỉ để tune) | Mở rộng `tooling/offline_jobs/evaluate.py` (ghi records) + script analyze riêng (đọc records, in calibration) | Báo cáo AURC/risk-coverage/ECE/MCE cho BM25/ONNX-hybrid; cost/latency accounting + shadow-challenger log không ảnh hưởng kết quả live |

Không làm: gọi Jev/TypeSafe SaaS; dùng threshold 0.45/0.70 của corpus Trung Quốc
(threshold tune trên corpus tiếng Việt duyệt riêng); đưa Pinecone cloud / Typesafe
SaaS / Anthropic baseline / npm-Vercel loop vào runtime; dùng calibration để bật tool
(ECE live ~0.33 đã biết kém; `SPEC_TEST_ONLY`/`BLOCKED`/`NOT_RUN` ≠ `PASS`).

### 3.3. Quy tắc data-flow bất biến

1. Không luồng nào đi từ runtime ngược lên offline (runtime không publish,
   không ghi artifact).
2. P1/P2/P3 chỉ đọc corpus đã duyệt hoặc `TEST_ONLY`; output của chúng là
   evidence/report, không phải gate PASS để bật tool.
3. Mọi check mới của P1 là pure function stdlib-only trong `domain` → test được
   mà không cần HTTP/network/model.

## 4. Error handling

Nguyên tắc: lỗi ở bất kỳ tầng nào cũng trả về câu trả lời an toàn + grounding
trung thực, không bao giờ fail-open thành dữ liệu bịa hoặc bật tool.

### 4.1. Fail-closed map (giữ + bổ sung)

| Tầng | Lỗi | Hành vi |
|---|---|---|
| Inbound | `SmartEventError` bất kỳ | `422 {"code", "message": "Request could not be completed"}` — generic |
| Gateway | Registry/gate invalid, tool disabled, gate ≠ PASS, non-public, side-effect route, schema/projection fail, page inconsistent | `ToolUnavailable` (chưa bật) vs `ContractViolation` (hợp đồng vỡ); `available_names()` rỗng → `/health/ready` `degraded` |
| Transport | Origin sai, path ngoài `/api/v1/`, redirect, byte-cap, depth, nonfinite, envelope sai, timeout 100..10000ms | `BackendUnavailable`; không retry; không credential |
| Knowledge runtime | Digest lệch, hết hạn, `TEST_ONLY` không `allow_test`, synthetic trong PRODUCTION, provenance/token-budget vỡ | `KnowledgeError` → `NO_EVIDENCE` + `NO_LIVE_DATA`; `status()` không `ready` giả |
| NLU | Không hiểu / thiếu slot | `CLARIFY` + `ClarificationReason`, không đoán intent |
| **P1** (mới) | Check crash/timeout | Chunk đó → `dropped`, không vào citation; P1 fail toàn bộ → fallback BM25 thuần + flag `judge_unavailable` |
| **P2** (mới, offline) | Judge-narrow timeout/concurrency-cap (4-wide, 2.0s) | Ghi record `timeout` vào JSONL, không loại chunk khỏi pool thật |
| **P3** (mới, offline) | Scorer đọc JSONL lỗi (thiếu field, NaN) | `evaluation_ready=false`, không in metric nửa vời; conformal threshold chỉ vào report tune |

### 4.2. Timeout / retry / budget

- Runtime: **không retry** (giữ như `SafeBackendTransport`). Timeout duy nhất:
  transport 100..10000ms + `RuntimePolicyReader.answer()` qua
  `asyncio.wait_for(timeout_ms)` → `NO_EVIDENCE`.
- Offline: `evaluate.py` / `benchmark_semantic.py` được retry tối đa 1 lần cho lỗi
  transient; mọi run ghi wall-time + token/cost accounting vào manifest.
- Budget check tập trung một chỗ: `policy.max_tokens ≤ tokenizer.context_window`,
  `chunk.token_count ≤ policy.max_tokens`, per-source `counts ≤ policy.max_chunks` —
  một hàm domain duy nhất, `artifact_reader` và `build_index` cùng gọi.

## 5. Testing

Giữ ngưỡng `pytest -q --cov=smartevent_ai --cov-fail-under=90` và toàn bộ gate CI.
Test mới chứng minh *không vỡ*, không chứng minh *đủ điều kiện bật tool*.

### 5.1. Test cho 6 điểm cấu trúc

| Thay đổi | Test thêm/cập nhật |
|---|---|
| C1 `ChunkProfile.from_policy` | `test_knowledge_contracts.py`: `from_policy` round-trip + `fingerprint` một nguồn; xóa test assert bound riêng của `ChunkProfile` |
| C1 dedupe + bỏ double-load | `test_knowledge_ingestion.py`: `profile_sha256` match sau refactor; đếm `loader.load` đúng 1 lần/source |
| C2 sync một chiều | `test_distribution.py`: chạy sync → diff byte-identical; sửa tay `resources/` vẫn bị phát hiện |
| C3 factory | `test_http.py`/`conftest.py` chuyển fixture `create_app()`; **mới** `test_no_import_side_effects.py`: import `http_api` trong subprocess không chạm filesystem |
| C4 khóa surface | **mới** `test_unused_tools_locked.py`: tool không caller trong `src/` bắt buộc `enabled: false`; `recommend()` hoặc có caller hoặc explicit-dead |
| C4 dedupe route/visibility/JSON | `test_transport.py` + `test_gateway.py`: 3 call-site cũ cùng qua 1 hàm; side-effect route mới vẫn bị chặn cả 3 đường |
| C5 chia package | CI cập nhật path; shim cũ re-export đúng module mới; `static_verify.py` allowlist path mới |
| C6 lockfile | `verify_dependency_locks.py` giữ nguyên (đã enforce `uv export` diff rỗng) |

### 5.2. Test cho 3 pattern offline — negative-first

- **P1** `tests/contract/test_evidence_verdicts.py` (mới): 4 check đúng thứ tự;
  case injection tiếng Việt ("bỏ qua hướng dẫn..."), premise mâu thuẫn, query
  off-topic, evidence thiếu → verdict đúng; check crash → `dropped`, không lọt
  citation; P1 fail toàn bộ → fallback BM25.
- **P2**: mở rộng `tests/fixtures/rag/questions.jsonl` + `test_policy_retrieval.py`:
  preset phủ định, near-empty, snippet-cap không cắt điều kiện/ngoại lệ
  (assert clause còn nguyên trong `answer`).
- **P3**: `test_knowledge_semantic.py` mở rộng: JSONL hỏng → `evaluation_ready=false`;
  assert không có code path nào đọc conformal threshold để set `enabled: true`.

### 5.3. Mapping CI gates (không thêm job mới, chỉ cập nhật path)

```text
compile → static_verify (allowlist tooling/offline_jobs) → Ruff/format → mypy
  → pytest (unit/contract/security, cov ≥ 90)
  → knowledge schemas → lockfile/export drift → config sync (byte-identical)
  → contexts v1.2 immutable → source_manifest --verify
  → pip-audit (runtime + rag) → wheel build + smoke (scripts/release/)
  → Docker build + live/ready smoke (ready vẫn degraded)
```

## 6. Rủi ro và thứ tự triển khai

### 6.1. Rủi ro

| Rủi ro | Mức | Chặn |
|---|---|---|
| Refactor C1/C4 đụng bound đang được test khác assert | Cao | C1/C4 cùng một PR; test cũ sửa cùng commit |
| Xóa `app` import-time làm vỡ `uvicorn smartevent_ai.main:app` hoặc import ngoài | Cao | `main.py` giữ `app = create_app()`; `wheel_smoke.py` + Docker live/ready kiểm chứng |
| Rename `tooling/knowledge` sót reference | Trung bình | PR riêng chỉ rename + shim; cập nhật `static_verify`, CI, README, regen manifest cùng commit |
| Sync script ghi đè sửa tay trong `resources/` | Trung bình | Mặc định `--check`; CI chỉ verify, không auto-write |
| Threshold tune trên corpus draft bị hiểu là bằng chứng bật tool | Cao | Output nhãn `OFFLINE_ONLY`/`evaluation_ready=false`; không code path report → `enabled: true`; test 5.2 khóa bằng assert |
| Chia `scripts/`/`tests/` làm CI path cũ vỡ | Thấp | Shim re-export 1 dòng trong 1 release; CI cập nhật cùng PR |

### 6.2. Thứ tự triển khai (4 PR nhỏ, reviewable)

1. **PR-1 rename + packaging**: `tooling/knowledge` → `offline_jobs`, sync script C2,
   lockfile/docs C6 (mechanical, không đổi behavior).
2. **PR-2 single-source + dedupe**: C1 chunking, C4 unify (đổi behavior validation
   → kèm test 5.1).
3. **PR-3 factory + khóa surface**: C3 import-time app, C4
   `test_unused_tools_locked.py`, chia `scripts/`/`tests/` C5.
4. **PR-4 patterns offline**: P1 kept/conflicts (domain pure + `EvidenceRetriever`
   port), P2 presets + fixtures, P3 execution/scoring split (offline + test 5.2,
   không chạm runtime enablement).

Mỗi PR chạy đủ gate 5.3 + `git status` sạch `docs/contexts/v1.2/`.

---

## Self-review (tác giả tự kiểm trước khi trình reviewer)

- [x] Placeholder scan: không còn TBD/TODO; mọi file/tham chiếu đều có path + dòng cụ thể.
- [x] Internal consistency: C1 single-source khớp 3.3(3) và 4.2 (budget một chỗ);
  C2 `--check`-default khớp rủi ro ghi đè; P1–P3 "offline-only" khớp 3.3(2) và
  test 5.2 (không path nào tới `enabled: true`).
- [x] Scope check: spec gói trong 1 implementation plan (4 PR theo 6.2); P0 revert
  và JEV-live đánh giá nằm ngoài scope, đã ghi rõ.
- [x] Ambiguity check: "giữ shim 1 release" = shim re-export tồn tại cho tới PR
  dọn dẹp sau khi CI xanh, không xóa cùng PR chia package; "sync script" mặc định
  `--write` là opt-in tường minh (người gọi truyền cờ rõ ràng).
