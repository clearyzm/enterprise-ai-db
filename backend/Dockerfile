FROM python:3.11-slim

WORKDIR /app

# curl for healthcheck in docker-compose
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Cache dependency layer: only re-runs when pyproject.toml changes
COPY pyproject.toml ./
RUN uv sync --no-dev

# Source code is mounted as a volume in development (docker-compose.yml)
# so COPY . . is intentionally omitted here.
# For production builds (Phase 11), a separate Dockerfile.prod will COPY . .

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
