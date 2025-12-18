FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project configuration
COPY pyproject.toml .

# Install dependencies with uv
RUN uv pip install --system -r pyproject.toml

FROM python:3.12-slim AS final

ENV PYTHONPATH=/app

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY graphtactics graphtactics
COPY data data

# Use uvicorn directly for FastAPI, the port is passed by docker-compose
CMD sh -c "uvicorn graphtactics.app:app --host 0.0.0.0 --port ${PORT}"
