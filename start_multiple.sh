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
    --public_listen_port 7000 \
    --session_capacity 10 \
    --internal_listen_port 7001 \
    2>&1 | stdbuf -o0 sed 's/^/[server-1] /' | while IFS= read -r line; do 
    echo -e "\033[32m$line\033[0m"
done &

# Start Server 2 (ports 7500, 7501) with blue output
stdbuf -o0 python3 -u cli.py server \
    --public_listen_port 7500 \
    --internal_listen_port 7501 \
    2>&1 | stdbuf -o0 sed 's/^/[server-2] /' | while IFS= read -r line; do 
    echo -e "\033[34m$line\033[0m"
done &

# Wait for background processes to keep script running
wait