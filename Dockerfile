# media.rip() — multi-stage Docker build
# Stage 1: Build frontend (Node)
# Stage 2: Install backend deps (Python)
# Stage 3: Slim runtime with ffmpeg
#
# Image: ghcr.io/xpltdco/media-rip
# Platforms: linux/amd64, linux/arm64

# ── Stage 1: Frontend build ──────────────────────────────────────────
FROM node:22-slim AS frontend-builder

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python dependencies ─────────────────────────────────────
FROM python:3.12-slim AS python-deps

WORKDIR /build
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 3: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Install ffmpeg (required by yt-dlp for muxing/transcoding)
# Install deno (required by yt-dlp for YouTube JS interpretation)
# Keep curl for Docker healthcheck probes
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    apt-get purge -y unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages from deps stage
COPY --from=python-deps /install /usr/local

# Create non-root user
RUN useradd --create-home --shell /bin/bash mediarip

# Application code
WORKDIR /app
COPY backend/ ./

# Inject version from build arg (set by CI from git tag)
ARG APP_VERSION=dev
RUN echo "__version__ = \"${APP_VERSION}\"" > app/__version__.py

# Copy built frontend into backend static dir
COPY --from=frontend-builder /build/frontend/dist ./static

# Create default directories
RUN mkdir -p /downloads /data && \
    chown -R mediarip:mediarip /downloads /data

# Harden: strip SUID/SGID bits (unnecessary in a single-purpose container)
RUN find / -perm -4000 -exec chmod u-s {} + 2>/dev/null; \
    find / -perm -2000 -exec chmod g-s {} + 2>/dev/null; \
    true

# Harden: make app source read-only (only /downloads and /data are writable)
RUN chmod -R a-w /app

USER mediarip

# Environment defaults
ENV MEDIARIP__DOWNLOADS__OUTPUT_DIR=/downloads \
    MEDIARIP__SERVER__DB_PATH=/data/mediarip.db \
    MEDIARIP__SERVER__DATA_DIR=/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${MEDIARIP__SERVER__PORT:-8000}/api/health || exit 1

CMD ["python", "start.py"]
