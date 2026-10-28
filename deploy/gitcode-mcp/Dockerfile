FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY packages/gitcode-mcp/pyproject.toml packages/gitcode-mcp/README.md packages/gitcode-mcp/LICENSE packages/gitcode-mcp/MIGRATION_SOURCE.json /app/packages/gitcode-mcp/
COPY packages/gitcode-mcp/src /app/packages/gitcode-mcp/src
RUN python -m pip install --no-cache-dir /app/packages/gitcode-mcp \
    && install -d -m 0700 -o 10001 -g 10001 /var/lib/gitcode-mcp

USER 10001:10001
EXPOSE 8765

CMD ["gitcode-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8765"]
