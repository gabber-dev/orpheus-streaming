import asyncio
import logging

import aiohttp
from aiohttp import web
from abc import ABC, abstractmethod

from models import BaseModel, BaseSessionHandle

from .health import Health
from .proto_generated.health_pb2 import ServerHealth
from .proto_generated.tts_pb2 import (
    Error,
    SendMessage,
    ReceiveMessage,
    AudioData,
    AUDIOTYPE_PCM16LE,
)


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
        self._ws = ws
        self._sessions: dict[str, WebsocketSession] = {}
        self._session_run_tasks = set[asyncio.Task]()
        self._model = model
        self._closed = False
        self._receive_task = asyncio.create_task(self.receive_loop())

    async def receive_loop(self):
        async for msg in self._ws:
            try:
                proto_msg = SendMessage.FromString(msg.data)
                if proto_msg.HasField("start_session"):
                    await self._handle_start_session(original=proto_msg)
                    continue

                print("NEIL got messsaage", proto_msg)
                ws_sess = self._sessions.get(proto_msg.session)
                if ws_sess is None:
                    await self._ws.send_bytes(
                        ReceiveMessage(
                            session=proto_msg.session,
                            error=Error(message="Session not found"),
                        ).SerializeToString()
                    )
                    continue

                await ws_sess.handle_message(proto_msg)
            except Exception as e:
                logging.error(f"Error handling message: {e}")
                await self._ws.close()

    async def _handle_start_session(self, *, original: SendMessage):
        logging.info(f"Creating session {original.session}")
        can_accept_local = await self._health.can_accept_session()
        # If we have local capacity, create a local session
        if can_accept_local:
            ws_sess = LocalWebsocketSession(
                ws=self._ws, start_msg=original, model=self._model
            )
            self._sessions[original.session] = ws_sess
            t = asyncio.create_task(ws_sess.run())
            self._session_run_tasks.add(t)
            t.add_done_callback(lambda _: self._session_run_tasks.remove(t))
            return

        # If we don't have capacity even after forwarding, return an error
        if self._internal:
            logging.error("No capacity after internal forwarding")
            raise Exception("No capacity")

        destination_candidates = await self._health.query_available_servers()
        if len(destination_candidates) == 0:
            logging.error("No destination servers available")
            raise Exception("No destination servers available")

        ws_sess = RemoteWebsocketSession(
            ws=self._ws,
            start_msg=original,
            proxy=self._proxy,
            destination_candidates=destination_candidates,
        )
        self._sessions[original.session] = ws_sess
        t = asyncio.create_task(ws_sess.run())
        self._session_run_tasks.add(t)
        t.add_done_callback(lambda _: self._session_run_tasks.remove(t))
        await ws_sess.handle_message(original)

    async def wait_for_complete(self):
        await self._receive_task
        for task in self._session_run_tasks:
            await task

    async def close(self):
        self._closed = True
        await self._ws.close()
        # TODO implement session migration after timeout


class WebsocketSession(ABC):
    @abstractmethod
    async def handle_message(self, msg: SendMessage):
        pass

    @abstractmethod
    async def run(self):
        pass


class LocalWebsocketSession(WebsocketSession):
    def __init__(
        self, *, ws: web.WebSocketResponse, start_msg: SendMessage, model: BaseModel
    ):
        self._ws = ws
        self._start_msg = start_msg
        self._model = model
        self._session_handle: BaseSessionHandle | None = None
        self._input_queue: asyncio.Queue[SendMessage | None] = asyncio.Queue()

    async def handle_message(self, msg: SendMessage):
        if msg.HasField("eos"):
            await self._input_queue.put(None)
            return
        await self._input_queue.put(msg)

    async def run(self):
        self._session_handle = self._model.create_session(
            session_id=self._start_msg.session,
            voice=self._start_msg.start_session.voice,
        )

        async def send_loop():
            while True:
                msg = await self._input_queue.get()
                if msg is None:
                    break

                if self._session_handle is None:
                    logging.error("Session handle not found")
                    continue

                if msg.HasField("push_text"):
                    self._session_handle.push(text=msg.push_text.text)

            if self._session_handle is None:
                logging.error("Session handle not found")
                return

            self._session_handle.eos()

        send_task = asyncio.create_task(send_loop())
        async for msg in self._session_handle:
            print("NEIL got audio", self._start_msg.session)
            audio_msg = ReceiveMessage(
                session=self._start_msg.session,
                audio_data=AudioData(
                    audio=msg,
                    sample_rate=24000,
                    channel_count=1,
                    audio_type=AUDIOTYPE_PCM16LE,
                ),
            )
            await self._ws.send_bytes(audio_msg.SerializeToString())

        audio_msg = ReceiveMessage(
            session=self._start_msg.session,
            audio_data=AudioData(
                audio=b"",
                sample_rate=24000,
                channel_count=1,
                audio_type=AUDIOTYPE_PCM16LE,
            ),
        )
        await self._ws.send_bytes(audio_msg.SerializeToString())
        await send_task


class RemoteWebsocketSession(WebsocketSession):
    def __init__(
        self,
        *,
        ws: web.WebSocketResponse,
        start_msg: SendMessage,
        proxy: "ProxyConnections",
        destination_candidates: list[ServerHealth],
    ):
        self._ws = ws
        self._start_msg = start_msg
        self._proxy = proxy
        self._destination_candidates = destination_candidates
        self._destination_server: ServerHealth | None = None
        self._proxy_handle: ProxyHandle | None = None
        self._proxy_handle_task: asyncio.Task | None = None
        self._input_queue: asyncio.Queue[SendMessage | None] = asyncio.Queue()

    async def handle_message(self, msg: SendMessage):
        await self._input_queue.put(msg)

    async def run(self):
        # This is the first message, so we need to find a viable destination server
        # if there are none, we return an error
        if not self._destination_server:
            for server in self._destination_candidates:
                try:
                    self._proxy_handle = await self._proxy.start_proxy(
                        session_id=self._start_msg.session,
                        destination=self._destination_candidates[0],
                    )
                except Exception as e:
                    logging.error(f"Failed to start proxy: {e}")
                    continue

            raise Exception(
                f"No destination servers available, tried: {len(self._destination_candidates)} candidates"
            )

        if self._proxy_handle is None:
            logging.error("Proxy not available")
            raise Exception("Proxy not available")

        await self._proxy_handle.send_message(message=self._start_msg)

        async def receive_loop():
            if self._proxy_handle is None:
                await self._ws.send_bytes(
                    ReceiveMessage(
                        session=self._start_msg.session,
                        error=Error(message="Proxy not available"),
                    ).SerializeToString()
                )
                return

            async for msg in self._proxy_handle:
                await self._ws.send_bytes(msg.SerializeToString())

        receive_task = asyncio.create_task(receive_loop())
        while True:
            msg = await self._input_queue.get()
            if msg is None:
                break

            if self._proxy_handle is None:
                await self._ws.send_bytes(
                    ReceiveMessage(
                        session=self._start_msg.session,
                        error=Error(message="Proxy not available"),
                    ).SerializeToString()
                )
                return

            await self._proxy_handle.send_message(message=msg)

        await receive_task


class ProxyConnections:
    def __init__(self):
        self._connections: dict[str, aiohttp.client.ClientWebSocketResponse] = {}
        self._connection_locks: dict[str, asyncio.Lock] = {}
        self._closing = False
        self._http_session = aiohttp.ClientSession()
        self._connection_tasks = set[asyncio.Task]()
        self._proxy_handle_lookup = dict[str, ProxyHandle]()
        self._session_ws_lookup = dict[str, aiohttp.client.ClientWebSocketResponse]()

    async def start_proxy(self, *, session_id: str, destination: ServerHealth):
        url = self._url_from_server(destination)
        ws = await self._get_or_create_connection(destination)
        if ws is None:
            raise Exception(f"Failed to create connection to {url}")
        self._session_ws_lookup[session_id] = ws
        proxy_handle = ProxyHandle(proxy=self)
        self._proxy_handle_lookup[session_id] = proxy_handle
        return proxy_handle

    async def send_message(self, *, session_id: str, message: bytes):
        ws = self._session_ws_lookup.get(session_id)
        if ws is None:
            raise Exception("websocket not found")

        try:
            await ws.send_bytes(message)
        except Exception as e:
            raise Exception(f"Failed to send message: {e}")

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
        t = asyncio.create_task(self._run_connection(url, ws))
        self._connection_tasks.add(t)
        t.add_done_callback(lambda _: self._connection_tasks.remove(t))
        return ws

    async def _run_connection(
        self, hostname: str, ws: aiohttp.client.ClientWebSocketResponse
    ):
        try:
            async for msg in ws:
                try:
                    proto_msg = ReceiveMessage.FromString(msg.data)
                    handle = self._proxy_handle_lookup.get(proto_msg.session)
                    if handle is None:
                        logging.error(
                            f"Handle not found for session {proto_msg.session}"
                        )
                        continue
                    await handle._receive_message(proto_msg)
                except Exception as e:
                    logging.error(f"Error handling message: {e}")
                    await ws.close()
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


class ProxyHandle:
    def __init__(self, *, proxy: ProxyConnections):
        self._proxy = proxy
        self._msg_queue = asyncio.Queue[ReceiveMessage | None]()

    async def _receive_message(self, msg: ReceiveMessage):
        pass

    async def send_message(self, *, message: SendMessage):
        await self._proxy.send_message(
            session_id=message.session, message=message.SerializeToString()
        )

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self._msg_queue.get()
        if msg is None:
            raise StopAsyncIteration
        return msg

    async def handle(self, request: web.Request):
        destination = request.match_info["destination"]
        message = await request.read()
        if destination not in self._proxy._connections:
            return web.Response(status=404)

        ws = self._proxy._connections[destination]
        await ws.send_bytes(message)
        return web.Response(status=200)
