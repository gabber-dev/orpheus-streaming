import asyncio
from datetime import datetime
import logging
import time

from aiohttp import web
from google.protobuf.json_format import Parse, MessageToDict

from proto_generated.health_pb2 import GetServerHealthResponse, ServerHealth

from .config import Config


class Controller:
    def __init__(self, *, config: Config):
        self._config = config
        self._app = web.Application()
        self.setup_routes()
        self._closed = False
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._service_health_repository = ServiceHealthRepository()

    async def start(self):
        logging.info(
            f"Starting controller on {self._config.listen_ip}:{self._config.listen_port}"
        )
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner,
            self._config.listen_ip,
            self._config.listen_port,
        )

        await self._site.start()
        logging.info(
            f"Controller started on {self._config.listen_ip}:{self._config.listen_port}"
        )
        while not self._closed:
            await asyncio.sleep(1)

        logging.info("Controller stopped")

    def setup_routes(self):
        """Configure the server routes."""
        self._app.add_routes([web.get("/ws", self._ws_handler)])
        self._app.add_routes([web.get("/admin", self._get_admin)])

        self._app.add_routes(
            [web.get("/health/available_servers", self._get_available_servers)]
        )
        self._app.add_routes([web.get("/health/all_servers", self._get_all_servers)])
        self._app.add_routes([web.post("/health/report", self._post_health_report)])

    async def _ws_handler(self, request: web.Request):
        servers = await self._service_health_repository.get_available_servers()
        if len(servers):
            return web.Response(status=503)

        # redirect to first available server
        server = servers[0]
        return web.HTTPFound(f"ws://{server.server_health.url}")

    async def _get_admin(self, request: web.Request):
        # Query all servers from the health object
        servers = await self._service_health_repository.get_all_servers()

        # Generate a simple HTML page with server list
        html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Server Health Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        tr:nth-child(even) { background-color: #f9f9f9; }
    </style>
</head>
<body>
    <h1>Server Health Dashboard</h1>
    <table>
        <tr>
            <th>Url</th>
            <th>Capacity</th>
            <th>Last Check</th>
        </tr>
            """

        # Add rows for each server
        for s in servers:
            last_updated_dt = datetime.fromtimestamp(s.last_updated)
            formatted_time = last_updated_dt.strftime("%Y-%m-%d %H:%M:%S")
            html += f"""
<tr>
    <td>{s.server_health.url}</td>
    <td>{s.server_health.max_sessions - s.server_health.sessions}</td>
    <td>{formatted_time}</td>
</tr>
                """

        html += """
    </table>
</body>
</html>
            """

        return web.Response(text=html, content_type="text/html")

    async def _post_health_report(self, request: web.Request):
        body = await request.text()
        server_health = Parse(body, ServerHealth())
        await self._service_health_repository.update_server_health(info=server_health)
        return web.Response(text="OK")

    async def _get_available_servers(self, request: web.Request):
        servers = await self._service_health_repository.get_available_servers()
        return web.json_response(
            [MessageToDict(s, float_precision=32) for s in servers],
            content_type="application/json",
        )

    async def _get_all_servers(self, request: web.Request):
        servers = await self._service_health_repository.get_all_servers()
        return web.json_response(
            [MessageToDict(s, float_precision=32) for s in servers],
            content_type="application/json",
        )

    async def close(self):
        self._closed = True
        if self._runner:
            await self._runner.cleanup()
        await self._service_health_repository.close()


# Naive implementation but should work fine considering each server is a multiple-thousand-dollar a month machine
# Issues with the algorithms here mean we're winning and can hire someone to fix it.
class ServiceHealthRepository:
    def __init__(self, timeout_seconds: int = 30, update_interval: float = 5.0):
        self._servers: dict[str, ServerHealth] = {}
        self._server_updated_time: dict[str, float] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._closed = False

    async def start(self):
        """Start the controller's cleanup loop."""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_servers_loop())

    async def _cleanup_expired_servers_loop(self):
        """Periodically clean up expired servers."""
        while not self._closed:
            now = time.time()
            servers_to_remove: list[str] = []
            for s in self._servers:
                if now - self._server_updated_time[s] > 120:
                    servers_to_remove.append(s)

            for s in servers_to_remove:
                del self._servers[s]
                del self._server_updated_time[s]

            await asyncio.sleep(5)

    async def update_server_health(self, info: ServerHealth):
        """Update the status of a server."""
        logging.info(
            f"Updating server health: {info.url} {info.sessions}/{info.max_sessions}"
        )
        self._servers[info.url] = info
        self._server_updated_time[info.url] = time.time()
        print("NEIL WAS HERE", self._server_updated_time)

    async def get_available_servers(self) -> list[GetServerHealthResponse]:
        """Get a list of available servers (capacity < max_sessions)."""
        servers = self._servers.values()
        sorted_by_capacity = sorted(
            servers, key=lambda x: (x.max_sessions - x.sessions)
        )

        return [
            GetServerHealthResponse(
                server_health=s, last_updated=self._server_updated_time.get(s.url, 0.0)
            )
            for s in sorted_by_capacity
            if s.sessions < s.max_sessions
        ]

    async def get_all_servers(self) -> list[GetServerHealthResponse]:
        servers = self._servers.values()
        sorted_by_capacity = sorted(
            servers, key=lambda x: (x.max_sessions - x.sessions)
        )

        return [
            GetServerHealthResponse(
                server_health=s, last_updated=self._server_updated_time.get(s.url, 0.0)
            )
            for s in sorted_by_capacity
        ]

    async def close(self):
        """Shutdown the controller."""
        self._closed = True
        if self._cleanup_task:
            await self._cleanup_task
