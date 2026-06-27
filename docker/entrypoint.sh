#!/usr/bin/env bash
# MangaSama entrypoint: run migrations, then exec the CMD.
set -euo pipefail

cd /app

echo "[mangasama] Starting at $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "[mangasama] DATA_DIR=${DATA_DIR:-/data}  CONFIG_DIR=${CONFIG_DIR:-/config}"

# Ensure persistent dirs exist.
mkdir -p "${DATA_DIR:-/data}" "${CONFIG_DIR:-/config}/cookies" "${CONFIG_DIR:-/config}/.cache" "${CONFIG_DIR:-/config}/backups" "${DATA_DIR:-/data}/downloads" "${DATA_DIR:-/data}/covers"

# Seed default YAML into the persistent config volume on first boot.
# Runtime reads CONFIG_DIR (/config); the image ships defaults under /app/config/.
for f in default.yaml sources.yaml logging.yaml; do
  if [ ! -f "${CONFIG_DIR:-/config}/${f}" ] && [ -f "/app/config/${f}" ]; then
    echo "[mangasama] Seeding ${CONFIG_DIR:-/config}/${f} from image defaults"
    cp "/app/config/${f}" "${CONFIG_DIR:-/config}/${f}"
  fi
done

# Run Alembic migrations.
echo "[mangasama] Running database migrations..."
alembic upgrade head

# Hand off to CMD (default: uvicorn).
echo "[mangasama] Launching: $*"
exec "$@"
