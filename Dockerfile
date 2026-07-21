FROM ghcr.io/astral-sh/uv:python3.13-trixie-slim AS builder


WORKDIR /app

# Copy manifests
COPY pyproject.toml uv.lock ./

# Create .venv
RUN uv sync --locked --no-dev --compile-bytecode --no-cache

# Runner
FROM python:3.13-slim-trixie AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app


# Copy .venv and application code
COPY --from=builder /app/.venv .venv
COPY src/ src/
COPY run.py ./

# Compile application code to bytecode
RUN ./.venv/bin/python -m compileall src/ run.py

# Run the launcher by default; command arguments can override CMD.
ENTRYPOINT ["./.venv/bin/python", "run.py"]
CMD ["rss"]
