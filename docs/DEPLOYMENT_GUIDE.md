# Deployment Guide

## Prerequisites

| Component         | Version / Spec                        |
|-------------------|---------------------------------------|
| Python            | >= 3.11                               |
| pip               | >= 23.0                               |
| Node.js           | >= 18 (for dashboard frontend builds) |
| Docker            | >= 24.0 (optional, container features)|
| SQLite            | Built-in (dev/small deployments)      |
| PostgreSQL        | >= 14 (production multi-tenant)       |
| Redis             | >= 7.0 (optional, for scheduling)     |

## Quick Start (Development)

```powershell
# 1. Clone and enter repository
git clone <repo-url> aegisnex
cd aegisnex

# 2. Create virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
copy .env.example .env
# Edit .env with your settings

# 5. Initialize database
python -m src.scripts.init_db

# 6. Run the application
python -m uvicorn src.dashboard:app --reload --port 8000

# 7. Open browser
start http://localhost:8000
```

---

## Configuration

### Environment Variables (`.env`)

| Variable                     | Required | Default              | Description                           |
|------------------------------|----------|----------------------|---------------------------------------|
| `AEGISNEX_SECRET_KEY`        | Yes      | —                    | JWT signing secret                    |
| `AEGISNEX_DATABASE_URL`      | No       | `sqlite:///aegisnex.db` | Database connection string         |
| `AEGISNEX_REDIS_URL`         | No       | `redis://localhost:6379` | Redis connection string (optional) |
| `AEGISNEX_LOG_LEVEL`         | No       | `INFO`               | Logging level                        |
| `AEGISNEX_CORS_ORIGINS`      | No       | `*`                  | Allowed CORS origins                  |
| `AEGISNEX_JWT_ALGORITHM`     | No       | `HS256`              | JWT signing algorithm                 |
| `AEGISNEX_ACCESS_TOKEN_EXPIRE_MINUTES` | No | `30`          | Token expiry                          |
| `OPENAI_API_KEY`             | Varies   | —                    | Required for OpenAI provider          |
| `ANTHROPIC_API_KEY`          | Varies   | —                    | Required for Anthropic provider       |
| `OLLAMA_BASE_URL`            | No       | `http://localhost:11434` | Ollama base URL                   |
| `AEGISNEX_AI_PROVIDER`       | No       | `openai`             | Default AI provider                   |
| `AEGISNEX_AI_MODEL`          | No       | `gpt-4o`             | Default AI model                      |

### AI Provider Config

Edit `src/intelligence/providers/config.yaml`:

```yaml
providers:
  openai:
    api_key: ${OPENAI_API_KEY}
    models: [gpt-4o, gpt-4o-mini, gpt-4-turbo]
    default_model: gpt-4o
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    models: [claude-3-opus, claude-3-sonnet, claude-3-haiku]
    default_model: claude-3-sonnet
  ollama:
    base_url: http://localhost:11434
    models: [llama3, mistral, codellama]
    default_model: llama3
  bedrock:
    region: us-east-1
    models: [claude-3-sonnet, claude-3-haiku]
    default_model: claude-3-sonnet
  azure:
    endpoint: https://<resource>.openai.azure.com
    api_key: ${AZURE_OPENAI_API_KEY}
    models: [gpt-4o]
    default_model: gpt-4o
```

---

## Production Deployment

### Option 1: Docker Compose (Recommended)

```yaml
# docker-compose.yml
version: "3.9"
services:
  aegisnex:
    build: .
    ports:
      - "8000:8000"
    environment:
      - AEGISNEX_SECRET_KEY=${AEGISNEX_SECRET_KEY}
      - AEGISNEX_DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/aegisnex
      - AEGISNEX_REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    volumes:
      - ./data:/app/data
    restart: unless-stopped
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: aegisnex
      POSTGRES_USER: aegisnex
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aegisnex"]
  redis:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
volumes:
  pgdata:
  redisdata:
```

```powershell
# Build and start
docker compose build
docker compose up -d

# View logs
docker compose logs -f aegisnex
```

### Option 2: Kubernetes

```yaml
# aegisnex-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: aegisnex
spec:
  replicas: 2
  selector:
    matchLabels:
      app: aegisnex
  template:
    metadata:
      labels:
        app: aegisnex
    spec:
      containers:
      - name: aegisnex
        image: aegisnex:latest
        ports:
        - containerPort: 8000
        env:
        - name: AEGISNEX_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: aegisnex-secrets
              key: secret-key
        - name: AEGISNEX_DATABASE_URL
          value: "postgresql+asyncpg://aegisnex:$(DB_PASSWORD)@postgres:5432/aegisnex"
        readinessProbe:
          httpGet:
            path: /api/health
            port: 8000
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2"
```

### Option 3: Bare Metal / VM

```powershell
# Using systemd (Linux) or NSSM (Windows)

# Install NSSM for Windows service
nssm install AegisNex "C:\path\to\venv\Scripts\uvicorn.exe" "src.dashboard:app --host 0.0.0.0 --port 8000 --workers 4"
nssm set AegisNex AppDirectory "C:\path\to\aegisnex"
nssm start AegisNex
```

---

## Database Setup

### SQLite (Default)

```powershell
# Database auto-created at startup
# Or manually:
python -m src.scripts.init_db
```

### PostgreSQL (Production)

```sql
-- Create database and user
CREATE USER aegisnex WITH PASSWORD '<password>';
CREATE DATABASE aegisnex OWNER aegisnex;
GRANT ALL PRIVILEGES ON DATABASE aegisnex TO aegisnex;

-- Run migrations
python -m src.scripts.migrate
```

Connection string: `postgresql+asyncpg://aegisnex:<password>@<host>:5432/aegisnex`

---

## Reverse Proxy

### Nginx

```nginx
server {
    listen 443 ssl;
    server_name aegisnex.example.com;

    ssl_certificate /etc/ssl/certs/aegisnex.crt;
    ssl_certificate_key /etc/ssl/private/aegisnex.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
        proxy_send_timeout 120s;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400s;
    }
}
```

### Caddy

```
aegisnex.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

---

## Scaling Considerations

| Factor                | Sizing Guideline                                |
|-----------------------|-------------------------------------------------|
| **Concurrent users**  | 1–2 GB RAM per 100 concurrent users             |
| **AI requests**       | 1–2 GB RAM per 10 concurrent AI queries         |
| **Monitoring targets**| 500 targets per GB RAM (in-memory cache)        |
| **Database**          | PostgreSQL recommended above 1M audit log rows  |
| **Workers**           | `2–4 * CPU cores` for uvicorn workers           |
| **Redis**             | Required for multi-worker scheduling            |
| **WebSocket**         | ~10K concurrent connections per 1 GB RAM        |

---

## Health Check Endpoints

| Endpoint              | Purpose                                  |
|-----------------------|------------------------------------------|
| `GET /api/health`     | Overall system health                    |
| `GET /api/health/db`  | Database connectivity                    |
| `GET /api/health/ai`  | AI provider connectivity                 |
| `GET /api/health/ws`  | WebSocket server status                  |

---

## Upgrade Procedure

```powershell
# 1. Backup database
python -m src.scripts.backup --output .\backups\pre-upgrade.db

# 2. Pull latest code
git pull origin main

# 3. Update dependencies
pip install -r requirements.txt --upgrade

# 4. Run migrations
python -m src.scripts.migrate

# 5. Restart application
# (if Docker: docker compose restart aegisnex)
```

---

## Backup & Restore

```powershell
# Backup
python -m src.scripts.backup --output .\backups\aegisnex-backup-%date:~10,4%%date:~4,2%%date:~7,2%.db

# Restore
python -m src.scripts.restore --input .\backups\aegisnex-backup-20250115.db
```

---

## Monitoring & Observability

Configure Prometheus metrics via `PrometheusExporter`:

```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'aegisnex'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/api/metrics'
```

Alerting thresholds can be configured in `src/intelligence/runbooks/` and via the Alert Rules UI at `/api/alerts/rules`.
