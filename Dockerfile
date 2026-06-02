FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY sidecar ./sidecar
COPY migrations ./migrations
COPY scripts ./scripts

RUN pip install --no-cache-dir fastapi uvicorn pydantic pydantic-settings asyncpg

EXPOSE 8765

CMD ["uvicorn", "autoskill.main:app", "--app-dir", "sidecar", "--host", "0.0.0.0", "--port", "8765"]
