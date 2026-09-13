# AegisNex FastAPI backend - production image for Azure Container Apps.
# Optional infra (Redis, Grafana, Prometheus, Postgres, Nmap/Nuclei, Docker socket)
# is intentionally NOT included here; the app must boot without it.
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AEGISNEX_ENV=production \
    AEGISNEX_DATA_DIR=/app/data \
    PORT=8000

RUN addgroup --system aegisnex \
    && adduser --system --ingroup aegisnex --home /app aegisnex \
    && install -d -o aegisnex -g aegisnex /app/data \
    && chown aegisnex:aegisnex /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=aegisnex:aegisnex . .

USER aegisnex

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=3)" || exit 1

# --proxy-headers/--forwarded-allow-ips trusts the managed ingress in front of
# the container so HTTPS scheme and client IP are interpreted from forwarded headers.
CMD ["uvicorn", "src.dashboard:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
