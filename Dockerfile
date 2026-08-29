FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY app/ app/
COPY migrations/ migrations/
COPY scripts/ scripts/
COPY alembic.ini .

# Create data directories
RUN mkdir -p data/raw data/exports

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Expose no ports (CLI tool, not a web server)

# Default command
CMD ["python", "-m", "app.main", "collect-once"]
