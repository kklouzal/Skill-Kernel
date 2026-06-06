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
printf '%s\n' 'postgresql://skillkernel:change-me@postgres:5432/skillkernel' > secrets/database_url.txt
printf '%s\n' 'replace-with-plugin-shared-secret' > secrets/plugin_shared_secret.txt
printf '%s\n' 'replace-with-control-token' > secrets/control_token.txt
printf '%s\n' 'replace-with-admin-token' > secrets/admin_token.txt
docker compose -f compose.example.yml config --quiet
```

Core expands the reference `*_FILE` variables at container start, so the
database URL and plugin/control/admin credentials remain mounted secrets rather
than inline environment values. The Observatory web/API container receives only
the database URL and admin token secrets, has no `depends_on` edge to Core or
Postgres, and can serve the UI shell plus read-only/degraded API diagnostics
when Core is unreachable.

The root `docker-compose.yml` remains the Dev-01 oriented deployment file. This
reference directory is the portable topology and packaging contract surface.
