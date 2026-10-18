# SmartEvent AI Service — Instructions for Coding/Audit Agents

1. Read `README.md`, `docs/architecture/ADR-001.md`, and `docs/contexts/v1.2/AGENTS.md` first. The runtime **READ_ONLY** permission supersedes any mutation suggestions in older PRDs.
2. Treat `docs/contexts/v1.2/` as immutable historical evidence. Add corrections under `docs/architecture/`, runtime contracts under `configs/`, and update tests with every behavior change.
3. Preserve Clean Architecture: `domain` is standard-library-only; `application` may depend on domain and ports only; adapters/infrastructure own FastAPI, Pydantic, HTTP, YAML and configuration details.
4. SmartEvent business HTTP is **GET only** on named registry paths. No arbitrary URLs/methods, SQL access, auth impersonation, admin-context customer reads, raw backend JSON to model context, or QR/token fields.
5. Every business tool must default disabled and define: gate, strict arguments, required response fields, allowlist projection, fixed endpoint, timeout/result limits and negative tests. `SPEC_TEST_ONLY`, `BLOCKED`, and `NOT_RUN` are not `PASS`.
6. Never claim complete/realtime inventory from incomplete pages or truncated lists. Never enable a tool based only on unit tests.
7. Config source of truth is `configs/`; packaged fallback copies under `src/smartevent_ai/resources/` must remain byte-identical. Run `python scripts/verify_runtime_config_sync.py` after config edits.
8. Before a PR run, where tooling is available: `python -m compileall -q src scripts tests`, `python scripts/static_verify.py`, `python scripts/verify_runtime_config_sync.py`, `ruff check src tests scripts`, `mypy src`, `pytest -q --cov=smartevent_ai --cov-fail-under=90`, `python scripts/verify_contexts.py`, `python scripts/source_manifest.py --verify`, and clean-wheel smoke/build gates.
9. Never modify other repositories unless explicitly requested. Never push or merge without permission. Use small reviewable changes and record unexecuted gates honestly.
