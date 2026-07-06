# Figma Specification: Dashboard Mockup

## Purpose
Main dashboard overview screenshot for the README.

## Canvas
- Frame: 1440 × 900 px
- Background: `#0E1016`

## Layout Structure

### Sidebar (Left, 240px)
- Background: `#0A0C12`
- Border-right: 1px `rgba(255,255,255,0.04)`
- App logo + name at top (32px padding)
- Navigation items (14 items):
  - Dashboard (active, highlighted)
  - AI
  - Containers
  - Incidents
  - Infrastructure
  - Integrations
  - Audit
  - Notifications
  - Reports
  - Search
  - MCP
  - Targets
  - Settings
  - Admin
- Each item: 14px text, `rgba(255,255,255,0.5)`, 16px left icon (Lucide icons)
- Active item: `#5046E4` accent bar on left, white text

### Header (Top, 64px)
- Background: `#0E1016`
- Border-bottom: 1px `rgba(255,255,255,0.04)`
- Left: "Dashboard" title, 20px, semibold
- Right: Notification bell icon, avatar circle (32px) with initial

### Main Content Area

#### KPI Cards Row (4 cards, 312px each)
- Background: `#141822` with `rgba(255,255,255,0.04)` border
- Border radius: 12px
- Card 1 — System Health: green status dot + "Healthy" text, CPU/Memory mini progress bars
- Card 2 — Containers: "12 Running · 0 Stopped · 0 Unhealthy"
- Card 3 — Incidents: "3 Active · 27 Resolved"
- Card 4 — AI: "98% Confidence · 45 Workflows"

#### Charts Row (2 panels)
- Left panel (680px): TrendChart — CPU/Memory/Network timeseries over last 60 minutes
  - Area chart with gradient fill
  - 3 colored lines (chart-1, chart-2, chart-3)
  - Time axis on X, percentage on Y
  - Legend: CPU (blue), Memory (green), Network (orange)
- Right panel (460px): Container status donut chart
  - Running: green, Stopped: gray, Unhealthy: red
  - Center text: "12 containers"

#### Bottom Row (2 panels)
- Left (680px): Recent Incidents table
  - Columns: ID, Service, Severity, Status, Time
  - 5 rows with colored severity badges
  - "View All" link at bottom
- Right (460px): Recent Notifications feed
  - Timestamped entries with channel icon
  - "View All" link at bottom

## Typography
- Font: Inter
- Headers: 14px semibold, `rgba(255,255,255,0.7)` uppercase tracking
- Card values: 28px bold white
- Body: 13px regular, `rgba(255,255,255,0.6)`

## Color Palette (CSS Variables)
- `--primary`: `#5046E4`
- `--success`: `#10B981`
- `--warning`: `#F59E0B`
- `--danger`: `#EF4444`
- `--chart-1`: `#3B82F6`
- `--chart-2`: `#10B981`
- `--chart-3`: `#F97316`

## Export
- PNG, 1440 × 900 px
- Also @2x for retina
