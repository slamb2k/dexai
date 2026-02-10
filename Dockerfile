# =============================================================================
# DexAI Backend Dockerfile
# Multi-stage build for Python/FastAPI backend
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Builder
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set environment variables
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install dependencies into the virtual environment
# Include channels + multimodal extras for messaging and image generation
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /app/.venv && \
    uv pip install --python=/app/.venv/bin/python -e ".[channels,multimodal]"

# -----------------------------------------------------------------------------
# Stage 2: Runtime
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Create non-root user for security
RUN groupadd --gid 1000 dexai && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home dexai

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY --chown=dexai:dexai . .

# Create data directory for SQLite databases
RUN mkdir -p /app/data && chown -R dexai:dexai /app/data

# Switch to non-root user
USER dexai

# Expose API port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/api/health', timeout=5).raise_for_status()" || exit 1

# Default command: run FastAPI backend
CMD ["uvicorn", "tools.dashboard.backend.main:app", "--host", "0.0.0.0", "--port", "8080"]
