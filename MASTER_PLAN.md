# Facebook Monitor — Master Plan

**Role:** Senior Solutions Architect / DevOps Lead

**Project context:** Monitor specific Facebook Groups via Graph API (including MCP-driven search), analyze content with Anthropic Claude, persist to SQLite (dev) or PostgreSQL (prod), generate daily HTML/CSV reports sent over SMTP, and handle Meta webhooks for near-real-time signals.

**Tech stack:** Python 3.11+, Facebook Graph API v21.0, Anthropic Claude API, Flask, APScheduler, SQLite / PostgreSQL, Docker & Docker Compose, GitHub Actions; optional Prometheus/Grafana.

---

## 1. Architecture Plan

### 1.1 Data flow (Mermaid)

Flow: **Facebook → Webhook / MCP / Scheduler → App → Claude API → DB → Reports → Email.**

```mermaid
flowchart LR
  subgraph facebook [Facebook]
    GraphAPI[GraphAPIv21]
    Webhooks[Webhooks]
  end

  subgraph ingest [Ingest]
    MCP[McpSearchTool]
    FlaskWH[FlaskWebhook]
    Sched[ApSchedulerCron]
  end

  subgraph appCore [Application]
    Norm[NormalizeDedupe]
    Rules[BusinessRules]
  end

  subgraph aiLayer [AI]
    Claude[ClaudeAPI]
  end

  subgraph persistence [Persistence]
    DB[(SqliteOrPostgres)]
  end

  subgraph output [Output]
    Reports[HtmlCsvReports]
    SMTP[SmtpEmail]
  end

  GraphAPI --> MCP
  GraphAPI --> Sched
  Webhooks --> FlaskWH
  MCP --> Norm
  FlaskWH --> Norm
  Sched --> Norm
  Norm --> Rules
  Rules --> Claude
  Claude --> DB
  Rules --> DB
  DB --> Reports
  Reports --> SMTP
  FlaskWH -->|optionalInstantAlert| SMTP
```

**Narrative:** Pull-based ingestion (scheduled jobs and/or MCP-exposed search tools) and push-based ingestion (webhooks) converge on one normalization and idempotency layer. Business rules decide what is analyzed, stored, and reported. Claude produces structured analysis persisted through the app. Scheduled jobs materialize HTML/CSV and send via SMTP. High-priority webhook paths may send a slim notification without waiting for the daily batch.

### 1.2 Monolith vs microservices

**Recommendation: modular monolith** — a single deployable (Flask WSGI for HTTP + APScheduler in the same codebase; optionally a second process in the same image via `supervisord` if you must isolate scheduler CPU from webhook workers).

| Criterion | Modular monolith | Split microservices |
|-----------|------------------|---------------------|
| Operational cost | Low: one image, one Compose stack | Higher: more services, networking, tracing |
| Graph rate limits | Central backoff and token bucket | Risk of duplicate uncached calls across services |
| Transactions | Simple: analysis + persistence in one DB | Sagas / eventual consistency |
| Webhook latency | Few hops to DB | Extra network unless dedicated ingress |

**When to split:** Dedicated HA webhook ingress, independent scaling for CPU-heavy Claude batch jobs, or compliance boundaries (e.g. PII-scrubbing service). Until then, enforce package boundaries (`api/`, `services/`, `jobs/`, `webhooks/`) so a future split is mechanical.

### 1.3 Security architecture

- **Secrets:** Never commit tokens. Inject at runtime: `.env` (local only, gitignored), Docker/Kubernetes secrets, or cloud secret managers (AWS Secrets Manager, GCP Secret Manager, Vault). Prefer **OIDC** from CI to registries instead of long-lived `DOCKER_PASSWORD` in YAML.
- **Facebook tokens:** Minimal scopes; prefer system/page tokens where policy allows; monitor expiry; automate refresh where supported; **alert on refresh failure** (metric + log). Never log full tokens.
- **Webhooks:** Constant-time compare for `hub.verify_token` against `WEBHOOK_VERIFY_TOKEN`; validate `X-Hub-Signature-256` with `FACEBOOK_APP_SECRET`; idempotency using stable keys (e.g. `entry[].id` + `time` or payload hash) before side effects.
- **Network:** Postgres on an internal bridge **without** a published port in production; only the app joins that database network. Expose **only** `443`/`80` via a reverse proxy with TLS termination (Caddy, Traefik, nginx).
- **Claude:** Server-side API key only; per-environment keys; rotate on compromise.
- **Logging:** Structured JSON for SIEM; redact emails, message bodies, and auth material; use correlation IDs across webhook and Graph calls.

---

## 2. Implementation Roadmap

### 2.1 Phases

| Phase | Scope | Exit criteria |
|-------|--------|----------------|
| **1 — Core API** | Graph client (`v21.0`), persistence models, `/health`, typed config | Fetch + store sample posts; health green in Docker |
| **2 — AI integration** | `claude_analyzer.py`, prompts, JSON schema for outputs, mocked unit tests | Analysis rows linked to posts; deterministic tests |
| **3 — Reporting and schedule** | Jinja2 HTML + CSV export, APScheduler daily job, SMTP | End-to-end report email in staging |
| **4 — Real-time** | Webhook routes, signature verification, dedupe store, optional instant email | Meta test webhook succeeds; no duplicate processing |
| **5 — Hardening and DevOps** | Postgres profile, migrations, CI/CD, metrics, backups | Prod compose profile; pipeline green; restore drill documented |

### 2.2 Directory structure (production-oriented)

Copy this layout when implementing the application repository (paths are illustrative).

```text
facebook-monitor/
├── .env.example
├── .github/workflows/ci.yml
├── docker-compose.yml
├── docker-compose.prod.yml
├── Dockerfile
├── pyproject.toml                 # or requirements.txt
├── README.md
├── src/
│   ├── __init__.py
│   ├── main.py                    # app factory: routes + scheduler lifecycle
│   ├── config.py                  # pydantic-settings / env validation
│   ├── api/
│   │   ├── routes_health.py
│   │   └── routes_admin.py      # optional: manual report trigger
│   ├── services/
│   │   ├── facebook_client.py
│   │   ├── claude_analyzer.py
│   │   ├── email_reporter.py
│   │   └── rate_limit.py          # shared backoff for Graph
│   ├── webhooks/
│   │   ├── facebook_webhook.py
│   │   └── verify.py
│   ├── jobs/
│   │   └── scheduler.py         # APScheduler job definitions
│   ├── db/
│   │   ├── db_models.py
│   │   ├── session.py
│   │   └── migrations/          # Alembic if using SQLAlchemy
│   └── mcp_server.py            # optional: MCP tool registration
├── deploy/
│   └── prometheus.yml           # optional scrape config
├── templates/
│   └── report.html.j2
├── tests/
├── scripts/
│   └── backup_db.sh
└── data/                         # gitignored — SQLite or bind mount
```

### 2.3 Critical code modules

| Module | Responsibility |
|--------|----------------|
| `facebook_client.py` | Graph HTTP client, pagination, `429` handling, version `v21.0` |
| `claude_analyzer.py` | Prompt assembly, Anthropic SDK calls, response parsing, token budget |
| `db_models.py` | ORM models: posts, analyses, webhook_events, idempotency keys |
| `email_reporter.py` | Render templates, attach CSV, SMTP STARTTLS |
| `scheduler.py` | Cron (`REPORT_CRON`), timezone (`TIMEZONE`) |
| `facebook_webhook.py` | GET verify, POST ingest, enqueue or synchronous process |
| `config.py` | Typed settings; no secrets in code; fail fast if required env missing |

### 2.4 Pitfalls

- **Graph rate limits:** Aggressive polling exhausts quotas; use exponential backoff + jitter; use `etag` where semantics allow.
- **Token expiration:** Long-lived tokens still expire; handle Graph error subcodes and refresh flows; alert before silent failure.
- **Webhook duplicates:** Meta may retry; persist idempotency key before email or Claude spend.
- **PII in logs:** Prefer post IDs over bodies in default logs.
- **SMTP throttling:** Queue and retry; surface dead-letter visibility.
- **SQLite concurrency:** Multiple writers block; use Postgres when webhooks and the scheduler overlap writes.

---

## 3. Build and containerization strategy

### 3.1 Production-ready multi-stage Dockerfile

Python 3.11+, non-root user, healthcheck, venv copied from builder stage.

```dockerfile
# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.11

FROM python:${PYTHON_VERSION}-slim AS builder
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

FROM python:${PYTHON_VERSION}-slim AS runtime
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data /app/reports /app/logs \
    && chown -R app:app /app

COPY --chown=app:app src/ ./src/
COPY --chown=app:app templates/ ./templates/

USER app
EXPOSE 5000
ENV DATABASE_URL=sqlite:////app/data/posts_tracking.db

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "src.main:app"]
```

If you use an application factory, add a thin `wsgi.py` or run Gunicorn with `--factory` where supported.

### 3.2 docker-compose.yml (development: app and SQLite)

Use this as the **base** file. Do not duplicate production services here; merge with `docker-compose.prod.yml` (next section).

```yaml
services:
  facebook-monitor:
    build: .
    container_name: facebook-monitor
    restart: unless-stopped
    ports:
      - "5000:5000"
    environment:
      FACEBOOK_ACCESS_TOKEN: ${FACEBOOK_ACCESS_TOKEN}
      FACEBOOK_APP_SECRET: ${FACEBOOK_APP_SECRET}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      SMTP_USER: ${SMTP_USER}
      SMTP_PASSWORD: ${SMTP_PASSWORD}
      SMTP_SERVER: ${SMTP_SERVER:-smtp.gmail.com}
      SMTP_PORT: ${SMTP_PORT:-587}
      REPORT_EMAIL: ${REPORT_EMAIL}
      REPORT_EMAIL_CC: ${REPORT_EMAIL_CC:-}
      WEBHOOK_VERIFY_TOKEN: ${WEBHOOK_VERIFY_TOKEN}
      CLAUDE_MODEL: ${CLAUDE_MODEL:-claude-3-5-sonnet-20241022}
      GRAPH_API_VERSION: ${GRAPH_API_VERSION:-v21.0}
      DATABASE_URL: ${DATABASE_URL:-sqlite:////app/data/posts_tracking.db}
      TIMEZONE: ${TIMEZONE:-UTC}
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
    env_file:
      - .env
    volumes:
      - ./data:/app/data
      - ./reports:/app/reports
      - ./logs:/app/logs
    networks:
      - app_net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  app_net:
    driver: bridge
```

**Run (dev):**

```bash
docker compose up -d
```

### 3.3 docker-compose.prod.yml (overlay: Postgres and optional monitoring)

Keep this in a **separate** file so there is only one top-level `services:` key per file. Compose merges files by service name.

```yaml
services:
  facebook-monitor:
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-monitor}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set_postgres_password}
      POSTGRES_DB: ${POSTGRES_DB:-monitor}
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - app_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 5

  prometheus:
    image: prom/prometheus:v2.53.0
    profiles: ["monitoring"]
    volumes:
      - ./deploy/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    ports:
      - "9090:9090"
    networks:
      - app_net

  grafana:
    image: grafana/grafana:11.2.0
    profiles: ["monitoring"]
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?set_grafana_password}
    networks:
      - app_net

volumes:
  pgdata: {}
```

**Merge and run (production-style stack):**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**With optional monitoring profile:**

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml --profile monitoring up -d
```

**Important:** In production, do **not** publish Postgres port `5432` to the public internet. Only the app service should reach Postgres on the internal network.

### 3.4 Environment variables vs Docker secrets

| Mechanism | When to use |
|-----------|-------------|
| `.env` and `env_file` | Local developer machines only; never commit |
| CI `environment` from encrypted secrets | GitHub Actions and other CI |
| Docker Swarm `secrets` | Secret files under `/run/secrets/`; map in entrypoint |
| Kubernetes Secrets and ExternalSecrets | Production clusters; sync from cloud secret manager |
| Cloud secret manager | Dynamic rotation without baking secrets into images |

**Rule:** Build the same image for every environment; only **runtime** configuration changes.

---

## 4. DevOps and deployment

### 4.1 CI/CD — GitHub Actions

Lint (Ruff), test (pytest), build and push image to GHCR on `main`.

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff pytest
          pip install -r requirements.txt

      - name: Ruff
        run: ruff check src tests

      - name: Pytest
        run: pytest -q

  build-push:
    needs: lint-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:main
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

**Extensions:** Add `mypy`, coverage gates, and Trivy or Grype image scanning; use OIDC (`aws-actions/configure-aws-credentials`) for ECR instead of static AWS keys.

### 4.2 Deployment strategy

- **Single-node Docker Compose:** `docker compose pull && docker compose up -d` performs a **rolling recreate** of containers. Put Caddy, Traefik, or nginx in front for TLS and health-based routing if you run multiple app replicas.
- **Kubernetes:** `Deployment` with `strategy.type: RollingUpdate`, `maxUnavailable: 0`, `maxSurge: 1` for webhook-safe rollouts.
- **Blue/Green:** Use when you cannot tolerate brief health check failures during migrations: stand up the green stack, switch DNS or proxy to green, drain blue. Higher cost; justified by strict SLOs.

**Database migrations:** Run `alembic upgrade head` (or equivalent) as a **one-off job** before shifting traffic. Ship **backward-compatible** schema changes only.

### 4.3 Monitoring and logging (essential metrics)

| Metric or log | Purpose |
|---------------|---------|
| HTTP latency histogram | API p95 and p99 |
| `http_requests_total` by status | Error rate |
| `graph_api_calls_total`, `graph_api_429_total` | Graph quota pressure |
| `claude_requests_total`, `claude_latency_seconds` | AI dependency health |
| `webhook_verify_failures_total` or signature failures | Misconfiguration or abuse |
| `token_refresh_success` / `token_refresh_failure` | Token rotation health |
| `scheduler_last_success_timestamp` | Silent cron failures |
| DB pool available connections, `db_errors_total` | Connection exhaustion |

**Logging:** JSON logs with `trace_id` and resource IDs; avoid raw PII; ship to Loki, ELK, or CloudWatch.

### 4.4 Disaster recovery

| Topic | Practice |
|-------|----------|
| **RPO and RTO** | Document targets (example: RPO 24h for analytics DB, RTO 4h) |
| **Backup** | Postgres: nightly encrypted `pg_dump` or volume snapshots. SQLite: dev-only; copy `/app/data`. Store off-site (for example S3 with SSE-KMS). |
| **Restore procedure** | Follow these steps in order: (1) Stop or drain application traffic. (2) Restore the database from the latest verified backup. (3) Run migrations if the backup predates the schema. (4) Verify `/health` and a sample report job. (5) Resume traffic. (6) Record wall-clock time and gaps. |
| **Testing** | Quarterly restore drill; compare row counts or checksums on sample tables |

---

## Appendix A — Python dependencies (reference)

Pin exact versions in your real `requirements.txt` or lockfile.

```text
mcp>=1.0.0
requests>=2.31.0
python-dotenv>=1.0.0
flask>=3.0.0
apscheduler>=3.10.0
anthropic>=0.18.0
python-dateutil>=2.8.2
jinja2>=3.1.2
gunicorn>=21.0.0
```

Add `sqlalchemy`, `alembic`, and `psycopg[binary]` when adopting PostgreSQL.

---

## Appendix B — Environment variable checklist

| Variable | Purpose |
|----------|---------|
| `FACEBOOK_ACCESS_TOKEN` | Graph API access |
| `FACEBOOK_APP_SECRET` | Webhook signature verification |
| `GRAPH_API_VERSION` | Default `v21.0` |
| `ANTHROPIC_API_KEY` | Claude API |
| `CLAUDE_MODEL` | Model id |
| `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Outbound mail |
| `REPORT_EMAIL`, `REPORT_EMAIL_CC` | Recipients |
| `WEBHOOK_VERIFY_TOKEN` | Meta webhook verification |
| `DATABASE_URL` | SQLite or Postgres DSN |
| `REPORT_CRON`, `TIMEZONE` | Scheduling |
| `LOG_LEVEL` | Logging verbosity |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Compose Postgres (prod overlay) |
| `GRAFANA_ADMIN_PASSWORD` | Optional Grafana (monitoring profile) |

---

*End of Master Plan*
