# AegisNex Grafana Support

## Architecture

AegisNex exposes operational metrics through the FastAPI dashboard at
`/metrics`. Prometheus scrapes that endpoint, and Grafana provisions a
Prometheus datasource plus four dashboards from this repository.

```text
AegisNex FastAPI /metrics -> Prometheus -> Grafana dashboards
```

## Folder Structure

```text
grafana/
  docker-compose.yml
  prometheus/prometheus.yml
  provisioning/datasources/prometheus.yml
  provisioning/dashboards/aegisnex.yml
  dashboards/infrastructure.json
  dashboards/containers.json
  dashboards/incidents.json
  dashboards/remediation.json
docs/grafana/
  README.md
  screenshots/.gitkeep
```

## Dashboard Descriptions

- Infrastructure Dashboard: CPU, memory, disk, and network throughput.
- Container Dashboard: running, stopped, and unhealthy container counts.
- Incident Dashboard: active incidents, resolved incidents, total incidents, and trends.
- Remediation Dashboard: restart attempts, successful restarts, failed restarts, and trends.

## Setup Instructions

1. Start AegisNex dashboard so `/metrics` is available:

   ```bash
   uvicorn src.dashboard:create_app --factory --host 0.0.0.0 --port 8000
   ```

2. Start Prometheus and Grafana:

   ```bash
   cd grafana
   docker compose up -d
   ```

3. Open Grafana:

   ```text
   http://localhost:3000
   ```

4. Login with:

   ```text
   username: admin
   password: admin
   ```

5. Open the `AegisNex` folder in Grafana dashboards.

## Local Development

- Prometheus UI: `http://localhost:9090`
- Grafana UI: `http://localhost:3000`
- AegisNex metrics: `http://localhost:8000/metrics`

If AegisNex runs inside Docker instead of on the host, update
`grafana/prometheus/prometheus.yml` to target the service name and port.

## Screenshots

Place screenshots here when validating dashboards:

- `docs/grafana/screenshots/infrastructure.png`
- `docs/grafana/screenshots/containers.png`
- `docs/grafana/screenshots/incidents.png`
- `docs/grafana/screenshots/remediation.png`
