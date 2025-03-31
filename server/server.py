import asyncio
from aiohttp import web
import logging
from .connection import WebsocketConnection
from .health import Health
from models import BaseModel
from .config import Config
from .admin_frontend import AdminFrontend


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
        self._closed = False
        self._connections: set[WebsocketConnection] = set()  # Track all connections
        self._internal_runner: web.AppRunner | None = None
        self._public_runner: web.AppRunner | None = None
        self._internal_site: web.TCPSite | None = None
        self._public_site: web.TCPSite | None = None
        self._admin_frontend: AdminFrontend | None = None

    def setup_routes(self):
        """Configure the server routes."""
        self.internal_app.add_routes([web.get("/ws", self.internal_websocket_handler)])
        self.public_app.add_routes([web.get("/ws", self.public_websocket_handler)])

    async def internal_websocket_handler(self, request: web.Request):
        """Handle internal WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logging.info(f"Internal client connected from {request.remote}")
        conn = WebsocketConnection(
            ws=ws,
            config=self._config,
            health=self._health,
            model=self._model,
            internal=True,
        )
        self._connections.add(conn)
        try:
            await conn.wait_for_complete()
        finally:
            self._connections.remove(conn)
        await ws.close()
        return ws

    async def public_websocket_handler(self, request: web.Request):
        """Handle public WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        logging.info(f"Public client connected from {request.remote}")
        conn = WebsocketConnection(
            ws=ws,
            config=self._config,
            health=self._health,
            model=self._model,
            internal=False,
        )
        self._connections.add(conn)
        try:
            await conn.wait_for_complete()
        finally:
            self._connections.remove(conn)
        await ws.close()
        return ws

    async def start_server(self):
        """Start the aiohttp server."""
        self._internal_runner = web.AppRunner(self.internal_app)
        self._public_runner = web.AppRunner(self.public_app)
        await self._internal_runner.setup()
        await self._public_runner.setup()
        self._internal_site = web.TCPSite(
            self._internal_runner,
            self._config.internal_listen_ip,
            self._config.internal_listen_port,
        )
        self._public_site = web.TCPSite(
            self._public_runner,
            self._config.public_listen_ip,
            self._config.public_listen_port,
        )
        await asyncio.gather(self._internal_site.start(), self._public_site.start())
        logging.info(
            f"Server started on internal {self._config.internal_listen_ip}:{self._config.internal_listen_port} "
            f"and public {self._config.public_listen_ip}:{self._config.public_listen_port}"
        )
        while not self._closed:
            await asyncio.sleep(1)

    async def stop_server(self):
        """Stop the aiohttp server and clean up resources with timeouts."""
        if self._closed:
            return
        self._closed = True
        logging.info("Stopping server")

        # Close all active WebSocket connections with a timeout
        if self._connections:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *[conn.close() for conn in self._connections],
                        return_exceptions=True,
                    ),
                    timeout=5.0,  # 5-second timeout for closing connections
                )
            except asyncio.TimeoutError:
                logging.warning("Timeout occurred while closing WebSocket connections")
            finally:
                self._connections.clear()

        logging.info("closed connections")

        # Stop sites with a timeout
        if self._internal_site and self._public_site:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self._internal_site.stop(),
                        self._public_site.stop(),
                        return_exceptions=True,
                    ),
                    timeout=5.0,  # 5-second timeout for stopping sites
                )
            except asyncio.TimeoutError:
                logging.warning("Timeout occurred while stopping sites")

        # Cleanup runners with a timeout
        if self._internal_runner and self._public_runner:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self._internal_runner.shutdown(),
                        self._public_runner.shutdown(),
                        return_exceptions=True,
                    ),
                    timeout=5.0,  # 5-second timeout for runner cleanup
                )
            except asyncio.TimeoutError:
                logging.warning("Timeout occurred while cleaning up runners")

        logging.info("Server stopped")
