# Build stage: Install dependencies and prepare the environment
FROM python:3.9-slim AS builder
WORKDIR /app

# Copy requirements file first (for caching)
COPY requirements.txt .

# Install build dependencies and Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc \
    && rm -rf /var/lib/apt/lists/*

# Final stage: Create the runtime image
FROM python:3.9-slim
WORKDIR /app

# Define build argument for model source directory
ARG MODEL_SOURCE_DIR

# Copy only the necessary Python packages from the builder stage
COPY --from=builder /usr/local/lib/python3.9/site-packages/ /usr/local/lib/python3.9/site-packages/

# Copy the model and application code
COPY ${MODEL_SOURCE_DIR}/* /app/data/model/
COPY controller . 
COPY models . 
COPY proto_generated . 
COPY server . 
COPY cli.py .

# Set environment variables
ENV PUBLIC_LISTEN_IP="0.0.0.0" \
    PUBLIC_LISTEN_PORT=8080 \
    INTERNAL_LISTEN_IP="0.0.0.0" \
    INTERNAL_LISTEN_PORT=8081 \
    INTERNAL_CONNECTION_BASE_URL="ws://127.0.0.1" \
    SESSION_CAPACITY=10 \
    REDIS_HOST="0.1" \
    REDIS_PORT=6379 \
    REDIS_DB=0

# Ensure the model directory exists (in case COPY doesn't create it)
RUN mkdir -p /app/data/model

# Run the application
CMD ["python", "cli.py", "server", \
    "--public_listen_ip", "$PUBLIC_LISTEN_IP", \
    "--public_listen_port", "$PUBLIC_LISTEN_PORT", \
    "--internal_listen_ip", "$INTERNAL_LISTEN_IP", \
    "--internal_listen_port", "$INTERNAL_LISTEN_PORT", \
    "--internal_connection_base_url", "$INTERNAL_CONNECTION_BASE_URL", \
    "--session_capacity", "$SESSION_CAPACITY", \
    "--model_directory", "/app/data/model"]