# Figma Specification: Deployment Architecture Diagram

## Purpose
Infrastructure diagram showing production deployment topology.

## Canvas
- Frame: 1000 × 700 px
- Background: `#0E1016`

## Layout (Top-to-Bottom with two columns)

### Row 1 — User Access
- **Browser** icon (left): 140 × 50px, `#37474F`
- **Nginx/Caddy** (center): 160 × 50px, `#009688`
- Arrow: Browser → Nginx

### Row 2 — Application (Parallel)
- **Left:** Frontend (Next.js 14), 180 × 50px, `#5046E4`
  - Port 3000
  - Static assets + SSR
- **Right:** Backend (FastAPI/Uvicorn), 200 × 50px, `#E65100`
  - Port 8000
  - 2-4 workers
  - Gunicorn (production)
- Arrow: Nginx → Both
- Arrow: Frontend → Backend (HTTP/WS)

### Row 3 — Data Stores (Parallel, three columns)
- **Left:** PostgreSQL 16+, 180 × 50px, `#4169E1`
  - Primary database
  - Connection: `AEGISNEX_DATABASE_URL`
- **Center:** Redis 7+, 180 × 50px, `#D32F2F`
  - Scheduler + Cache (optional)
  - Dashed border to indicate optional
- **Right:** Docker Engine, 180 × 50px, `#2496ED`
  - Container management
  - Socket connection
- Arrows: Backend → All three

### Row 4 — Observability (Left column only)
- **Prometheus**, 180 × 50px, `#E6522C`
  - Scrapes `/metrics` every 15s
  - Arrow from Backend (dashed, labeled "scrape")
- **Grafana**, 180 × 50px, `#F46800`
  - 4 pre-provisioned dashboards
  - Arrow: Prometheus → Grafana

### Visual Container
- Large dashed box around Backend + PostgreSQL + Redis labeled "Docker / Kubernetes Pod"
- Optional secondary dashed box around Prometheus + Grafana labeled "Monitoring Stack"

### Legend
- Bottom-right corner
- Solid line: Direct connection
- Dashed line: Optional / scrape
- Colors: Blue = data, Orange = app, Green = proxy, Red = cache

## Typography
- Title: "Deployment Architecture", 22px white bold
- Port numbers in smaller text below names
- Connection labels: 10px

## Export
- SVG preferred
- Include .fig file reference for editable version
