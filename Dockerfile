# Builder and runtime stage (single stage for simplicity with CUDA)
FROM gabberneil/torch:latest

ARG MODEL_SOURCE_DIR

# Copy the model and application code
COPY ${MODEL_SOURCE_DIR}/* /app/data/model/
COPY controller ./controller/
COPY models ./models/
COPY sentence_tokenizer ./sentence_tokenizer/
COPY proto_generated ./proto_generated/
COPY server ./server/
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

# Ensure the model directory exists
RUN mkdir -p /app/data/model

RUN python3 -m pip install nltk
RUN python3 -m nltk.downloader punkt
RUN python3 -m nltk.downloader punkt_tab

# Run the application
CMD ["python2", "cli.py", "server", \
    "--public_listen_ip", "${PUBLIC_LISTEN_IP}", \
    "--public_listen_port", "${PUBLIC_LISTEN_PORT}", \
    "--internal_listen_ip", "${INTERNAL_LISTEN_IP}", \
    "--internal_listen_port", "${INTERNAL_LISTEN_PORT}", \
    "--internal_connection_base_url", "${INTERNAL_CONNECTION_BASE_URL}", \
    "--session_capacity", "${SESSION_CAPACITY}", \
    "--model_directory", "/app/data/model"]