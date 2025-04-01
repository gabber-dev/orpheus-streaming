import logging
from .config import Config
from .health import Health
from aiohttp import web


class AdminFrontend:
    def __init__(self, *, config: Config, health: Health):
        """Initialize the AdminFrontend with config and health."""
        self._config = config
        self._health = health
        self.app = web.Application()
        self.setup_routes()
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._closed = False

    async def start(self):
        """Start the admin frontend server."""
        if self._closed:
            raise RuntimeError("Cannot start a closed server")
        if self._runner is not None:
            raise RuntimeError("Server is already running")
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner, self._config.admin_listen_ip, self._config.admin_listen_port
        )
        await self._site.start()

    def setup_routes(self):
        """Configure the admin frontend routes."""
        self.app.add_routes([web.get("/", self.admin_page_handler)])

    async def admin_page_handler(self, request: web.Request):
        """Handle requests to the admin page, displaying server health."""
        try:
            # Query all servers from the health object
            servers = await self._health.query_all_servers()

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
                        <th>Server ID</th>
                        <th>Capacity</th>
                        <th>Last Check</th>
                    </tr>
            """

            # Add rows for each server
            for s in servers:
                status = s.capacity
                last_check = s.last_update
                html += f"""
                    <tr>
                        <td>{s.server_id}</td>
                        <td>{status * -1}</td>
                        <td>{last_check}</td>
                    </tr>
                """

            html += """
                </table>
            </body>
            </html>
            """

            return web.Response(text=html, content_type="text/html")

        except Exception as e:
            logging.error(f"Error generating admin page: {e}")
            return web.Response(
                text=f"<h1>Error</h1><p>Could not load server data: {str(e)}</p>",
                content_type="text/html",
                status=500,
            )

    async def close(self):
        """Close the admin frontend server."""
        if self._closed:
            return
        self._closed = True
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()
        self._runner = None
        self._site = None
        logging.info("Admin frontend server closed")
