#!/bin/bash

# Function to kill all background processes
cleanup() {
    echo "Shutting down both servers..."
    # Kill all background jobs
    kill $(jobs -p) 2>/dev/null
    exit 0
}

# Trap Ctrl+C (SIGINT) and call cleanup
trap cleanup SIGINT

# Start Server 1 (ports 7000, 7001) with green output
stdbuf -o0 python3 -u cli.py server \
    --listen-port 7000 \
    --max-sessions 0 \
    --advertise-url ws://localhost:7000 \
    --controller-url http://localhost:9000 \
    --session-input-timeout 20 \
    --session-output-timeout 20 \
    --mock \
    2>&1 | stdbuf -o0 sed 's/^/[server-1] /' | while IFS= read -r line; do 
    echo -e "\033[32m$line\033[0m"
done &

# Start Server 2 (ports 7500, 7501) with blue output
stdbuf -o0 python3 -u cli.py server \
    --listen-port 7500 \
    --max-sessions 1 \
    --advertise-url ws://localhost:7500 \
    --session-input-timeout 20 \
    --session-output-timeout 20 \
    --controller-url http://localhost:9000 \
    --mock \
    2>&1 | stdbuf -o0 sed 's/^/[server-2] /' | while IFS= read -r line; do 
    echo -e "\033[34m$line\033[0m"
done &

stdbuf -o0 python3 -u cli.py controller \
    --listen-port 9000 \
    2>&1 | stdbuf -o0 sed 's/^/[controller] /' | while IFS= read -r line; do 
    echo -e "\033[35m$line\033[0m"
done &

# Wait for background processes to keep script running
wait