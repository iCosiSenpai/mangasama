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

# Install Python deps first (cacheable).
COPY pyproject.toml ./
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

# Copy built frontend.
COPY --from=frontend-builder /build/frontend/ ../frontend-dist-tmp/
RUN if [ -d /frontend-dist-tmp/dist ]; then cp -r /frontend-dist-tmp/dist/* /app/app/web/; \
    elif [ -d /frontend-dist-tmp/app/web ]; then cp -r /frontend-dist-tmp/app/web/* /app/app/web/; \
    fi && rm -rf /frontend-dist-tmp

# Pre-create persistent dirs.
RUN mkdir -p /data /config && chown -R mangasama:mangasama /data /config /app

USER mangasama

EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/health', timeout=5).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
