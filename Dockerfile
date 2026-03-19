# media.rip() — multi-stage Docker build
# Stage 1: Build frontend (Node)
# Stage 2: Install backend deps (Python)
# Stage 3: Slim runtime with ffmpeg
#
# Image: ghcr.io/xpltd/media-rip
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
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl unzip && \
    curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh && \
    apt-get purge -y curl unzip && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Copy Python packages from deps stage
COPY --from=python-deps /install /usr/local

# Create non-root user
RUN useradd --create-home --shell /bin/bash mediarip

# Application code
WORKDIR /app
COPY backend/ ./

# Copy built frontend into backend static dir
COPY --from=frontend-builder /build/frontend/dist ./static

# Create default directories
RUN mkdir -p /downloads /data && \
    chown -R mediarip:mediarip /app /downloads /data

USER mediarip

# Environment defaults
ENV MEDIARIP__DOWNLOADS__OUTPUT_DIR=/downloads \
    MEDIARIP__DATABASE__PATH=/data/mediarip.db \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
