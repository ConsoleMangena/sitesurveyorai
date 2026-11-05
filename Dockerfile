# ==============================================================================
# SiteSurveyor AI — Production Dockerfile for Render / Cloud Deployment
# ==============================================================================
FROM python:3.11-slim

# Avoid prompts from debian frontends
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Coverages are read as remote COGs; without this GDAL lists the whole S3 prefix
# on every open, which turns each layer read into a multi-second stall.
# PORT is deliberately not set here — the platform injects it at runtime.
ENV GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR

# Install runtime dependencies.
# libexpat1 is not optional: the manylinux rasterio wheel vendors GDAL/PROJ, whose
# SQLite-backed coordinate-database load links against libexpat.so.1. python:*-slim
# does not ship it, so "import rasterio" raises ImportError in the container and the
# instance restarts in a loop before /health is ever reachable.
# proj-data settles a second clash: pyproj points PROJ_DATA at its own bundled proj.db,
# rasterio's newer vendored libproj rejects it ("DATABASE.LAYOUT.VERSION.MINOR = 4
# whereas a number >= 6 is expected. It comes from another PROJ installation") and every
# CRS lookup dies. One system dataset is the only version both wheels can read.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgomp1 \
    libexpat1 \
    proj-data \
    && rm -rf /var/lib/apt/lists/*

ENV PROJ_DATA=/usr/share/proj \
    PROJ_LIB=/usr/share/proj

WORKDIR /app

# Copy dependency manifest and install Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and configurations
COPY src/ ./src/
COPY main.py .

# Create persistent cache & outputs directories
RUN mkdir -p /app/data/raw /app/outputs

# Import the app once during the build. A missing shared library or module otherwise
# surfaces only as a restarting instance and a 502, with the traceback buried in runtime
# logs; this turns it into a build failure that names the missing piece.
RUN python -c "import src.api; print('app imports clean')"

EXPOSE 8000

# $$ escapes Dockerfile substitution so ${PORT} is read from the *runtime* environment.
# Written unescaped, Docker resolves it at build time and bakes in 8000 -- the image then
# listens on a port Render never routes to, because Render assigns $PORT per instance.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -sf "http://localhost:$${PORT:-8000}/health" || exit 1

# Start FastAPI + MCP SSE server via Uvicorn.
# One worker is deliberate: the engines read the AOI from process-global src.config and
# every survey writes the same fixed filenames under /app/outputs. Multiple workers would
# each hold their own config and lock, so two concurrent requests could analyse different
# sites while overwriting each other's deliverables. Raise this only after the planned
# immutable per-job SiteContext + namespaced output directory lands.
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port $${PORT:-8000} --workers 1"]

