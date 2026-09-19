# Production Deployment: Docker behind Cloudflare Tunnel

This is the runbook for the production architecture:

```
Cloudflare Tunnel
     -> Next.js frontend (proxies /api/* and /ws/* internally)
          -> FastAPI backend
               -> Neon PostgreSQL + Groq
```

The browser only ever talks to **one public hostname** (the Cloudflare
Tunnel hostname, routed to the frontend container). The backend is never
exposed publicly - it's only reachable from the frontend over the
Docker-internal network. Same-origin access means there is no CORS to
configure and no cross-site cookie problem to work around.

This is additive to, not a replacement for, the existing local/Docker
development workflow (`docker-compose.demo.yml`, `deploy/docker-compose.yml`,
`docs/DEPLOYMENT_GUIDE.md`) - nothing about those changes. This document
covers only the `docker-compose.production.yml` target.

## 1. Required environment variables

Set these in a `.env` file next to `docker-compose.production.yml` (never
commit it - it's already in `.gitignore`), or via your platform/secret
manager. All secrets are environment variables only; nothing is baked into
an image or committed to the repo.

| Variable | Required | Purpose |
|---|---|---|
| `AEGISNEX_DATABASE_URL` | **Yes** | Neon PostgreSQL connection string, e.g. `postgresql://user:password@ep-xxx.neon.tech/aegisnex?sslmode=require` |
| `AEGISNEX_JWT_SECRET` | **Yes** | Session token signing key, >=32 bytes. Generate with `openssl rand -hex 32` |
| `AEGISNEX_FRONTEND_URL` | **Yes** | The public `https://` hostname behind the tunnel (used for auth redirects after login/logout/SSO) |
| `AEGIS_AI_GROQ_API_KEY` | **Yes** | Groq API key (`AEGIS_AI_PROVIDER=groq` is set for you in the compose file) |
| `CLOUDFLARE_TUNNEL_TOKEN` | **Yes** | From the Cloudflare Zero Trust dashboard - see [Section 3](#3-cloudflare-tunnel-origin) |
| `AEGISNEX_LOCAL_AUTH_ENABLED` | No (default `false`) | Set `true` to allow password login without SSO |
| `AEGISNEX_SEED_DEFAULT_ADMIN` / `AEGISNEX_BOOTSTRAP_ADMIN_PASSWORD` | No | Seed a real `administrator` account on startup - see [Section 5](#5-demo-account-initialization) |
| `AEGISNEX_DEMO_ENABLED` / `AEGISNEX_DEMO_PASSWORD` / `AEGISNEX_DEMO_USERNAME` | No | Public recruiter demo login - see [Section 5](#5-demo-account-initialization) |
| `AEGISNEX_REQUIRE_TENANT_MEMBERSHIP` | No (default `true`) | Keep `true` in production |
| `AEGISNEX_DOCKER_SCANNER_ENABLED` | No (default `false` here) | There is no Docker socket available to this container in this topology - leave `false` |
| `AEGISNEX_CORS_ORIGINS` | No | Leave unset - same-origin access means CORS is not needed. Only set if something else calls the API cross-origin |
| `AEGISNEX_SECRET_KEY` | No | Only needed if the secrets-management feature is used |
| `AEGISNEX_METRICS_TOKEN` | No | Protects `/metrics` if scraped externally |
| `AEGISNEX_LOG_LEVEL` | No (default `INFO`) | |
| `AEGIS_AI_GROQ_MODEL` | No | Defaults to Groq's own default if unset |

`AEGISNEX_FORCE_HTTPS_REDIRECT` and `NEXT_PUBLIC_API_URL`/`NEXT_PUBLIC_WS_URL`
are deliberately **not** set in this architecture - see the inline comments
in `docker-compose.production.yml` and [Section 3](#3-cloudflare-tunnel-origin)
for why.

Full variable reference with inline explanations: `.env.example`.

## 2. Docker Compose startup

```bash
# One-time: create your .env with the variables from Section 1.
cp .env.example .env
# edit .env

docker compose -f docker-compose.production.yml --env-file .env config --quiet
# ^ validates the compose file and required variables without starting anything

docker compose -f docker-compose.production.yml --env-file .env up -d --build
docker compose -f docker-compose.production.yml logs -f
```

This starts three services on one internal Docker network
(`aegisnex-internal`); only `cloudflared` needs to be reachable from the
internet, and it reaches out to Cloudflare rather than accepting inbound
connections, so no ports need to be published on the host at all.

- `backend` - FastAPI (`src.dashboard:app` via Uvicorn), not published
- `frontend` - Next.js, not published, waits for `backend`'s healthcheck
- `cloudflared` - the tunnel client, waits for `frontend`'s healthcheck

## 3. Cloudflare Tunnel origin

1. In the Cloudflare Zero Trust dashboard: **Networks -> Tunnels -> Create a
   tunnel** (choose the "Cloudflared" connector type).
2. On the tunnel's **Install connector** step, choose **Docker** and copy
   the token from the generated command (`cloudflared tunnel run --token
   <TOKEN>`) - that token is `CLOUDFLARE_TUNNEL_TOKEN`. This is the only
   credential `cloudflared` needs; no certificate file to mount or commit.
3. Under **Public Hostnames**, add a route:
   - **Public hostname**: your chosen hostname (e.g. `app.example.com`)
   - **Service type**: `HTTP`
   - **URL**: `frontend:3000` (the Docker Compose service name and port -
     Cloudflare Tunnel reaches it over the same `aegisnex-internal` network,
     which is why nothing needs to be published to the host)
4. Set `AEGISNEX_FRONTEND_URL=https://app.example.com` (same hostname, used
   for backend auth redirects) and leave `NEXT_PUBLIC_API_URL` /
   `NEXT_PUBLIC_WS_URL` unset so the browser only ever addresses that one
   hostname; the frontend container proxies `/api/*` and `/ws/*` to
   `backend:8000` server-side (see `frontend/next.config.js`) using the
   `BACKEND_INTERNAL_URL` compose variable - never a `NEXT_PUBLIC_` var, so
   it's never inlined into the browser bundle.
5. Cloudflare terminates TLS at its edge and forwards to `cloudflared` (and
   from there to `frontend`) over plain HTTP - the same posture as any
   other TLS-terminating reverse proxy. `AEGISNEX_FORCE_HTTPS_REDIRECT` is
   pinned to `false` in the compose file for exactly this reason; setting
   it `true` here would create a redirect loop against the tunnel.

## 4. Database migrations

Schema changes ship as idempotent Alembic migrations
(`alembic/versions/`). `PlatformRepository.initialize()` also
self-heals common schema drift on every boot (`CREATE TABLE IF NOT EXISTS`
/ `ADD COLUMN IF NOT EXISTS`), but **Alembic is the source of truth** - run
it explicitly before/after a deploy that changes schema:

```bash
# From a shell with AEGISNEX_DATABASE_URL pointed at Neon (e.g. inside the
# backend container, or locally with the same env var set):
docker compose -f docker-compose.production.yml exec backend \
  python -m alembic upgrade head

# Check current revision:
docker compose -f docker-compose.production.yml exec backend \
  python -m alembic current
```

This is required once for any database that predates this deployment's
auth changes (`UserStore`/`TokenBlacklist` now persist to the `users` /
`external_identities` / `token_blacklist` tables in this same PostgreSQL
database, added by the `enterprise_auth_hardening` migration, with
`token_blacklist.expires_at` further widened to `BIGINT` by
`widen_token_blacklist_expires_at` - required for PostgreSQL specifically,
since the "revoked forever" sentinel value overflows a 32-bit `INTEGER`).
Run `alembic upgrade head` once against your Neon database before or
immediately after the first deploy of this stack.

## 5. Demo account initialization

The public recruiter demo is **opt-in and off by default**. To enable it:

```bash
AEGISNEX_DEMO_ENABLED=true
AEGISNEX_DEMO_PASSWORD=<a strong secret, not used anywhere else>
# AEGISNEX_DEMO_USERNAME=demo   # optional, this is the default
```

The demo account is **created on first login attempt**, not at container
startup - `POST /api/auth/demo-login` seeds (or, if the password rotated,
re-syncs) a dedicated account the first time it's called, then logs in
normally. It is always `read_only` and never `is_superuser`, regardless of
`AEGISNEX_DEMO_USERNAME`, and this cannot be changed by configuration - see
`src/auth.py`'s `seed_demo_user` and [Section "Demo security
verification"](#demo-security-guarantees) below. If
`AEGISNEX_DEMO_ENABLED=true` but `AEGISNEX_DEMO_PASSWORD` is unset, the
backend logs a clear warning at startup and `/api/auth/demo-login` returns
`503` with an actionable message rather than a silent failure.

A real administrator account, if you want one, is separate and off by
default too:

```bash
AEGISNEX_LOCAL_AUTH_ENABLED=true
AEGISNEX_SEED_DEFAULT_ADMIN=true
AEGISNEX_BOOTSTRAP_ADMIN_PASSWORD=<a strong secret>
```

### Demo security guarantees

The demo account is restricted at the RBAC layer, not just by convention -
verified by `tests/test_demo_login.py`:

- Always `role=read_only`, always `is_superuser=False`, regardless of
  `AEGISNEX_DEMO_USERNAME` (even if misconfigured to `admin`).
- Cannot read or write `/api/secrets` (403).
- Cannot start/stop/restart containers or run destructive
  infrastructure operations (403).
- Cannot manage users or roles (`/api/users/*` requires `ADMIN_ROLES` and,
  for role changes, `super_admin` specifically).
- Cannot install, configure, or uninstall integrations - `/api/integrations/
  install|{name}/uninstall|{name}` all require `OPERATOR_ROLES`+. There is
  no shell-execution endpoint reachable by any role; the only `subprocess`
  usage in the codebase is the Kubernetes integration provider
  (`src/integrations/providers/kubernetes.py`), which only runs `kubectl`
  for an integration that has already been installed/configured.
  **Operational note:** `POST /api/integrations/{name}/test` itself only
  requires `VIEWER_ROLES` (which includes `read_only`), so if an
  operator/admin *does* install the Kubernetes integration in a demo
  environment, the demo account could trigger a connection test against
  it. Do not install the Kubernetes (or any infrastructure-credentialed)
  integration in a public demo deployment.
- Cannot register or configure arbitrary scanners/webhooks - those routes
  require `OPERATOR_ROLES` or `ADMIN_ROLES`.

## 6. Health verification

```
GET /api/health         -> {"status": "ok", ...} (always 200, no auth)
GET /api/health/live     -> {"status": "alive"} (always 200, no auth)
GET /api/health/ready    -> {"status": "ready"} or {"status": "not_ready", ...}
```

`/api/health/ready` additionally checks database connectivity
(`PlatformRepository.health_check()`) and returns `not_ready` (still HTTP
200 - this is a body-level signal, not a status-code one) if Neon is
unreachable. All three also answer `OPTIONS` without auth for platform
health probes.

```bash
docker compose -f docker-compose.production.yml ps
# STATE column shows "healthy" once the compose healthchecks
# (backend: /api/health/live, frontend: /login) pass

curl -s https://app.example.com/api/health/ready | python -m json.tool
curl -s https://app.example.com/api/health/live
```

If `/api/health/ready` reports `not_ready`, check `AEGISNEX_DATABASE_URL`
and that Neon's IP allowlist (if configured) includes your egress IP.

## 7. Restart / recovery procedure

Because authentication, sessions, incidents, monitoring, reporting, and
governance data all live in Neon PostgreSQL (not the container
filesystem - see "Auth persistence" and "Other persistence" below), a
container restart is safe and stateless from the app's perspective:

```bash
# Restart everything:
docker compose -f docker-compose.production.yml restart

# Restart just the backend (e.g. after a config/env change):
docker compose -f docker-compose.production.yml up -d --force-recreate backend

# Full redeploy after a code change:
docker compose -f docker-compose.production.yml --env-file .env up -d --build

# Tail logs while diagnosing:
docker compose -f docker-compose.production.yml logs -f backend

# Recovery if a deploy is bad - roll back to the previous image/commit,
# then redeploy the same way. No database rollback is implied; only run
# `alembic downgrade` if the bad deploy actually changed schema.
```

What does **not** survive a restart, by design (see "Other persistence
changes" below): the local search FTS index (`src/search/indexer.py`)
rebuilds itself from Neon data automatically; anything written only to
`logs/` inside the container. Nothing in that set is user-facing data -
losing it costs a rebuild/re-log, not information.

## What's *not* covered here

- Local development (`AEGISNEX_ENV=development`, SQLite): unchanged, see
  `docs/DEPLOYMENT_GUIDE.md`.
- Non-Cloudflare reverse proxies (Nginx/Caddy): see
  `docs/DEPLOYMENT_GUIDE.md`'s "Reverse Proxy" section.
- Cloudflare **Workers** (a fundamentally different serverless runtime, not
  covered by this Docker-based architecture at all).
