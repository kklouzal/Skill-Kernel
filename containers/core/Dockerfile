FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/sidecar \
    SKILLKERNEL_CORE_PORT=8765

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sidecar ./sidecar
COPY migrations ./migrations
COPY scripts ./scripts
COPY containers/core/entrypoint.sh /app/entrypoint.sh
COPY containers/core/healthcheck.py /app/healthcheck.py

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings asyncpg \
    && chmod +x /app/entrypoint.sh /app/healthcheck.py \
    && useradd --create-home --home-dir /home/skillkernel --shell /usr/sbin/nologin skillkernel \
    && mkdir -p /workspace /var/lib/skillkernel \
    && chown -R skillkernel:skillkernel /app /workspace /var/lib/skillkernel

USER skillkernel

EXPOSE 8765

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "autoskill.main:app", "--app-dir", "/app/sidecar", "--host", "0.0.0.0", "--port", "8765"]
HEALTHCHECK --interval=10s --timeout=5s --retries=12 CMD ["python", "/app/healthcheck.py", "core"]
