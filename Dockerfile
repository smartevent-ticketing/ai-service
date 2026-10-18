FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CONFIG_DIR=/app/configs

WORKDIR /app
RUN groupadd --system app && useradd --system --gid app app

COPY requirements/runtime.lock ./requirements/runtime.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements/runtime.lock
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY configs/ ./configs/
RUN python -m pip install --no-cache-dir --no-deps . && chown -R app:app /app

USER app
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health/live', timeout=2).read()" || exit 1
CMD ["python", "-m", "uvicorn", "smartevent_ai.main:app", "--host", "0.0.0.0", "--port", "8001"]
