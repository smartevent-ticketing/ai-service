# Dependency reproducibility

`pyproject.toml` defines direct pins and `uv.lock` records the resolved graph with
artifact hashes. Generated `runtime.lock`, `dev.lock` and `rag.lock` are pip-compatible hash
exports. CI installs the development export with `--require-hashes`, then installs
this project with `--no-deps --no-build-isolation`; setuptools is in the locked
development graph. Docker installs the runtime hash export before the package.

Update using uv 0.12.6 from the project root:

```powershell
uv lock
uv export --quiet --frozen --no-header --no-dev --no-emit-project --format requirements-txt --output-file requirements/runtime.lock
uv export --quiet --frozen --no-header --no-emit-project --format requirements-txt --output-file requirements/dev.lock
uv export --quiet --frozen --no-header --no-dev --extra rag-ingest --extra rag-semantic --no-emit-project --format requirements-txt --output-file requirements/rag.lock
```

`requirements/dev.txt` is generated from the `dev` dependency group and the
hashed `dev.lock` export — do not edit it by hand. Regenerate with
`python scripts/export_dev_tools.py --write` (verify with `--check`). The hash
exports remain the installation input for verification and release. Dependency
changes must regenerate uv.lock and all three hash exports, pass
consistency/type/tests/wheel checks and
run `pip-audit --no-deps --disable-pip -r requirements/runtime.lock`.

The graph supports the Python range in pyproject; execution evidence for each
interpreter/OS is recorded separately in `docs/architecture/QA_REPORT.md`. A lock
does not prove runtime compatibility, vulnerability absence forever, identical
Docker base images or trained-model reproducibility.

Foundation 0.2.0 keeps tokenizers/NumPy/ONNX Runtime optional for runtime installs.
The development lock includes these and ONNX graph helpers for network-free tests.
After an expanded development audit, pytest, setuptools and ONNX helpers were
updated to fixed releases; audit all three exports without advisory exemptions.
Model/tokenizer assets are separately revision/checksum pinned and never auto-downloaded.
