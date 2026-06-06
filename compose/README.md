# SkillKernel Compose Reference

This directory contains the reference split-container topology required by the
unified implementation specification.

- `compose.example.yml` defines Postgres/pgvector, Core, and Observatory as
  separate services with distinct networks, volumes, secrets, and health checks.
- `compose.local-llm.example.yml` is an optional override for operator-supplied
  local model and embedding endpoints. Image variables intentionally require
  explicit tags or digests.
- `env.core.example`, `env.observatory.example`, and `env.postgres.example`
  document the service-specific environment split.

Run the reference topology from this directory after creating the secret files:

```bash
mkdir -p secrets ../.skillkernel/workspace ../.skillkernel/openclaw
printf '%s\n' 'change-me' > secrets/postgres_password.txt
docker compose -f compose.example.yml config --quiet
```

The root `docker-compose.yml` remains the Dev-01 oriented deployment file. This
reference directory is the portable topology and packaging contract surface.
