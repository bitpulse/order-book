FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY live/ ./live/

# Create logs directory
RUN mkdir -p logs

# Note: .env is NOT copied - environment variables are passed at runtime via docker run -e

# Default command (can be overridden in docker-compose.yml)
CMD ["python", "live/orderbook_tracker.py", "--help"]