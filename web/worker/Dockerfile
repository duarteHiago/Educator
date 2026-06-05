FROM python:3.12-slim

WORKDIR /app

# Install both requirement sets then add psycopg2 for sync DB access
COPY requirements.txt /tmp/requirements_automation.txt
COPY web/backend/requirements.txt /tmp/requirements_web.txt
RUN pip install --no-cache-dir \
    -r /tmp/requirements_automation.txt \
    -r /tmp/requirements_web.txt \
    psycopg2-binary==2.9.9

# Install Chromium and its system dependencies
RUN playwright install chromium --with-deps

COPY backend/ /app/backend/
COPY web/backend/app/ /app/app/

ENV PYTHONPATH=/app
