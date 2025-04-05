import asyncio
import argparse
import logging


from server import WebSocketServer, Config, ControllerHealth, LocalHealth, Health
from models import BaseModel, orpheus, mock
from controller import Controller, Config as ControllerConfig

# Configure logging globally at INFO level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


async def server_command(args):
    """Handle server command"""
    logging.info("Starting server with the following configuration:")
    logging.info(f"Public Listen IP: {args.listen_ip}")
    logging.info(f"Public Listen Port: {args.listen_port}")
    logging.info(f"Advertise URL: {args.advertise_url}")
    logging.info(f"Controller URL: {args.controller_url}")
    logging.info(f"Max Sessions: {args.max_sessions}")
    logging.info(f"Model Directory: {args.model_directory}")
    logging.info(f"Mock: {args.mock}")
    logging.info(f"Session Input Timeout: {args.session_input_timeout}")
    logging.info(f"Session Output Timeout: {args.session_output_timeout}")

    model: BaseModel
    if args.mock:
        model = mock.MockModel()
    else:
        model = orpheus.OrpheusModel(model_directory=args.model_directory)

    controller_url: str | None = None
    if args.controller_url != "":
        controller_url = args.controller_url

    password: str | None = None
    if args.password != "":
        password = args.password

    config = Config(
        listen_ip=args.listen_ip,
        listen_port=args.listen_port,
        advertise_url=args.advertise_url,
        max_sessions=args.max_sessions,
        session_input_timeout=args.session_input_timeout,
        session_output_timeout=args.session_output_timeout,
        controller_url=controller_url,
        password=password,
    )

    health: Health
    if controller_url is not None:
        health = ControllerHealth(config=config)
    else:
        health = LocalHealth(config=config)
    health_task = asyncio.create_task(health.start())
    server = WebSocketServer(config=config, health=health, model=model)

    try:
        await server.start()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down server")
        await server.stop_server()
    except Exception as e:
        logging.error(f"An error occurred: {e}")

    if health_task is not None:
        await health_task


async def controller_command(args):
    """Handle controller command"""
    logging.info(f"Listen IP: {args.listen_ip}")
    logging.info(f"Listen Port: {args.listen_port}")
    password: str | None = None
    if args.password != "":
        password = args.password
    cfg = ControllerConfig(
        listen_ip=args.listen_ip,
        listen_port=args.listen_port,
        password=password,
    )
    controller = Controller(config=cfg)
    try:
        await controller.start()
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down controller")
        await controller.close()
    except Exception as e:
        logging.error(f"An error occurred: {e}")


def main():
    # Create the top-level parser
    parser = argparse.ArgumentParser(description="CLI Tool with multiple commands")
    subparsers = parser.add_subparsers(
        dest="command", help="Available commands", required=True
    )

    # Server command parser
    server_parser = subparsers.add_parser("server", help="Start the server")
    server_parser.add_argument(
        "--listen-ip",
        type=str,
        default="0.0.0.0",
        help="Public ip to listen on",
    )
    server_parser.add_argument(
        "--listen-port",
        type=int,
        default=8080,
        help="Public port to listen on",
    )
    server_parser.add_argument(
        "--advertise-url",
        type=str,
        help="Host to advertise to the cluster",
        default="",
    )
    server_parser.add_argument(
        "--controller-url",
        type=str,
        help="URL of the controller",
        default="",
    )
    server_parser.add_argument(
        "--max-sessions",
        type=int,
        default=10,
        help="Maximum number of sessions",
    )
    server_parser.add_argument(
        "--model-directory",
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
        "--session-input-timeout", type=float, default=2.0, help="Session input timeout"
    )
    server_parser.add_argument(
        "--session-output-timeout",
        type=float,
        default=3.0,
        help="Session output timeout",
    )
    server_parser.add_argument(
        "--password",
        type=str,
        default="",
        help="Bearer token password for authentication",
    )

    # Controller command parser
    controller_parser = subparsers.add_parser("controller", help="Start the controller")
    controller_parser.add_argument(
        "--listen-ip",
        type=str,
        default="0.0.0.0",
        help="Public ip to listen on",
    )
    controller_parser.add_argument(
        "--listen-port",
        type=int,
        default=8080,
        help="Public port to listen on",
    )
    controller_parser.add_argument(
        "--password",
        type=str,
        default="",
        help="Bearer token password for authentication",
    )

    # Parse arguments
    args = parser.parse_args()

    # Dispatch to appropriate command
    if args.command == "server":
        asyncio.run(server_command(args))
    elif args.command == "controller":
        asyncio.run(controller_command(args))


if __name__ == "__main__":
    main()
