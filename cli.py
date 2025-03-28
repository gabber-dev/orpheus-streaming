import asyncio
import argparse
import sys

from server import WebSocketServer, RedisHealth
from models import BaseModel, orpheus, mock


def server_command(args):
    """Handle server command"""
    print("Starting server with the following configuration:")
    print(f"Public Listen IP: {args.public_listen_ip}")
    print(f"Public Listen Port: {args.public_listen_port}")
    print(f"Internal Listen IP: {args.internal_listen_ip}")
    print(f"Internal Listen Port: {args.internal_listen_port}")
    print(f"Session Capacity: {args.session_capacity}")
    print(f"Model Directory: {args.model_directory}")
    print(f"Internal connection base url: {args.internal_connection_base_url}")
    print(f"Mock: {args.mock}")
    print(f"Redis Host: {args.redis_host}")
    print(f"Redis Port: {args.redis_port}")
    print(f"Redis DB: {args.redis_db}")

    model: BaseModel
    if args.mock:
        model = mock.MockModel()
    else:
        model = orpheus.OrpheusModel(model_directory=args.model_directory)

    health = RedisHealth(
        max_sessions=args.session_capacity,
        internal_connection_base_url=args.internal_connection_base_url,
        internal_listen_port=args.internal_listen_port,
        redis_db=args.redis_db,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
    )
    server = WebSocketServer(
        public_listen_ip=args.public_listen_ip,
        public_listen_port=args.public_listen_port,
        internal_listen_ip=args.internal_listen_ip,
        internal_listen_port=args.internal_listen_port,
        internal_connection_base_url=args.internal_connection_base_url,
        health=health,
        model=model,
    )
    server.run()
    # Add your server implementation here


def main():
    # Create the top-level parser
    parser = argparse.ArgumentParser(description="CLI Tool with multiple commands")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Server command parser
    server_parser = subparsers.add_parser("server", help="Start the server")
    server_parser.add_argument(
        "--public_listen_ip",
        type=str,
        default="0.0.0.0",
        help="Public ip to listen on",
    )
    server_parser.add_argument(
        "--public_listen_port", type=int, default=8080, help="Public port to listen on"
    )
    server_parser.add_argument(
        "--internal_listen_ip",
        type=str,
        default="0.0.0.0",
        help="Internal ip to listen on",
    )
    server_parser.add_argument(
        "--internal_listen_port",
        type=int,
        default=8081,
        help="Internal port to listen on",
    )
    server_parser.add_argument(
        "--internal_connection_base_url",
        type=str,
        default="ws://127.0.0.1",
        help="Host that will be registered with internal pool for load proxying from other servers",
    )
    server_parser.add_argument(
        "--session_capacity", type=int, default=10, help="Maximum number of sessions"
    )
    server_parser.add_argument(
        "--model_directory",
        type=str,
        default="./data/finetune-fp16",
        help="Directory containing models",
    )
    server_parser.add_argument(
        "--mock",
        action="store_true",
        help="Use a mock model instead of the real model",
    )
    server_parser.add_argument(
        "--redis_host",
        type=str,
        default=0.1,
        help="Delay for redis load balancing",
    )
    server_parser.add_argument(
        "--redis_port",
        type=int,
        default=6379,
        help="Port for redis load balancing",
    )
    server_parser.add_argument(
        "--redis_db",
        type=int,
        default=0,
        help="Database for redis load balancing",
    )

    # Parse arguments
    args = parser.parse_args()

    # Handle commands
    if args.command == "server":
        print("here")
        server_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
