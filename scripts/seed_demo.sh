#!/usr/bin/env bash
# seed_demo.sh — Deploy all example data products for a live demo.
set -euo pipefail

log() { echo "[seed] $*"; }

log "Deploying example data products..."

uv run dpa deploy examples/customer_360.yml
uv run dpa deploy examples/order_events.yml

log ""
log "All products deployed. Summary:"
uv run dpa catalog list
