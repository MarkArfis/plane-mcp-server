# Self-hosted image for Plane Community: one long-running HTTP process instead of
# MetaMCP spawning `uvx --from git+...` over stdio. Dependencies come from uv.lock,
# so the image is reproducible; uv is pinned instead of ghcr.io/astral-sh/uv:latest.
ARG BASE_IMAGE=python:3.11-slim
FROM ${BASE_IMAGE}

RUN pip install --no-cache-dir uv==0.11.32 \
    && useradd --create-home --uid 10001 mcp

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY plane_mcp/ ./plane_mcp/
RUN uv export --frozen --no-dev --no-emit-project -o /tmp/requirements.txt \
    && uv pip install --system --no-cache -r /tmp/requirements.txt \
    && uv pip install --system --no-cache --no-deps . \
    && rm /tmp/requirements.txt

USER mcp
EXPOSE 8211
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8211), 3)" || exit 1
ENTRYPOINT ["python", "-m", "plane_mcp"]
CMD ["http"]
