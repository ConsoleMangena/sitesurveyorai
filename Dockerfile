# ==============================================================================
# SiteSurveyor AI — Production Dockerfile for Render / Cloud Deployment
# ==============================================================================
FROM python:3.11-slim

# Avoid prompts from debian frontends
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libgomp1 \
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
RUN mkdir -p /app/data/raw /app/outputs

EXPOSE 8000

# Health check using Render's $PORT or fallback 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start FastAPI + MCP SSE server via Uvicorn
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]

