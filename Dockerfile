# Use official Python runtime as base image
FROM python:3.9-slim

# Set working directory in container
WORKDIR /app

# Define build argument for model source directory
ARG MODEL_SOURCE_DIR

# Create data directory and copy model
RUN mkdir -p /app/data/model
COPY ${MODEL_SOURCE_DIR}/* /app/data/model

# Define environment variables with defaults (can be overridden at runtime)
ENV PUBLIC_LISTEN_IP="0.0.0.0" \
    PUBLIC_LISTEN_PORT=8080 \
    INTERNAL_LISTEN_IP="0.0.0.0" \
    INTERNAL_LISTEN_PORT=8081 \
    INTERNAL_CONNECTION_BASE_URL="ws://127.0.0.1" \
    SESSION_CAPACITY=10 \
    REDIS_HOST="0.1" \
    REDIS_PORT=6379 \
    REDIS_DB=0

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Command using environment variables as CLI args
CMD ["python", "cli.py", "server", \
    "--public_listen_ip", "$PUBLIC_LISTEN_IP", \
    "--public_listen_port", "$PUBLIC_LISTEN_PORT", \
    "--internal_listen_ip", "$INTERNAL_LISTEN_IP", \
    "--internal_listen_port", "$INTERNAL_LISTEN_PORT", \
    "--internal_connection_base_url", "$INTERNAL_CONNECTION_BASE_URL", \
    "--session_capacity", "$SESSION_CAPACITY", \
    "--model_directory", "/app/data/model", \
    "--redis_host", "$REDIS_HOST", \
    "--redis_port", "$REDIS_PORT", \
    "--redis_db", "$REDIS_DB"]