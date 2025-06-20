# Use a lightweight Python base image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    libcairo2-dev \
    libglib2.0-0 \
    libpoppler-cpp-dev \
    gcc \
    git \
    pkg-config \
    libcairo2-dev \
    python3-dev \
    libpango1.0-dev \
    libgdk-pixbuf2.0-dev \
    libgirepository1.0-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logging /app/vectorstores && \
    chown -R appuser:appuser /app/logging /app/vectorstores

# Switch to non-root user
USER appuser

# Expose the Flask port
EXPOSE 5000

# Set memory limits
ENV PYTHONMALLOC=malloc
ENV PYTHONMALLOCSTATS=1

# Add healthcheck
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Start the Flask application with gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "app:app"]
