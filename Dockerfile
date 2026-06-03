FROM node:24-slim AS observatory-build

WORKDIR /ui

COPY sidecar/autoskill/observatory/package*.json ./
RUN npm ci

COPY sidecar/autoskill/observatory ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sidecar ./sidecar
COPY migrations ./migrations
COPY scripts ./scripts
COPY --from=observatory-build /ui/dist ./sidecar/autoskill/observatory/dist

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings asyncpg

EXPOSE 8765

CMD ["uvicorn", "autoskill.main:app", "--app-dir", "sidecar", "--host", "0.0.0.0", "--port", "8765"]
