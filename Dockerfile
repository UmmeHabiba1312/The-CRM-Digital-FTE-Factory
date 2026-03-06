FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY database/     database/
COPY kafka_client.py .
COPY production/   production/

# Non-root user (security)
RUN useradd -m -u 1000 fte
USER fte

EXPOSE 8000

# Default: run API (override for worker)
CMD ["uvicorn", "production.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
