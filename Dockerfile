# ==============================================================================
# Production Dockerfile for Hanoi IT Job Radar Bot
# Python 3.10 + Playwright Chromium dependencies
# ==============================================================================

FROM python:3.10-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Ho_Chi_Minh \
    DEBIAN_FRONTEND=noninteractive

# Set working directory
WORKDIR /app

# Install system dependencies and tzdata
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tzdata \
    ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium browser and its system shared libraries
RUN playwright install --with-deps chromium

# Copy application source code
COPY . .

# Create directories for persistent volumes
RUN mkdir -p /app/data /app/logs /app/cookies

# Run as non-root or default container user
CMD ["python", "main.py"]

