# media.rip() Docker Build
#
# Multi-stage build:
#   1. frontend-build: Install npm deps + build Vue 3 SPA
#   2. backend-deps:   Install Python deps into a virtual env
#   3. runtime:        Copy built assets + venv into minimal image
#
# Usage:
#   docker build -t media-rip .
#   docker run -p 8080:8000 -v ./downloads:/downloads media-rip

# ══════════════════════════════════════════
# Stage 1: Build frontend
# ══════════════════════════════════════════
FROM node:20-slim AS frontend-build

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ══════════════════════════════════════════
# Stage 2: Install Python dependencies
# ══════════════════════════════════════════
FROM python:3.12-slim AS backend-deps

WORKDIR /build

# Install build tools needed for some pip packages (bcrypt, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ══════════════════════════════════════════
# Stage 3: Runtime image
# ══════════════════════════════════════════
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="media.rip()"
LABEL org.opencontainers.image.description="Self-hostable yt-dlp web frontend"
LABEL org.opencontainers.image.source="https://github.com/jlightner/media-rip"

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (latest stable)
RUN pip install --no-cache-dir yt-dlp

# Copy virtual env from deps stage
COPY --from=backend-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set up application directory
WORKDIR /app

# Copy backend source
COPY backend/app ./app

# Copy built frontend into static serving directory
COPY --from=frontend-build /build/dist ./static

# Create directories for runtime data
RUN mkdir -p /downloads /themes /data

# Default environment
ENV MEDIARIP__SERVER__HOST=0.0.0.0 \
    MEDIARIP__SERVER__PORT=8000 \
    MEDIARIP__SERVER__DB_PATH=/data/mediarip.db \
    MEDIARIP__DOWNLOADS__OUTPUT_DIR=/downloads \
    MEDIARIP__THEMES_DIR=/themes \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Volumes for persistent data
VOLUME ["/downloads", "/themes", "/data"]

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
