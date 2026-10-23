.PHONY: setup compile static lint typecheck test contexts configs manifest package wheel-smoke knowledge-smoke check run

setup:
	python -m pip install --require-hashes -r requirements/dev.lock
	python -m pip install --no-deps --no-build-isolation -e .

compile:
	python -m compileall -q src scripts tests

static:
	python scripts/verify/static_verify.py

lint:
	ruff check src tests scripts

typecheck:
	mypy src

test:
	pytest -q --cov=smartevent_ai --cov-report=term-missing --cov-fail-under=90

contexts:
	python scripts/verify/verify_contexts.py

configs:
	python scripts/verify/verify_runtime_config_sync.py
	python scripts/knowledge/export_knowledge_schemas.py --verify

knowledge-smoke:
	python scripts/knowledge/knowledge_smoke.py --output artifacts/knowledge-smoke

manifest:
	python scripts/verify/source_manifest.py --verify

package:
	python -m pip wheel --no-deps --no-build-isolation . -w dist/wheel

wheel-smoke: package
	python scripts/release/wheel_smoke.py dist/wheel

check: compile static configs lint typecheck test contexts manifest wheel-smoke

run:
	uvicorn smartevent_ai.main:app --reload --host 127.0.0.1 --port 8001
