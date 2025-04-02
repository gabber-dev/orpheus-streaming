import asyncio
import json
import logging
from abc import ABC, abstractmethod

import aiohttp
from google.protobuf.json_format import MessageToJson, Parse

from proto_generated.health_pb2 import GetServerHealthResponse, ServerHealth

from .config import Config


class Health(ABC):
    # Abstract methods remain unchanged
    @abstractmethod
    async def query_available_servers(self) -> list[GetServerHealthResponse]:
        pass

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def add_session(self):
        pass

    @abstractmethod
    async def remove_session(self):
        pass

    @abstractmethod
    async def can_accept_session(self) -> bool:
        pass

    @abstractmethod
    async def query_all_servers(self) -> list[GetServerHealthResponse]:
        pass

    @abstractmethod
    async def close(self):
        pass


class LocalHealth(Health):
    def __init__(self, config: Config):
        self._config = config
        self._sessions = 0
        self._closed = False

    async def query_available_servers(self) -> list[GetServerHealthResponse]:
        return []

    async def start(self):
        pass

    async def add_session(self):
        self._sessions += 1

    async def remove_session(self):
        self._sessions -= 1

    async def can_accept_session(self) -> bool:
        return self._sessions < self._config.max_sessions

    async def query_all_servers(self) -> list[GetServerHealthResponse]:
        raise NotImplementedError

    async def close(self):
        pass


class ControllerHealth(Health):
    def __init__(self, config: Config):
        self._config = config
        self._sessions = 0
        self._closed = False
        self._client_session = aiohttp.ClientSession()
        self._update_interval = 5
        self._update_task: asyncio.Task | None = None

    async def query_available_servers(self) -> list[GetServerHealthResponse]:
        async with self._client_session.get(
            f"{self._config.controller_url}/health/available_servers"
        ) as resp:
            logging.info("NEIL WAS HERE %s", await resp.text())
            json_res = await resp.json()

            # Convert each JSON item to a protobuf message
            result = []
            for item in json_res:
                message = GetServerHealthResponse()
                Parse(json.dumps(item), message)
                result.append(message)
            return result

    async def start(self):
        self._update_task = asyncio.create_task(self._report_status_loop())

    async def add_session(self):
        self._sessions += 1
        await self._update_status()

    async def remove_session(self):
        self._sessions -= 1
        await self._update_status()

    async def can_accept_session(self) -> bool:
        return self._sessions < self._config.max_sessions

    async def query_all_servers(self) -> list[GetServerHealthResponse]:
        async with self._client_session.get(
            f"{self._config.controller_url}/health/all_servers"
        ) as resp:
            text = await resp.text()
            # Parse JSON text into Python list
            data = json.loads(text)

            # Convert each JSON item to a protobuf message
            result = []
            for item in data:
                message = GetServerHealthResponse()
                Parse(json.dumps(item), message)
                result.append(message)
            return result

    async def _report_status_loop(self):
        while not self._closed:
            logging.info("Updating health status")
            await self._update_status()
            await asyncio.sleep(self._update_interval)

    async def _update_status(self):
        # Create ServerHealth message with current status
        health_status = ServerHealth(
            url=self._config.advertise_url,  # Assuming config has host
            sessions=self._sessions,
            max_sessions=self._config.max_sessions,
        )

        health_json = MessageToJson(health_status)

        try:
            # Send POST request to controller's health report endpoint
            async with self._client_session.post(
                f"{self._config.controller_url}/health/report",
                data=health_json,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status != 200:
                    logging.error(f"Failed to update status: {await resp.text()}")
        except Exception as e:
            logging.error("Error updating health status", exc_info=e)

    async def close(self):
        self._closed = True
        if self._update_task:
            await self._update_task
        await self._client_session.close()
