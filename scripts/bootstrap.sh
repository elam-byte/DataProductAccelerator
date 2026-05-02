#!/usr/bin/env bash
# bootstrap.sh — Start the DPA local stack and wait until all services are healthy.
set -euo pipefail

log() { echo "[bootstrap] $*"; }

log "Starting core services (MinIO + Iceberg REST + Dagster)..."
docker compose up -d

# Wait for MinIO
log "Waiting for MinIO..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:9000/minio/health/live > /dev/null 2>&1; then
    log "MinIO ready"
    break
  fi
  sleep 2
done

# Wait for Iceberg REST catalog
log "Waiting for Iceberg REST catalog..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8181/v1/config > /dev/null 2>&1; then
    log "Iceberg REST ready"
    break
  fi
  sleep 3
done

# Wait for Dagster webserver
log "Waiting for Dagster..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:3000/server_info > /dev/null 2>&1; then
    log "Dagster ready"
    break
  fi
  sleep 3
done

log ""
log "Stack is ready!"
log ""
log "  MinIO console:  http://localhost:9001  (minioadmin / minioadmin)"
log "  Iceberg REST:   http://localhost:8181"
log "  Dagster UI:     http://localhost:3000"
log ""
log "Run: make demo   — to deploy example data products"
