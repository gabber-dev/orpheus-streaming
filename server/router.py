import asyncio
import logging

import aiohttp
from aiohttp import WSMessage, web

from models import BaseModel, BaseSessionHandle

from .health import Health
from .proto_generated.health_pb2 import ServerHealth
from .proto_generated.tts_pb2 import (
    Eos,
    Error,
    PushText,
    SendMessage,
    StartSession,
)


class Router:
    def __init__(self, *, model: BaseModel, health: Health):
        self._health = health
        self._model = model

    async def add_connection(self, ws: web.WebSocketResponse, internal: bool):
        conn = WebsocketConnection(
            ws=ws, health=self._health, model=self._model, internal=internal
        )
        return conn


class WebsocketConnection:
    def __init__(
        self,
        *,
        ws: web.WebSocketResponse,
        health: Health,
        model: BaseModel,
        internal: bool,
    ):
        self._internal = internal
        self._health = health
        self._proxy = ProxyConnections()
        self._output_queue: asyncio.Queue = asyncio.Queue()
        self._ws = ws
        self._session_local: dict[str, BaseSessionHandle] = {}
        self._session_remote: dict[str, RemoteForwarder] = {}
        self._receive_task = asyncio.create_task(self.receive_task())
        self._session_tasks = set[asyncio.Task]()
        self._model = model
        self._closed = False

    async def receive_task(self):
        async for msg in self._ws:
            try:
                proto_msg = SendMessage.FromString(msg.data)
                if proto_msg.HasField("start_session"):
                    await self._handle_start_session(msg, proto_msg.start_session)
                elif proto_msg.HasField("push_text"):
                    await self._handle_text(msg, proto_msg.push_text)
                elif proto_msg.HasField("eos"):
                    await self._handle_eos(msg, proto_msg.eos)
                elif proto_msg.HasField("audio_data"):
                    pass
            except Exception as e:
                logging.error(f"Error handling message: {e}")
                await self._ws.close()

    async def _handle_start_session(self, original: WSMessage, msg: StartSession):
        logging.info(f"Creating session {msg.id}")
        can_accept_local = await self._health.can_accept_session()
        # If we have local capacity, create a local session
        if can_accept_local:
            session_handle = self._model.create_session(msg.id)
            self._session_local[msg.id] = session_handle
            task = asyncio.create_task(self._run_session(session_handle))
            self._session_tasks.add(task)
            task.add_done_callback(lambda _: self._session_tasks.remove(task))
            return

        # If we don't have capacity even after forwarding, return an error
        if self._internal:
            logging.error("No capacity after internal forwarding")
            raise Exception("No capacity")

        destination_candidates = await self._health.query_available_servers()
        if len(destination_candidates) == 0:
            logging.error("No destination servers available")
            raise Exception("No destination servers available")

        forwarder = RemoteForwarder(
            source_ws=self._ws,
            proxy=self._proxy,
            destination_candidates=destination_candidates,
        )
        self._session_remote[msg.id] = forwarder
        await forwarder.forward(original)

    async def _handle_text(self, original: WSMessage, msg: PushText):
        id = msg.session
        if id in self._session_local:
            self._session_local[id].push(msg.text)
        elif id in self._session_remote:
            await self._session_remote[id].forward(original)
        else:
            await self._ws.send_bytes(
                Error(session=id, message="Session not found").SerializeToString()
            )

    async def _handle_eos(self, original: WSMessage, msg: Eos):
        id = msg.session
        if id in self._session_local:
            self._session_local[id].eos()
        elif id in self._session_remote:
            await self._session_remote[id].forward(original)
        else:
            await self._ws.send_bytes(
                Error(session=id, message="Session not found").SerializeToString()
            )

    async def _run_session(self, handle: BaseSessionHandle):
        async for data in handle:
            logging.info(f"Sending data: {data}")
            pass

    async def wait_for_complete(self):
        for task in self._session_tasks:
            await task

        await self._receive_task

    async def close(self):
        self._closed = True
        await self._ws.close()
        # TODO implement session migration after timeout


class RemoteForwarder:
    def __init__(
        self,
        *,
        source_ws: web.WebSocketResponse,
        proxy: "ProxyConnections",
        destination_candidates: list[ServerHealth],
    ):
        self._proxy = proxy
        self._destination_candidates = destination_candidates
        self._destination_server: ServerHealth | None = None

    async def forward(self, msg: WSMessage):
        # This is the first message, so we need to find a viable destination server
        # if there are none, we return an error
        if not self._destination_server:
            for server in self._destination_candidates:
                if await self._proxy.send_message(server, msg.data):
                    self._destination_server = server
                    return

            raise Exception(
                f"No destination servers available, tried: {len(self._destination_candidates)} candidates"
            )

        await self._proxy.send_message(self._destination_server, msg.data)


class ProxyConnections:
    def __init__(self):
        self._connections: dict[str, aiohttp.client.ClientWebSocketResponse] = {}
        self._connection_locks: dict[str, asyncio.Lock] = {}
        self._closing = False
        self._http_session = aiohttp.ClientSession()

    async def send_message(self, destination: ServerHealth, message: bytes) -> bool:
        url = self._url_from_server(destination)

        # Get or create connection
        ws = await self._get_or_create_connection(destination)
        if ws is None or ws.closed:
            return False

        try:
            await ws.send_bytes(message)
            return True
        except Exception as e:
            print(f"Error sending message to {url}: {e}")
            # Clean up failed connection
            if url in self._connections:
                del self._connections[url]
            return False

    async def _get_or_create_connection(self, destination: ServerHealth):
        url = self._url_from_server(destination)

        if url in self._connections:
            ws = self._connections[url]
            if not ws.closed:
                return ws

        # Initialize lock for this hostname if it doesn't exist
        if url not in self._connection_locks:
            self._connection_locks[url] = asyncio.Lock()

        # Use lock to prevent multiple simultaneous connection attempts
        async with self._connection_locks[url]:
            if url in self._connections:
                ws = self._connections[url]
                if not ws.closed:
                    return ws

            if self._closing:
                return None

            try:
                ws = await self._create_connection(destination)
                if ws is not None:
                    self._connections[url] = ws
                return ws
            except Exception as e:
                print(f"Failed to create connection to {url}: {e}")
                return None

    async def _create_connection(self, destination: ServerHealth):
        url = self._url_from_server(destination)
        timeout = aiohttp.ClientWSTimeout(ws_close=10.0, ws_receive=10.0)

        ws = await self._http_session.ws_connect(
            url,
            timeout=timeout,
            autoclose=False,
            autoping=True,
        )
        return ws

    async def _monitor_connection(self, hostname: str, ws: web.WebSocketResponse):
        try:
            async for msg in ws:
                # Handle any incoming messages if needed
                pass
        except Exception as e:
            print(f"Connection to {hostname} closed: {e}")
        finally:
            if hostname in self._connections and self._connections[hostname] == ws:
                del self._connections[hostname]

    async def close(self):
        self._closing = True
        for hostname, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
            finally:
                if hostname in self._connections:
                    del self._connections[hostname]

    def _url_from_server(self, server: ServerHealth) -> str:
        return f"{server.internal_connection_url}:{server.internal_connection_port}"
