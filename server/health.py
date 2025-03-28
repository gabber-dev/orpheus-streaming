import asyncio
from .proto_generated.health_pb2 import ServerHealth


class Health:
    def __init__(
        self,
        *,
        max_sessions: int = 1,
        internal_connection_base_url: str,
        internal_listen_port: int,
    ):
        self._internal_connection_base_url = internal_connection_base_url
        self._internal_listen_port = internal_listen_port
        self._closed = False
        self._report_status_task: asyncio.Task | None = None
        self._sessions = 0
        self._max_sessions = max_sessions

    async def start(self):
        self._report_status_task = asyncio.create_task(self._report_status_loop())

    async def query_available_servers(self) -> list[ServerHealth]:
        return []

    async def _report_status_loop(self):
        while not self._closed:
            await asyncio.sleep(1)

    async def add_session(self):
        self._sessions += 1

    async def remove_session(self):
        self._sessions -= 1

    async def can_accept_session(self) -> bool:
        if self._closed:
            return False
        return self._sessions < self._max_sessions
