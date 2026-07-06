# Figma Specification: Monitoring Pipeline Diagram

## Purpose
Flow diagram showing the monitoring pipeline from targets through remediation and notification.

## Canvas
- Frame: 1100 × 700 px
- Background: `#0E1016`

## Layout (Left-to-Right Flow)

### Stage 1 — Monitoring Targets (Left column)
- Vertical stack of 6 target type boxes:
  1. HTTP Endpoints (160 × 36px, `#1565C0`)
  2. SSL Certificates
  3. TCP Ports
  4. DNS Records
  5. System Resources (psutil)
  6. Docker Containers
- Each box: 11px text, white, monospace icon prefix

### Stage 2 — Monitors (Middle-left)
- 6 individual monitor boxes, aligned with targets:
  1. HTTP Monitor (`#1565C0`)
  2. SSL Monitor
  3. TCP Monitor
  4. DNS Monitor
  5. System Monitor
  6. Container Health Monitor
- Each: 160 × 36px, rounded

### Stage 3 — Orchestrator (Center)
- Larger box: 220 × 50px, `#E65100` (orange)
- "Monitoring Engine / Orchestrator"
- Receives arrows from all 6 monitors

### Stage 4 — Actions (Center-right)
Three parallel action paths:

**Path A — Guardian (Red):**
- Guardian box (`#D32F2F`, 200 × 40px)
- Arrow: Orchestrator → Guardian
- Guardian → (configurable cooldown + max attempts)
- Sub-label: "restart_cooldown: 300s, max_restart: 3"

**Path B — Incidents (Amber):**
- Incident Manager box (`#F57F17`, 200 × 50px)
- Status flow label: "Open → Acknowledged → In Progress → Resolved → Closed"
- Incident transitions recorded in audit log

**Path C — Metrics (Teal):**
- Prometheus Exporter box (`#E6522C`, 200 × 40px)
- Arrow to Grafana

### Stage 5 — Notifications (Right column)
- Notification Dispatcher (`#6A1B9A`, 200 × 50px)
- Connected from Incidents
- Channel boxes below:
  - Email (SMTP), Slack, Discord, PagerDuty, Teams, Webhook
  - Each: 100 × 28px, `#7B1FA2`

### Stage 6 — Dashboard (Top right)
- Dashboard box (`#2E7D32`, 200 × 45px)
- Connected from Orchestrator, Incidents, Notifications

## Arrow Styling
- Solid arrows: 2px stroke, matching source color
- Data flow arrows (to Grafana): dashed

## Typography
- Title: "Monitoring & Incident Pipeline", 22px white bold
- Body text: 11-12px, white
- Channel labels: 10px

## Export
- SVG preferred, PNG fallback
