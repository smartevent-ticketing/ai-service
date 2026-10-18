# Dependency reproducibility

`pyproject.toml` defines direct pins and `uv.lock` records the resolved graph with
artifact hashes. Generated `runtime.lock` and `dev.lock` are pip-compatible hash
exports. CI installs the development export with `--require-hashes`, then installs
this project with `--no-deps --no-build-isolation`; setuptools is in the locked
development graph. Docker installs the runtime hash export before the package.

Update using uv 0.12.6 from the project root:

```powershell
uv lock
uv export --quiet --frozen --no-header --no-dev --no-emit-project --format requirements-txt --output-file requirements/runtime.lock
uv export --quiet --frozen --no-header --no-emit-project --format requirements-txt --output-file requirements/dev.lock
```

`requirements/dev.txt` remains a direct-tool convenience list; the hash exports
are the installation input for verification and release. Dependency changes must
regenerate all three lock artifacts, pass consistency/type/tests/wheel checks and
run `pip-audit --no-deps --disable-pip -r requirements/runtime.lock`.

The graph supports the Python range in pyproject; execution evidence for each
interpreter/OS is recorded separately in `docs/architecture/QA_REPORT.md`. A lock
does not prove runtime compatibility, vulnerability absence forever, identical
Docker base images or trained-model reproducibility.
