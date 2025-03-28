import asyncio
from aiohttp import web
import logging
from .connection import WebsocketConnection
from .health import Health
from models import BaseModel


class WebSocketServer:
    def __init__(
        self,
        *,
        internal_listen_ip: str,
        internal_listen_port: int,
        internal_connection_base_url: str,
        public_listen_ip: str,
        public_listen_port: int,
        health: Health,
        model: BaseModel,
    ):
        """Initialize the WebSocket server with host and port."""
        self.internal_listening_ip = internal_listen_ip
        self.internal_listening_port = internal_listen_port
        self.internal_connection_base_url = internal_connection_base_url
        self.public_listening_ip = public_listen_ip
        self.public_listening_port = public_listen_port
        self._model = model
        self._health = health
        self.internal_app = web.Application()
        self.public_app = web.Application()
        self.setup_routes()
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

    def setup_routes(self):
        """Configure the server routes."""
        self.internal_app.add_routes([web.get("/ws", self.internal_websocket_handler)])
        self.public_app.add_routes([web.get("/ws", self.public_websocket_handler)])

    async def internal_websocket_handler(self, request: web.Request):
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.logger.info(f"Client connected from {request.remote}")
        conn = WebsocketConnection(
            ws=ws, health=self._health, model=self._model, internal=True
        )
        await conn.wait_for_complete()
        print("NEIL conn complete")
        return ws

    async def public_websocket_handler(self, request: web.Request):
        """Handle WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.logger.info(f"Client connected from {request.remote}")
        conn = WebsocketConnection(
            ws=ws, health=self._health, model=self._model, internal=False
        )
        await conn.wait_for_complete()
        print("NEIL conn complete")
        return ws

    async def start_server(self):
        """Start the aiohttp server."""
        internal_runner = web.AppRunner(self.internal_app)
        public_runner = web.AppRunner(self.public_app)
        await internal_runner.setup()
        await public_runner.setup()
        internal_site = web.TCPSite(
            internal_runner, self.internal_listening_ip, self.internal_listening_port
        )
        public_site = web.TCPSite(
            public_runner, self.public_listening_ip, self.public_listening_port
        )
        await asyncio.gather(internal_site.start(), public_site.start())

    def run(self):
        """Run the WebSocket server."""
        loop = asyncio.get_event_loop()
        runner: web.AppRunner | None = None
        try:
            runner = loop.run_until_complete(self.start_server())
            # Keep the server running
            loop.run_forever()

        except KeyboardInterrupt:
            if runner:
                self.logger.info("Server shutting down...")
                loop.run_until_complete(runner.cleanup())
        except Exception as e:
            self.logger.error(f"Server error: {e}")
        finally:
            loop.close()
