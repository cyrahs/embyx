# Builder
FROM python:3.12-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Bring in uv
COPY --from=ghcr.io/astral-sh/uv:python3.12-bookworm-slim /uv /usr/local/bin/uv

# Copy manifests
COPY pyproject.toml uv.lock ./

# Create .venv
RUN uv sync --frozen --no-dev

# Runner
FROM python:3.12-bookworm-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app


# Copy .venv and application code
COPY --from=builder /app/.venv .venv
COPY src/ src/
COPY run.py ./


# Default command runs your launcher, which invokes .venv/bin/python
CMD ["python", "run.py"]
