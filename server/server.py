import asyncio
from aiohttp import web
import logging
from .connection import WebsocketConnection
from .health import Health
from models import BaseModel
from .config import Config


class WebSocketServer:
    def __init__(
        self,
        *,
        config: Config,
        health: Health,
        model: BaseModel,
    ):
        """Initialize the WebSocket server with host and port."""
        self._config = config
        self._model = model
        self._health = health
        self.internal_app = web.Application()
        self.public_app = web.Application()
        self.setup_routes()
        self.logger = logging.getLogger(__name__)
        self._closed = False
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
            ws=ws,
            config=self._config,
            health=self._health,
            model=self._model,
            internal=True,
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
            ws=ws,
            config=self._config,
            health=self._health,
            model=self._model,
            internal=False,
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
            internal_runner,
            self._config.internal_listen_ip,
            self._config.internal_listen_port,
        )
        public_site = web.TCPSite(
            public_runner,
            self._config.public_listen_ip,
            self._config.public_listen_port,
        )
        await asyncio.gather(internal_site.start(), public_site.start())
        print("NEIL done")
        while not self._closed:
            await asyncio.sleep(1)

    async def stop_server(self):
        logging.info("Stopping server")
        self._closed = True
