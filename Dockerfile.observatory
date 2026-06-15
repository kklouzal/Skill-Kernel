FROM node:24-slim AS build

WORKDIR /ui

COPY sidecar/autoskill/observatory/package*.json ./
RUN npm ci

COPY sidecar/autoskill/observatory ./
RUN npm run build

FROM python:3.13-slim

ARG SKILLKERNEL_BUILD_SHA=local
ARG SKILLKERNEL_IMAGE_SOURCE=local
LABEL org.opencontainers.image.revision="${SKILLKERNEL_BUILD_SHA}" \
    org.opencontainers.image.source="${SKILLKERNEL_IMAGE_SOURCE}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/sidecar \
    SKILLKERNEL_OBSERVATORY_PORT=8757 \
    SKILLKERNEL_OBSERVATORY_STATIC_ROOT=/app/observatory

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sidecar ./sidecar
COPY --from=build /ui/dist /app/observatory
COPY containers/observatory/entrypoint.sh /app/entrypoint.sh
COPY containers/observatory/healthcheck.py /app/healthcheck.py

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings asyncpg \
    && chmod +x /app/entrypoint.sh /app/healthcheck.py \
    && useradd --create-home --home-dir /home/skillkernel --shell /usr/sbin/nologin skillkernel \
    && chown -R skillkernel:skillkernel /app

USER skillkernel

EXPOSE 8757

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "autoskill.observatory_main:app", "--app-dir", "/app/sidecar", "--host", "0.0.0.0", "--port", "8757"]
HEALTHCHECK --interval=10s --timeout=5s --retries=12 CMD ["python", "/app/healthcheck.py", "observatory"]
