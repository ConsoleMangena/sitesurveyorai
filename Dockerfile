# ==============================================================================
# SiteSurveyor AI — Production Dockerfile for Render / Cloud Deployment
# ==============================================================================
# 3.14, not 3.11: pyproj and rasterio both require Python >=3.12 since the releases whose
# bundled PROJ data agree with each other. On 3.11 pip silently resolves the older pair,
# where rasterio's vendored libproj rejects pyproj's proj.db
# ("DATABASE.LAYOUT.VERSION.MINOR = 4 whereas a number >= 6 is expected") and every CRS
# lookup fails at import. The image now takes the same wheels the test suite runs against.
FROM python:3.14-slim

# Avoid prompts from debian frontends
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Survey cache + published deliverables. Point this at a mounted disk in production; on a
# plain `docker run` it simply lives inside the container and is lost with it.
ENV SITESURVEYOR_STATE_DIR=/app/state
# Coverages are read as remote COGs; without this GDAL lists the whole S3 prefix
# on every open, which turns each layer read into a multi-second stall.
# PORT is deliberately not set here — the platform injects it at runtime.
ENV GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR
# Strict memory caps to prevent OOM on 512MB RAM cloud tiers
ENV GDAL_CACHEMAX=32
ENV MAP_DPI=90
ENV MALLOC_TRIM_THRESHOLD_=65536

# Install runtime dependencies.
# libexpat1 is not optional: the manylinux rasterio wheel vendors GDAL/PROJ, whose
# SQLite-backed coordinate-database load links against libexpat.so.1. python:*-slim
# does not ship it, so "import rasterio" raises ImportError in the container and the
# instance restarts in a loop before /health is ever reachable.
# No proj-data package: both wheels ship their own PROJ database, and src/config.py
# points PROJ_DATA at pyproj's copy, so a system dataset (Debian trixie's is layout 5)
# would only add a third version for the two libraries to disagree about.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgomp1 \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency manifest and install Python wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code and configurations
COPY src/ ./src/
COPY main.py .

# Create persistent cache & outputs directories
RUN mkdir -p /app/state/data/raw /app/state/data/external /app/state/outputs

# Import the app once during the build. A missing shared library or module otherwise
# surfaces only as a restarting instance and a 502, with the traceback buried in runtime
# logs; this turns it into a build failure that names the missing piece.
RUN python -c "import src.api; print('app imports clean')"

EXPOSE 8000

# The port and worker count live in a script, not here: see docker-entrypoint.sh.
# No Docker HEALTHCHECK either -- it cannot reference the runtime-assigned $PORT without
# the same substitution trap, and Render health-checks through healthCheckPath instead.
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

