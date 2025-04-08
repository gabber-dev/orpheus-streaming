import asyncio
import logging
import time
from abc import ABC, abstractmethod

import aiohttp
from aiohttp import web

from models import BaseModel, BaseSessionHandle

from .config import Config
from .errors import (
    NoCapacityError,
    UnknownServerError,
)
from .health import Health
from proto_generated.tts_pb2 import (
    AUDIOTYPE_PCM16LE,
    AudioData,
    Error,
    Finished,
    ReceiveMessage,
    SendMessage,
)

from proto_generated.health_pb2 import GetServerHealthResponse


class WebsocketConnection:
    def __init__(
        self,
        *,
        ws: web.WebSocketResponse,
        config: Config,
        health: Health,
        model: BaseModel,
        internal: bool,
    ):
        self._config = config
        self._internal = internal
        self._health = health
        self._proxy = ProxyConnections(config=config)
        self._ws = ws
        self._sessions: dict[str, WebsocketSession] = {}
        self._session_run_tasks = set[asyncio.Task]()
        self._model = model
        self._closed = False
        self._receive_task = asyncio.create_task(self.receive_loop())

    async def receive_loop(self):
        try:
            async for msg in self._ws:
                logging.debug(f"Received message: {msg}")
                proto_msg = SendMessage.FromString(msg.data)
                if proto_msg.HasField("start_session"):
                    try:
                        await self._handle_start_session(original=proto_msg)
                    except NoCapacityError as e:
                        logging.error(f"No capacity: {e}")
                        await self._ws.send_bytes(
                            ReceiveMessage(
                                session=proto_msg.session,
                                error=Error(message="No capacity"),
                            ).SerializeToString()
                        )
                    continue

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
            logging.info("WebSocket closed")
        except UnknownServerError as e:
            logging.error(f"Unknown server: {e}")
            await self._ws.send_bytes(
                ReceiveMessage(
                    session=e.session,
                    error=Error(message=e.message),
                ).SerializeToString()
            )
            await self._ws.close()
        except Exception as e:
            logging.error(f"Error handling message: {e}")
            await self._ws.close()

        try:
            sessions = list(self._sessions.values())
            for session in sessions:
                logging.info(f"Closing session loop {session}")
                await session.close()

        except Exception as e:
            logging.error(f"Error closing sessions: {e}")

    async def _handle_start_session(self, *, original: SendMessage):
        logging.info(f"Creating session {original.session}")
        can_accept_local = await self._health.can_accept_session()
        # If we have local capacity, create a local session
        if can_accept_local:
            ws_sess = LocalWebsocketSession(
                config=self._config, ws=self._ws, start_msg=original, model=self._model
            )
            self._sessions[original.session] = ws_sess
            await self._health.add_session()
            t = asyncio.create_task(
                self._run_session(id=original.session, ws_sess=ws_sess)
            )
            self._session_run_tasks.add(t)
            t.add_done_callback(self._session_run_tasks.remove)
            return

        # If we don't have capacity even after forwarding, return an error
        if self._internal:
            logging.error("No capacity after internal forwarding")
            raise NoCapacityError(original.session)

        destination_candidates = await self._health.query_available_servers()
        if len(destination_candidates) == 0:
            logging.error("No destination servers available")
            raise NoCapacityError(original.session)

        ws_sess = RemoteWebsocketSession(
            config=self._config,
            ws=self._ws,
            start_msg=original,
            proxy=self._proxy,
            destination_candidates=destination_candidates,
        )
        self._sessions[original.session] = ws_sess
        t = asyncio.create_task(ws_sess.run())
        self._session_run_tasks.add(t)
        t.add_done_callback(lambda _: self._session_run_tasks.remove(t))

    async def _run_session(self, *, id: str, ws_sess: "WebsocketSession"):
        try:
            logging.info(f"Running session: {id}")
            await ws_sess.run()
            logging.info(f"Session complete: {id}")
        except Exception as e:
            logging.error(f"Error running session {id}", exc_info=e)
            await ws_sess.close()
        self._sessions.pop(id, None)
        await self._health.remove_session()

    async def wait_for_complete(self):
        await self._receive_task
        all_tasks = list(self._session_run_tasks)
        for task in all_tasks:
            await task

    async def close(self):
        logging.info("Closing WebSocket connection")
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

    @abstractmethod
    async def close(self):
        pass


class LocalWebsocketSession(WebsocketSession):
    def __init__(
        self,
        *,
        ws: web.WebSocketResponse,
        start_msg: SendMessage,
        model: BaseModel,
        config: Config,
    ):
        self._config = config
        self._ws = ws
        self._start_msg = start_msg
        self._model = model
        self._session_handle: BaseSessionHandle | None = None
        self._input_queue: asyncio.Queue[SendMessage | None] = asyncio.Queue()
        self._closed = False
        self._inactivity_task = asyncio.create_task(self.inactivity_loop())
        self._eos = False
        self._last_input = time.time()
        self._last_output = time.time()

    async def handle_message(self, msg: SendMessage):
        if self._closed:
            return
        if msg.HasField("eos"):
            self._eos = True
            await self._input_queue.put(None)
            return
        self._last_input = time.time()
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

            logging.info(f"Session {self._start_msg.session} EOS")
            self._session_handle.eos()

        send_task = asyncio.create_task(send_loop())
        async for msg in self._session_handle:
            self._last_output = time.time()
            audio_msg = ReceiveMessage(
                session=self._start_msg.session,
                audio_data=AudioData(
                    audio=msg,
                    sample_rate=24000,
                    channel_count=1,
                    audio_type=AUDIOTYPE_PCM16LE,
                ),
            )
            if not self._closed:
                await self._ws.send_bytes(audio_msg.SerializeToString())

        self._last_output = time.time()
        audio_msg = ReceiveMessage(
            session=self._start_msg.session,
            finished=Finished(),
        )
        if not self._closed:
            await self._ws.send_bytes(audio_msg.SerializeToString())
        await send_task
        self._closed = True

    async def inactivity_loop(self):
        while not self._closed:
            current_time = time.time()
            if (
                current_time - self._last_input > self._config.session_input_timeout
                and not self._eos
            ):
                self._closed = True
                if not self._ws._closed:
                    await self._ws.send_bytes(
                        ReceiveMessage(
                            session=self._start_msg.session,
                            error=Error(message="Inactivity timeout"),
                        ).SerializeToString()
                    )
                self._input_queue.put_nowait(None)
                logging.warning(f"Input timeout: {self._start_msg.session}")
                break

            if current_time - self._last_output > self._config.session_output_timeout:
                self._closed = True
                if not self._ws._closed:
                    await self._ws.send_bytes(
                        ReceiveMessage(
                            session=self._start_msg.session,
                            error=Error(message="Output timeout"),
                        ).SerializeToString()
                    )
                self._input_queue.put_nowait(None)
                logging.warning(f"Output timeout: {self._start_msg.session}")
                break

            await asyncio.sleep(0.25)

    async def close(self):
        logging.info(f"Closing session {self._start_msg.session}")
        self._closed = True
        self._input_queue.put_nowait(None)


class RemoteWebsocketSession(WebsocketSession):
    def __init__(
        self,
        *,
        config: Config,
        ws: web.WebSocketResponse,
        start_msg: SendMessage,
        proxy: "ProxyConnections",
        destination_candidates: list[GetServerHealthResponse],
    ):
        self._config = config
        self._ws = ws
        self._start_msg = start_msg
        self._proxy = proxy
        self._destination_candidates = destination_candidates
        self._proxy_handle: ProxyHandle | None = None
        self._proxy_handle_task: asyncio.Task | None = None
        self._input_queue: asyncio.Queue[SendMessage | None] = asyncio.Queue()

    async def handle_message(self, msg: SendMessage):
        await self._input_queue.put(msg)

    async def run(self):
        # This is the first message, so we need to find a viable destination server
        # if there are none, we return an error
        destination = ""
        for server in self._destination_candidates:
            try:
                self._proxy_handle = await self._proxy.start_proxy(
                    session_id=self._start_msg.session,
                    destination=server.server_health.url,
                )
                destination = server
            except Exception as e:
                logging.error(f"Failed to start proxy: {e}")
                continue

        if self._proxy_handle is None:
            logging.error("Proxy not available")
            raise Exception("Proxy not available")

        assert destination is not None
        logging.info(
            f"Forwarding session to {destination} for session {self._start_msg.session}"
        )

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

    async def close(self):
        logging.info(f"Closing session {self._start_msg.session}")
        self._input_queue.put_nowait(None)
        if self._proxy_handle is not None:
            self._proxy_handle._msg_queue.put_nowait(None)


class ProxyConnections:
    def __init__(self, *, config: Config):
        self._config = config
        self._connections: dict[str, aiohttp.client.ClientWebSocketResponse] = {}
        self._connection_locks: dict[str, asyncio.Lock] = {}
        self._closing = False
        self._http_session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._config.password}"}
        )
        self._connection_tasks = set[asyncio.Task]()
        self._proxy_handle_lookup = dict[str, ProxyHandle]()
        self._session_ws_lookup = dict[str, aiohttp.client.ClientWebSocketResponse]()

    async def start_proxy(self, *, session_id: str, destination: str):
        url = f"{destination}/ws"
        ws = await self._get_or_create_connection(url)
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

    async def _get_or_create_connection(self, url: str):
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
                ws = await self._create_connection(url)
                if ws is not None:
                    self._connections[url] = ws
                return ws
            except Exception as e:
                logging.error(f"Failed to create connection to {url}", exc_info=e)
                return None

    async def _create_connection(self, url: str):
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
        except Exception as e:
            print(f"Connection to {hostname} closed: {e}")
        finally:
            if hostname in self._connections and self._connections[hostname] == ws:
                del self._connections[hostname]

    async def close(self):
        logging.info("Closing all proxy connections")
        self._closing = True
        for hostname, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
            finally:
                if hostname in self._connections:
                    del self._connections[hostname]
        await self._http_session.close()


class ProxyHandle:
    def __init__(self, *, proxy: ProxyConnections):
        self._proxy = proxy
        self._msg_queue = asyncio.Queue[ReceiveMessage | None]()

    async def _receive_message(self, msg: ReceiveMessage):
        self._msg_queue.put_nowait(msg)

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
