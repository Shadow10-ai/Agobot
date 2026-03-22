FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for LightGBM and scientific packages
RUN apt-get update && apt-get install -y \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway injects $PORT at runtime)
EXPOSE 8001

# Single uvicorn worker — required for shared in-memory bot state + asyncio bot loop
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8001} --workers 1"]
