import asyncio
import logging

import aioredis
import aioredis.client
import pytest
from aiohttp import ClientSession, WSMsgType

from models import mock
from server import Config, Health, ControllerHealth, WebSocketServer, LocalHealth
from controller import Controller, Config as ControllerConfig
from proto_generated.tts_pb2 import (
    Eos,
    PushText,
    ReceiveMessage,
    SendMessage,
    StartSession,
)


@pytest.mark.asyncio
async def test_basic_server():
    config = create_config(port=7000, max_sessions=1, controller_url=None)
    health = create_local_health(config)
    server = create_server(config, health)

    tasks = asyncio.gather(server.start(), health.start())
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    uri_1 = "ws://127.0.0.1:7000/ws"

    await asyncio.sleep(1)

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

    await server.stop_server()
    await health.close()
    await tasks


@pytest.mark.asyncio
async def test_proxy_server_happy():
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    c_1, c_2 = (
        create_config(
            port=7100, max_sessions=1, controller_url="http://127.0.0.1:9000"
        ),
        create_config(
            port=7200, max_sessions=1, controller_url="http://127.0.0.1:9000"
        ),
    )
    h_1, h_2 = create_local_health(c_1), create_local_health(c_2)
    s_1, s_2 = create_server(c_1, h_1), create_server(c_2, h_2)
    ctrl = create_controller_server(port=9000)

    tasks = asyncio.gather(
        s_1.start(),
        s_2.start(),
        h_1.start(),
        h_2.start(),
        ctrl.start(),
    )

    uri = "ws://127.0.0.1:7200/ws"

    await asyncio.sleep(1)

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

    await s_1.stop_server()
    await s_2.stop_server()
    await h_1.close()
    await h_2.close()
    await ctrl.close()
    await tasks


@pytest.mark.asyncio
async def test_proxy_server_capacity():
    """Test basic TTS functionality: start session, push text, get audio, send EOS"""
    c_1, c_2 = (
        create_config(
            port=7300, max_sessions=1, controller_url="http://127.0.0.1:9001"
        ),
        create_config(
            port=7400, max_sessions=1, controller_url="http://127.0.0.1:9001"
        ),
    )
    h_1, h_2 = create_local_health(c_1), create_local_health(c_2)
    s_1, s_2 = create_server(c_1, h_1), create_server(c_2, h_2)
    ctrl = create_controller_server(port=9001)

    tasks = asyncio.gather(
        s_1.start(),
        s_2.start(),
        h_1.start(),
        h_2.start(),
        ctrl.start(),
    )

    uri = "ws://127.0.0.1:7300/ws"
    uri = "ws://127.0.0.1:7400/ws"

    await asyncio.sleep(1)

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

    await s_1.stop_server()
    await s_2.stop_server()
    await h_1.close()
    await h_2.close()
    await ctrl.close()
    await tasks


@pytest.mark.asyncio
async def test_session_cleanup():
    """Test session cleanup: verify all sessions get correct responses and Redis capacity."""
    c_1, c_2 = (
        create_config(
            port=7500, max_sessions=10, controller_url="http://127.0.0.1:9002"
        ),
        create_config(
            port=7600, max_sessions=10, controller_url="http://127.0.0.1:9002"
        ),
    )
    h_1, h_2 = create_local_health(c_1), create_local_health(c_2)
    s_1, s_2 = create_server(c_1, h_1), create_server(c_2, h_2)
    ctrl = create_controller_server(port=9002)

    tasks = asyncio.gather(
        s_1.start(),
        s_2.start(),
        h_1.start(),
        h_2.start(),
        ctrl.start(),
    )

    uri = "ws://127.0.0.1:7500/ws"
    total_sessions = 20

    await asyncio.sleep(1)

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

            health_servers = await session.get(
                "http://127.0.0.1:9002/health/available_servers"
            )
            print("NEIL ", health_servers)

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

            health_servers = await session.get(
                "http://127.0.0.1:9002/health/available_servers"
            )
            print("NEIL ", health_servers)

    await s_1.stop_server()
    await s_2.stop_server()
    await h_1.close()
    await h_2.close()
    await ctrl.close()
    await tasks


def create_config(*, port: int, max_sessions: int, controller_url: str | None):
    return Config(
        listen_ip="127.0.0.1",
        listen_port=port,
        advertise_url=f"ws://127.0.0.1:{port}",
        max_sessions=max_sessions,
        session_input_timeout=0.5,
        session_output_timeout=0.5,
        controller_url=controller_url,
    )


def create_local_health(config: Config):
    return LocalHealth(config=config)


def create_controller_health(config: Config):
    return ControllerHealth(config=config)


def create_server(config: Config, health: Health):
    return WebSocketServer(
        config=config,
        health=health,
        model=mock.MockModel(),
    )


def create_controller_server(port: int):
    return Controller(config=ControllerConfig(listen_ip="127.0.0.1", listen_port=port))
