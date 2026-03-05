# Use official Playwright Python image (includes all browser deps)
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

WORKDIR /app

# Copy and install Python deps first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser at build time
RUN playwright install chromium

# Copy application code
COPY . .

# Default: run as combined API + Worker
ENV RUN_MODE=both

# Run database migrations then start server
CMD ["bash", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1
