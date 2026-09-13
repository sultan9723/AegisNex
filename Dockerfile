FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    AEGISNEX_ENV=production

WORKDIR /app

RUN addgroup --system aegisnex \
    && adduser --system --ingroup aegisnex --home /app aegisnex

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY --chown=aegisnex:aegisnex alembic.ini config.yaml ./
COPY --chown=aegisnex:aegisnex alembic ./alembic
COPY --chown=aegisnex:aegisnex assets ./assets
COPY --chown=aegisnex:aegisnex modules ./modules
COPY --chown=aegisnex:aegisnex src ./src
COPY --chown=aegisnex:aegisnex static ./static
COPY --chown=aegisnex:aegisnex templates ./templates

RUN mkdir -p /app/data /app/logs /app/reports \
    && chown -R aegisnex:aegisnex /app

USER aegisnex

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.dashboard:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
