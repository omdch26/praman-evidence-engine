# Praman Evidence Engine — Production Docker Image
# Base: Python 3.11 slim, non-root user
# Purpose: Run on Render (free tier) or any container platform

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (minimal for security)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (security: never run as root in containers)
RUN useradd -m -u 1000 appuser

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY praman/ ./praman/
COPY praman/main.py ./

# Change ownership to non-root user
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (matches PORT env var, default 8000)
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run FastAPI app
CMD ["uvicorn", "praman.main:app", "--host", "0.0.0.0", "--port", "8000"]
