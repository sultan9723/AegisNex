# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| 3.x (latest) | ✅ |
| < 3.0 | ❌ |

## Reporting a Vulnerability

We take security vulnerabilities seriously. Please report them responsibly.

**Do not** open public issues for security vulnerabilities.

Instead, send a detailed report to **security@aegisnex.io**.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact
- Suggested fix (if any)

### Response Timeline

| Timeframe | Action |
|---|---|
| 24 hours | Acknowledgment of receipt |
| 7 days | Initial assessment and severity classification |
| 30 days | Fix released for critical/high severity |
| 60 days | Fix released for medium/low severity |

## Security Features

### Authentication & Authorization

| Layer | Mechanism |
|---|---|
| API Authentication | JWT (access + refresh tokens), API keys (`X-API-Key` header) |
| Role-Based Access | `admin`, `operator`, `viewer` roles |
| Rate Limiting | `slowapi` with per-route limits |
| Session | HttpOnly, Secure, SameSite cookies |

### AI Safety

| Layer | Mechanism |
|---|---|
| Risk Assessment | Per-tool scoring (0–1), configurable auto-execute threshold |
| Policy Engine | 6 default policies (deny, require_approval) |
| Approval Gates | Destructive actions require human approval |
| Audit Logging | All tool executions recorded |

### Data Protection

| Concern | Implementation |
|---|---|
| Secrets | Environment variables, never hardcoded |
| Database | SQLite (dev), PostgreSQL (prod) with TLS |
| Password Storage | Hashed with bcrypt/argon2 |
| API Keys | Hashed before storage |

## Dependency Security

We use `pip-audit` in CI to scan for known vulnerabilities in dependencies. Dependencies are pinned in `requirements.txt` and reviewed regularly.

## Security Hardening

For production deployments:

1. Set `AEGISNEX_JWT_SECRET` to a 256-bit random value
2. Use HTTPS via reverse proxy (Nginx/Caddy)
3. Configure `AEGISNEX_CORS_ORIGINS` to specific origins
4. Enable rate limiting
5. Use PostgreSQL instead of SQLite
6. Run workers as non-root user
7. Enable `AEGISNEX_ENV=production` to disable debug endpoints
8. Configure Prometheus metrics with bearer token authentication
