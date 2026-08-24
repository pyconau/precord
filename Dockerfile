FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install dependencies separately from the project so this layer is reused
# whenever only application code changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

RUN useradd --create-home --uid 1000 precord
USER precord

EXPOSE 8000

# Liveness only, matching /health: a database blip should not restart a
# container that is otherwise serving.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

CMD ["gunicorn", "precord.web:app", \
     "--access-logfile", "-", \
     "--bind", "0.0.0.0:8000", \
     "--error-log", "-", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker"]
