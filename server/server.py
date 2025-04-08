import asyncio
import logging
from typing import Awaitable, Callable

from aiohttp import web

from models import BaseModel

from .config import Config
from .connection import WebsocketConnection
from .health import Health


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
        self.public_app = web.Application()
        self.setup_routes()
        self._closed = False
        self._connections: set[WebsocketConnection] = set()  # Track all connections
        self._public_runner: web.AppRunner | None = None
        self._public_site: web.TCPSite | None = None

    async def _validate_password(
        self,
        request: web.Request,
    ):
        if self._config.password is not None:
            auth_header = request.headers.get("Authorization")
            if auth_header is None:
                raise web.HTTPUnauthorized()
            if not auth_header.startswith("Bearer "):
                raise web.HTTPUnauthorized()
            token = auth_header.split(" ")[1]
            if token != self._config.password:
                raise web.HTTPUnauthorized()

    def setup_routes(self):
        """Configure the server routes."""
        self.public_app.add_routes([web.get("/ws", self.public_websocket_handler)])

    async def public_websocket_handler(self, request: web.Request):
        await self._validate_password(request)
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
            if conn in self._connections:
                logging.info(f"Public client disconnected from {request.remote}")
                self._connections.remove(conn)
        await ws.close()
        return ws

    async def start(self):
        """Start the aiohttp server."""
        self._public_runner = web.AppRunner(self.public_app)
        await self._public_runner.setup()
        self._public_site = web.TCPSite(
            self._public_runner,
            self._config.listen_ip,
            self._config.listen_port,
        )

        await self._public_site.start()
        logging.info(
            f"Server started on {self._config.listen_ip}:{self._config.listen_port}"
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
        if self._public_site:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        self._public_site.stop(),
                        return_exceptions=True,
                    ),
                    timeout=5.0,  # 5-second timeout for stopping sites
                )
            except asyncio.TimeoutError:
                logging.warning("Timeout occurred while stopping sites")

        logging.info("Server stopped")
