# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------------
# Stage 1: Build the Vue 3 frontend.
# ----------------------------------------------------------------------------
FROM node:20-alpine AS frontend-builder

WORKDIR /build/frontend

# Install dependencies first (cacheable layer).
COPY frontend/package.json frontend/package-lock.json* frontend/pnpm-lock.yaml* frontend/yarn.lock* ./
RUN \
    if [ -f package-lock.json ]; then npm ci; \
    elif [ -f pnpm-lock.yaml ]; then corepack enable pnpm && pnpm install --frozen-lockfile; \
    elif [ -f yarn.lock ]; then corepack enable yarn && yarn install --frozen-lockfile; \
    else npm install; \
    fi

# Copy sources and build.
COPY frontend/ ./
RUN npm run build

# ----------------------------------------------------------------------------
# Stage 2: Runtime image.
# ----------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: Pillow + Playwright (optional, only if CLOUDFLARE_SOLVER=playwright).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libjpeg-dev \
        zlib1g-dev \
        libwebp-dev \
        libxml2-dev \
        libxslt1-dev \
        sqlite3 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user.
RUN groupadd -g 1000 mangasama && useradd -u 1000 -g mangasama -m -s /bin/bash mangasama

WORKDIR /app

# Install Python deps first (cacheable). README.md + LICENSE are required by
# hatchling at build time (pyproject `readme` / `license` point at them).
COPY pyproject.toml README.md LICENSE ./
COPY app/ ./app/
RUN pip install --upgrade pip && \
    pip install . && \
    pip cache purge || true

# Copy config + migrations + entrypoint.
COPY config/ ./config/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && sed -i 's/\r$//' /entrypoint.sh

# Copy the built SPA. Vite's outDir is `<repo>/app/web`, which in the builder
# stage resolves to `/build/app/web` (one level up from /build/frontend).
COPY --from=frontend-builder /build/app/web/ /app/app/web/

# Pre-create persistent dirs.
RUN mkdir -p /data /config && chown -R mangasama:mangasama /data /config /app

USER mangasama

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=5).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
# `python -m uvicorn` (not the console script) so the working dir /app is on
# sys.path and the local `app` package — which contains the built `app/web` —
# is the one imported (main.py derives the SPA dir from app.main.__file__).
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
