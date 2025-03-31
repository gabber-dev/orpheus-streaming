import asyncio
import logging
import subprocess

import aioredis
import aioredis.client
import pytest
from aiohttp import ClientSession, WSMsgType

from models import mock
from server import Config, RedisConfig, RedisHealth, WebSocketServer
from server.proto_generated.tts_pb2 import (
    Eos,
    PushText,
    ReceiveMessage,
    SendMessage,
    StartSession,
)


@pytest.fixture
def redis_server(request):
    """Ensure Redis server is running, start if necessary with a specific db."""
    # Get the db from the redis_db marker
    marker = request.node.get_closest_marker("redis_db")
    db = marker.args[0] if marker else 2  # Default to 2 if marker is missing
    client = aioredis.from_url(f"redis://localhost:6379/{db}")
    process = None

    # Synchronous ping helper
    def ping_redis():
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(client.ping())

    # Synchronous delete helper
    def delete_key(key):
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(client.delete(key))

    try:
        # Check if Redis is already running
        delete_key("sessions_capacity")
        delete_key("expirations")
        if not ping_redis():
            raise aioredis.ConnectionError("Redis ping failed")
    except aioredis.ConnectionError:
        # If not running, start redis-server
        process = subprocess.Popen(
            ["redis-server"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        # Wait briefly for server to start
        asyncio.get_event_loop().run_until_complete(asyncio.sleep(1))

        # Verify it started successfully
        if not ping_redis():
            pytest.fail("Could not start or connect to Redis server")

    yield client

    # Cleanup
    if process:
        process.terminate()
    asyncio.get_event_loop().run_until_complete(client.close())


@pytest.fixture
def servers(request, redis_server, event_loop):
    """Set up servers with max_sessions_list, base_port, and db from markers."""
    # Get the server_config marker
    server_config_marker = request.node.get_closest_marker("server_config")
    if not server_config_marker:
        pytest.fail("server_config marker is required for the servers fixture")

    # Extract max_sessions_list and base_port from the marker
    max_sessions_list = server_config_marker.kwargs["max_sessions_list"]
    base_port = server_config_marker.kwargs["base_port"]

    # Get the redis_db marker
    redis_db_marker = request.node.get_closest_marker("redis_db")
    if not redis_db_marker:
        pytest.fail("redis_db marker is required for the servers fixture")
    db = redis_db_marker.args[0]

    if not isinstance(max_sessions_list, list) or not all(
        isinstance(x, int) for x in max_sessions_list
    ):
        pytest.fail("max_sessions_list must be a list of integers")
    if not isinstance(base_port, int):
        pytest.fail("base_port must be an integer")
    if not isinstance(db, int):
        pytest.fail("db must be an integer")

    server_instances = []
    server_tasks = []
    health_instances = []

    async def setup():
        nonlocal server_instances, server_tasks, health_instances
        for i, max_sessions in enumerate(max_sessions_list):
            public_port = base_port + (i * 2)
            internal_port = public_port + 1

            config = Config(
                public_listen_ip="127.0.0.1",
                public_listen_port=public_port,
                internal_connection_base_url="ws://127.0.0.1",
                internal_listen_ip="127.0.0.1",
                internal_listen_port=internal_port,
                redis_config=RedisConfig(host="127.0.0.1", port=6379, db=db),
                session_input_timeout=0.1,
                session_output_timeout=0.1,
                max_sessions=max_sessions,
            )

            model = mock.MockModel()
            health = RedisHealth(config=config, update_interval=0.5)
            server = WebSocketServer(config=config, health=health, model=model)

            health_instances.append(health)
            server_instances.append(server)
            server_tasks.append(asyncio.create_task(health.start()))
            server_tasks.append(asyncio.create_task(server.start_server()))

        await asyncio.sleep(1)  # Ensure servers are up

    async def teardown():
        for server, task in zip(server_instances, server_tasks):
            if hasattr(server, "stop_server"):
                await server.stop_server()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await asyncio.gather(*server_tasks, return_exceptions=True)

        for health in health_instances:
            await health.close()

    # Run setup in the event loop
    event_loop.run_until_complete(setup())

    # Yield the result to the test
    yield server_instances, server_tasks

    # Run teardown in the event loop
    event_loop.run_until_complete(teardown())


@pytest.mark.asyncio
@pytest.mark.redis_db(2)
@pytest.mark.server_config(max_sessions_list=[1], base_port=7000)
async def test_basic_server(servers, redis_server):
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    server_instances, server_tasks = servers
    uri_1 = "ws://127.0.0.1:7000/ws"

    async with ClientSession() as session:
        async with session.ws_connect(uri_1) as websocket:
            # Start session
            start_msg = SendMessage(
                session="session_1", start_session=StartSession(voice="tara")
            )
            await websocket.send_bytes(start_msg.SerializeToString())

            # Push some text
            push_msg = SendMessage(
                session="session_1", push_text=PushText(text="Hello, this is a test")
            )
            await websocket.send_bytes(push_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive()
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Send EOS
            eos_msg = SendMessage(session="session_1", eos=Eos())
            await websocket.send_bytes(eos_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive()
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Receive finished message
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            finished_response = ReceiveMessage.FromString(msg.data)
            assert finished_response.HasField("finished")


@pytest.mark.asyncio
@pytest.mark.redis_db(3)
@pytest.mark.server_config(max_sessions_list=[1, 1], base_port=7200)
async def test_proxy_server_happy(servers, redis_server):
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    server_instances, server_tasks = servers
    uri = "ws://127.0.0.1:7200/ws"

    async with ClientSession() as session:
        async with session.ws_connect(uri) as websocket:
            # Start first session that fills up the first server
            await websocket.send_bytes(
                SendMessage(
                    session="session_dummy", start_session=StartSession(voice="tara")
                ).SerializeToString()
            )

            # Start session
            await websocket.send_bytes(
                SendMessage(
                    session="session_1", start_session=StartSession(voice="tara")
                ).SerializeToString()
            )

            # Push some text
            push_msg = SendMessage(
                session="session_1", push_text=PushText(text="Hello, this is a test")
            )
            await websocket.send_bytes(push_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Send EOS
            eos_msg = SendMessage(session="session_1", eos=Eos())
            await websocket.send_bytes(eos_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Receive finished message
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            finished_response = ReceiveMessage.FromString(msg.data)
            assert finished_response.HasField("finished")


@pytest.mark.asyncio
@pytest.mark.redis_db(4)
@pytest.mark.server_config(max_sessions_list=[1, 1], base_port=7300)
async def test_proxy_server_capacity(servers, redis_server):
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    server_instances, server_tasks = servers
    uri = "ws://127.0.0.1:7300/ws"

    async with ClientSession() as session:
        async with session.ws_connect(uri) as websocket:
            # Start first session that fills up the first server
            await websocket.send_bytes(
                SendMessage(
                    session="session_1", start_session=StartSession(voice="tara")
                ).SerializeToString()
            )

            # Start session
            await websocket.send_bytes(
                SendMessage(
                    session="session_2", start_session=StartSession(voice="tara")
                ).SerializeToString()
            )

            await websocket.send_bytes(
                SendMessage(
                    session="session_3", start_session=StartSession(voice="tara")
                ).SerializeToString()
            )

            # Receive audio data
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            resp = ReceiveMessage.FromString(msg.data)
            assert resp.HasField("error")
            assert resp.session == "session_3"

            # Push some text
            push_msg = SendMessage(
                session="session_1", push_text=PushText(text="Hello, this is a test")
            )
            await websocket.send_bytes(push_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Send EOS
            eos_msg = SendMessage(session="session_1", eos=Eos())
            await websocket.send_bytes(eos_msg.SerializeToString())

            # Receive audio data
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            audio_response = ReceiveMessage.FromString(msg.data)
            assert audio_response.HasField("audio_data")

            # Receive finished message
            msg = await websocket.receive(timeout=1)
            assert msg.type == WSMsgType.BINARY
            finished_response = ReceiveMessage.FromString(msg.data)
            assert finished_response.HasField("finished")


@pytest.mark.asyncio
@pytest.mark.redis_db(5)
@pytest.mark.server_config(max_sessions_list=[10, 10], base_port=7400)
async def test_session_cleanup(servers, redis_server):
    """Test session cleanup: verify all sessions get correct responses and Redis capacity."""
    server_instances, server_tasks = servers
    uri = "ws://127.0.0.1:7400/ws"
    total_sessions = 20
    redis_cli = aioredis.from_url(f"redis://localhost:6379/{5}")

    async with ClientSession() as session:
        async with session.ws_connect(uri) as websocket:
            # Track responses for each session
            session_responses = {
                f"session_{i}": {"audio": 0, "finished": 0}
                for i in range(total_sessions)
            }

            # Send messages for all sessions
            for i in range(total_sessions):
                session_id = f"session_{i}"
                await websocket.send_bytes(
                    SendMessage(
                        session=session_id, start_session=StartSession(voice="tara")
                    ).SerializeToString()
                )
                await websocket.send_bytes(
                    SendMessage(
                        session=session_id, push_text=PushText(text="Hello")
                    ).SerializeToString()
                )
                await websocket.send_bytes(
                    SendMessage(session=session_id, eos=Eos()).SerializeToString()
                )

            # Collect and verify responses (expect 2 per session: audio_data and finished)
            expected_messages = total_sessions * 3  # audio x 2 + finished per session
            for _ in range(expected_messages):
                msg = await websocket.receive(timeout=1)
                assert msg.type == WSMsgType.BINARY
                response = ReceiveMessage.FromString(msg.data)

                if response.HasField("audio_data"):
                    session_responses[response.session]["audio"] += 1
                elif response.HasField("finished"):
                    session_responses[response.session]["finished"] += 1

            # Verify each session received exactly one audio and one finished message
            for session_id, counts in session_responses.items():
                assert counts["audio"] == 2, (
                    f"{session_id} expected 2 audio, got {counts['audio']}"
                )
                assert counts["finished"] == 1, (
                    f"{session_id} expected 1 finished, got {counts['finished']}"
                )

            # Wait for servers to update redis
            await asyncio.sleep(1)

            # Verify Redis sessions_capacity after cleanup
            capacity = await redis_cli.zrange(
                "sessions_capacity", 0, -1, withscores=True
            )
            logging.info("NEIL cap %s", capacity)
            capacity_dict: dict[str, int] = {}
            for k in capacity:
                capacity_dict[k[0].decode()] = int(k[1]) * -1

            assert capacity_dict["ws://127.0.0.1:7401"] == 10
            assert capacity_dict["ws://127.0.0.1:7403"] == 10

        # Run test again but don't send EOS and let session timeout
        async with session.ws_connect(uri) as websocket:
            # Track responses for each session
            session_responses = {
                f"session_{i}": {"audio": 0, "finished": 0}
                for i in range(total_sessions)
            }

            # Send messages for all sessions
            for i in range(total_sessions):
                session_id = f"session_{i}"
                await websocket.send_bytes(
                    SendMessage(
                        session=session_id, start_session=StartSession(voice="tara")
                    ).SerializeToString()
                )
                await websocket.send_bytes(
                    SendMessage(
                        session=session_id, push_text=PushText(text="Hello")
                    ).SerializeToString()
                )

            await asyncio.sleep(2)

            expected_messages = total_sessions * 1  # audio x 1 per session
            for _ in range(expected_messages):
                msg = await websocket.receive(timeout=1)
                assert msg.type == WSMsgType.BINARY
                response = ReceiveMessage.FromString(msg.data)

                if response.HasField("audio_data"):
                    session_responses[response.session]["audio"] += 1
                elif response.HasField("finished"):
                    session_responses[response.session]["finished"] += 1

            # Verify each session received exactly one audio and one finished message
            for session_id, counts in session_responses.items():
                assert counts["audio"] == 1, (
                    f"{session_id} expected 2 audio, got {counts['audio']}"
                )

            # Wait for servers to update redis
            await asyncio.sleep(1)

            # Verify Redis sessions_capacity after cleanup
            capacity = await redis_cli.zrange(
                "sessions_capacity", 0, -1, withscores=True
            )
            capacity_dict: dict[str, int] = {}
            for k in capacity:
                capacity_dict[k[0].decode()] = int(k[1]) * -1

            assert capacity_dict["ws://127.0.0.1:7401"] == 10
            assert capacity_dict["ws://127.0.0.1:7403"] == 10
