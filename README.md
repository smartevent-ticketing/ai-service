# SmartEvent AI Service — Clean Architecture Foundation

**Version:** 0.1.2
**Status:** runnable read-only foundation; **not production-ready**. QLoRA, live RAG, JEV, private identity delegation and live SmartEvent business reads remain disabled until their release gates are proven.

## Architectural contract

- **READ_ONLY business behavior:** this service must not POST/PUT/PATCH/DELETE SmartEvent business data. Customer actions stay in the existing SmartEvent web application.
- `domain`: standard-library-only entities/value objects/invariants.
- `application`: framework-independent use cases and ports.
- `adapters/inbound`: FastAPI/Pydantic HTTP DTO mapping.
- `adapters/outbound`: Vietnamese rule baseline, fail-closed GET tool gateway and safe HTTP transport.
- `infrastructure`: configuration discovery and dependency composition.
- No domain/application dependency on FastAPI, Pydantic, HTTP clients, YAML, database clients or other outer-layer libraries.
- No direct business SQL/ORM and no credential/QR/token forwarding into model context.
- `docs/contexts/v1.2/` is an **immutable 49-file historical specification snapshot**. Runtime-authoritative corrections live in `configs/` and `docs/architecture/`.

## Local development

```bash
python -m pip install --require-hashes -r requirements/dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/verify_dependency_locks.py
python -m compileall -q src scripts tests
python scripts/static_verify.py
python scripts/verify_runtime_config_sync.py
pytest -q --cov=smartevent_ai --cov-report=term-missing --cov-fail-under=90
python scripts/verify_contexts.py
ruff check src tests scripts
mypy src
ruff format --check src tests scripts
pip-audit --no-deps --disable-pip -r requirements/runtime.lock
```

Run the API:

```bash
uvicorn smartevent_ai.main:app --host 127.0.0.1 --port 8001
```

Quick requests:

```bash
curl http://127.0.0.1:8001/health/ready
curl -X POST http://127.0.0.1:8001/api/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Tìm concert ở Hà Nội"}'
```

## Runtime configuration

The package contains fail-closed fallback copies of:

- `runtime_tool_registry.yaml`
- `implementation_gates.yaml`

This makes the installed wheel boot independently of the current working directory. A reviewed external configuration directory may be selected with `CONFIG_DIR`; `.env.example` points local development to `configs/`. CI verifies root and packaged copies are byte-identical.

All business tools ship **disabled**. `/health/ready` therefore reports `degraded` until approved integration gates are changed to `PASS` in reviewed configuration. Environment variables do not provide individual tool-enable or gate-bypass switches.

`/api/v1/chat` is stateless. Send the returned `state` as `previous_state` on the next turn. That state is untrusted user preference context only and never authenticates private data access.

## Source-code fixes in 0.1.2

- Reject incomplete/contradictory page cardinality and response pages that differ from the request.
- Preserve the active dialogue task during budget clarification; support typed CLEAR/REMOVE and clarify invalid quantities.
- Validate optimizer values, JSON depth/numbers and end-to-end tool deadlines; block known side-effect GET routes in gateway and transport.
- Split datasets by connected dialogue groups and scenario families; hash exactly the bytes written on every OS and flag empty evaluation splits.
- Add safe request IDs and structured latency/status logs with no message/state/header payloads.
- Lock the complete dependency graph with artifact hashes, update affected framework dependencies and audit the runtime graph in CI.
- Verify Windows/Linux source integrity, dependency exports and a fully isolated wheel install. Source manifests exclude local reports/secrets; maintained QA evidence is versioned under `docs/architecture/`.

The earlier 0.1.1 repair included:

- Prevented large/invalid budget text from causing HTTP 500; money parsing uses `Decimal` and bounded domain values.
- Added multi-turn resolution for “tổng” / “mỗi vé” budget clarification.
- Added typed event-search criteria so backend `q` and `city` receive semantic fields rather than the whole user sentence.
- Strengthened Spring `PageResponse` invariants and global result-completeness semantics.
- Made domain/application inner layers framework-independent.
- Made wheel startup independent of repository CWD via packaged fail-closed config resources.
- Added deterministic dataset split manifests with input/schema/output SHA-256 hashes and optional source revision.
- Hardened registry validation, transport JSON/content bounds, config synchronization and CI wheel/Docker smoke gates.
- Made `pytest -q` run directly from repository root without special `PYTHONPATH` workarounds.

## How to promote a business read tool

1. Prove backend visibility/ownership behavior against a pinned backend revision.
2. Complete `RUNTIME-READONLY` plus the tool-specific gate with integration evidence.
3. For private reads, implement verified customer-self identity delegation with no admin-context inheritance.
4. Change gate/tool configuration only in a reviewed PR; never set `enabled` alone.
5. Run zero-business-write E2E checks, unchanged business-DB snapshots, sensitive-field projection tests and cross-account negatives.

## Reproducibility

- `.python-version` selects Python 3.12; CI covers Python 3.11 and 3.12.
- Runtime/dev dependencies are pinned in `uv.lock`; CI and Docker install generated hash exports from `requirements/`. See [dependency lock procedure](requirements/LOCKFILE_STATUS.md).
- `scripts/verify_contexts.py` verifies the immutable v1.2 snapshot.
- `scripts/verify_runtime_config_sync.py` verifies packaged config copies match reviewed root configs.
- `scripts/split_dataset.py` delegates to packaged deterministic tooling and emits input/schema/output hashes.
- Wheel clean-directory startup is a CI gate.
- Docker runs as a non-root user and includes liveness health checking.
- `.gitattributes` preserves historical bytes and uses LF for authored source, so hashes survive fresh checkouts on Windows and Linux.
- Dataset splits with empty partitions report `evaluation_ready=false`. The tiny seed corpus is a tooling example, not a valid model benchmark.

## Repository map

```text
src/smartevent_ai/
  domain/              # pure Python business/dialogue values and optimizer
  application/         # use cases, ports, response composition
  adapters/inbound/    # FastAPI/Pydantic transport DTOs
  adapters/outbound/   # NLU baseline, GET gateway, HTTP transport
  infrastructure/      # settings and composition root
  resources/           # packaged fail-closed runtime config fallback
  tooling/             # deterministic dataset tooling
configs/               # reviewed runtime registry/gates; all tools disabled
docs/contexts/v1.2/    # immutable historical 49-file context snapshot
docs/architecture/     # ADR, security and release-gate addenda
scripts/                # verification/CLI utilities
tests/                  # unit, HTTP, contract and negative security tests
.github/workflows/      # CI matrix + wheel + Docker smoke
```

## Quality and limitations

See [QA evidence](docs/architecture/QA_REPORT.md), [audit closures](docs/architecture/REVIEW_LOG.md) and [remaining integration work](docs/architecture/BACKLOG.md).

The repository is a development foundation. Local validation and unexecuted gates are recorded separately; a workflow definition is not a passing remote CI run. Docker uses a floating Python base tag, so hash-locked Python dependencies alone do not guarantee byte-identical images. No claim of production-readiness or live backend safety is made.

For a clean source export without local files, regenerate the source manifest after reviewed edits and run `python scripts/export_source.py dist/source-export`. The destination must be new. Run the same verification commands from that export before uploading. Never include `.env`, local reports, caches, build outputs or credentials in Git.
