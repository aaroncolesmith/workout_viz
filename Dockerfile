# ── Stage 1: Build React frontend ─────────────────────────────────────────────
FROM node:22-alpine AS frontend-builder

# Passed in at deploy time (flyctl deploy --build-arg GIT_SHA=...) — the
# build context has no .git dir, so vite.config.js can't shell out to git.
ARG GIT_SHA=unknown
ENV VITE_GIT_SHA=$GIT_SHA

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --silent
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python backend + static files ────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Backend source
COPY backend/ ./backend/

# Frontend dist from stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Data directory (Fly.io mounts the persistent volume here)
RUN mkdir -p /data

ENV DATA_DIR=/data
ENV PORT=8080

EXPOSE 8080

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
