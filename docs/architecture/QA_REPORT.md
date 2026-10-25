# Verification evidence

## Local review fixes — 0.2.0, 2026-10-23

Scope: current uncommitted working tree at baseline `861bfcd`. This records
local results, not remote CI or production approval. Repairs and limitations:
[REVIEW_LOG.md](REVIEW_LOG.md); execution status: [PROJECT_EXECUTION_PLAN.md](PROJECT_EXECUTION_PLAN.md).

| Gate | Current result |
|---|---|
| Full unit/contract/security suite | PASS, 348 tests, 92.47% statement coverage; Windows Python 3.12.10, `COVERAGE_CORE=pytrace` |
| Default coverage core | BLOCKED_ENV, native Windows access violation; no passing claim for that core |
| Historical reference tests / integrity | PASS, 47 tests / original 49 file hashes |
| Compile/static/Ruff/format/Mypy | PASS, 53 source files checked by Mypy |
| Runtime config / knowledge schemas / dependency lock | PASS |
| Project environment dependency consistency | PASS, pip check |
| Offline TEST_ONLY knowledge smoke | PASS; does not authorize runtime retrieval |
| Wheel build | PASS, offline build of 0.2.0 |
| New isolated wheel installation and HTTP smoke | NOT_RUN for this patch |
| New dependency advisory audit | NOT_RUN for this patch |
| Remote CI matrix / Docker / live integration | No qualifying evidence for this patch |

The successful full suite explicitly loaded pytest_asyncio and pytest_cov with
plugin autoload disabled. It retained all tests, the normal event loop and the
90% threshold. The Python tracer is a supported coverage core; the native crash
cause remains unresolved. TestClient deprecation and pyreadline shutdown warnings
were visible and were not suppressed. Earlier socketpair blocking did not recur
in this completed run.

Current wheel: `smartevent_ai_service-0.2.0-py3-none-any.whl`, 82670 bytes,
SHA-256 `3fd78597fd23f79d86f24b875c44c206ce6a069a1ac41cf3a34fb8950ebe73fc`.
This is a build result, not an isolated-install or container result. The historical
audit and wheel smoke results below do not certify the current patch.

## Historical foundation 0.1.2 — verification evidence

Date: 2026-10-18. Source preparation for GitHub upload is complete within the
development-foundation scope. This is not a production or merge approval; remote
CI and container evidence are still absent. All 14 business tools remain disabled.

Verification used Windows with Python 3.11.9 and 3.12.10 and the hashed dependency
graph in this repository. Full runtime tests ran from a manifest-only source
export, excluding local reports, credentials, virtual environments and build
metadata. Maintained documentation was finalized after those code checks; all
executable/config/test/dependency files were compared with the checked export.

| Gate | Result |
|---|---|
| Compile sources/scripts/tests | PASS |
| Clean Architecture/read-only static guard | PASS |
| Ruff + formatting | PASS |
| Mypy | PASS, 27 source files |
| Runtime tests on Python 3.11.9 | PASS, 150 tests, 92.45% statement coverage |
| Runtime tests on Python 3.12.10 | PASS, 150 tests, 92.45% statement coverage |
| Historical reference tests + static validator | PASS, 47 tests; specification evidence only |
| Historical source integrity | PASS, original 49 SHA-256 values |
| Runtime configuration synchronization | PASS, root/package copies byte-identical |
| Lock/export integrity | PASS, universal lock and both hash exports agree |
| Dependency consistency | PASS, no broken requirements in project environment |
| Runtime dependency audit | PASS, pip-audit 2.10.1 reports no known vulnerabilities after framework updates |
| Source manifest/export | PASS, no ignored manifest entries; fresh export verifies without local reports |
| Wheel build | PASS from clean source using CI's pip wheel command |
| Isolated wheel smoke | PASS, hashed runtime install in new venv, import from that venv, empty CWD, health/degraded/chat |
| Docker build/smoke | NOT_RUN: Docker Engine `/version` returns HTTP 500 on this host |
| Remote Linux/Windows CI | NOT_RUN: no push performed; workflow definition is not passing Actions evidence |
| Live visibility/auth/zero-write/load/model/RAG | BLOCKED / NOT_IMPLEMENTED; see release gates |

Wheel: `smartevent_ai_service-0.1.2-py3-none-any.whl`, 35349 bytes,
SHA-256 `0a556664abb5359beba8cc1abfb0f7ae003460eee170ae3aa968fa5788272518`.
Every packaged Python/YAML file was matched to the current source bytes.

One third-party deprecation warning remains: Starlette TestClient's compatibility
with httpx. It does not fail tests and is not suppressed. The business HTTP adapter
still explicitly uses httpx 0.28.1; a future TestClient migration must be tested.

The original dependency audit reported advisories in pydantic-settings and
Starlette; the pins were upgraded and the audit rerun without ignore exemptions.
This does not establish exploitability of every advisory in this application or
guarantee the absence of future advisories. Upstream references:
[pydantic-settings advisory](https://github.com/pydantic/pydantic-settings/security/advisories/GHSA-4xgf-cpjx-pc3j),
[Starlette advisory](https://github.com/Kludex/starlette/security/advisories/GHSA-82w8-qh3p-5jfq).

CI defines Python 3.11/3.12 on Windows and Linux, hash-locked installation, lint,
format/type/static checks, runtime and historical tests, context/config/source
integrity, dependency audit, wheel build/isolated install and Docker smoke. The
Docker base tag still floats; locked Python dependencies alone do not make image
bytes reproducible. A passing remote run and container evidence must precede any
merge/release claim.

See [REVIEW_LOG.md](REVIEW_LOG.md) for the 12 audit closures and
[BACKLOG.md](BACKLOG.md) for remaining product/release work. These tests authorize
no live backend reads and make no claims about trained models or production load.
