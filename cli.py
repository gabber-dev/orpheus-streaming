import asyncio
import argparse
import sys

from server import WebSocketServer, Router, Health
from models.orpheus import OrpheusModel
from models.mock import MockModel


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
    # model = OrpheusModel(model_directory=args.model_directory)
    model = MockModel()
    health = Health(
        max_sessions=args.session_capacity,
        internal_connection_base_url=args.internal_connection_base_url,
        internal_listen_port=args.internal_listen_port,
    )
    router = Router(model=model, health=health)
    server = WebSocketServer(
        public_listen_ip=args.public_listen_ip,
        public_listen_port=args.public_listen_port,
        internal_listen_ip=args.internal_listen_ip,
        internal_listen_port=args.internal_listen_port,
        internal_connection_base_url=args.internal_connection_base_url,
        router=router,
    )
    server.run()
    # Add your server implementation here


def inference_command(args):
    """Handle inference command"""
    print("Running inference with:")
    print(f"Voice: {args.voice}")
    print(f"Text: {args.text}")
    # Add your inference implementation here


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

    # Inference command parser
    inference_parser = subparsers.add_parser("inference", help="Run inference")
    inference_parser.add_argument(
        "--voice", type=str, required=True, help="Voice to use for inference"
    )
    inference_parser.add_argument(
        "--text", type=str, required=True, help="Text to process"
    )

    # Gradio command parser
    gradio_parser = subparsers.add_parser("gradio", help="Start Gradio interface")
    gradio_parser.add_argument(
        "--port", type=int, default=7860, help="Port for Gradio interface"
    )

    # Parse arguments
    args = parser.parse_args()

    # Handle commands
    if args.command == "server":
        print("here")
        server_command(args)
    elif args.command == "inference":
        inference_command(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
