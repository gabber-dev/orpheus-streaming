import asyncio
import logging
import time
from abc import ABC, abstractmethod

import aioredis
from .config import Config


class Health(ABC):
    # Abstract methods remain unchanged
    @abstractmethod
    async def query_available_servers(self) -> list[str]:
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


class RedisHealth(Health):
    def __init__(
        self,
        *,
        config: Config,
        timeout_seconds: int = 30,
        update_interval: float = 5.0,
    ):
        self._redis = aioredis.Redis(
            host=config.redis_config.host,
            port=config.redis_config.port,
            db=config.redis_config.db,
        )
        self._config = config
        self._internal_connection_base_url = config.internal_connection_base_url
        self._internal_listen_port = config.internal_listen_port
        self._closed = False
        self._report_status_task: asyncio.Task | None = None
        self._cleanup_expired_servers_task: asyncio.Task | None = None
        self._sessions = 0
        self._max_sessions = config.max_sessions
        self._timeout_seconds = timeout_seconds
        self._update_interval = update_interval

    async def start(self):
        self._report_status_task = asyncio.create_task(self._report_status_loop())
        self._cleanup_expired_servers_task = asyncio.create_task(
            self.cleanup_expired_servers_loop()
        )

    async def cleanup_expired_servers_loop(self):
        lock_key = "cleanup_lock"
        lock_timeout = 15
        server_key = (
            f"{self._internal_connection_base_url}:{self._internal_listen_port}"
        )
        while not self._closed:
            lock_acquired = await self._redis.set(
                lock_key,
                server_key,
                nx=True,
                ex=lock_timeout,
            )

            if lock_acquired:
                logging.info(f"Server {server_key} acquired cleanup lock")
                while not self._closed:
                    current_time = time.time()
                    expiration_threshold = current_time - self._timeout_seconds

                    expired_servers = await self._redis.zrangebyscore(
                        "expirations", "-inf", expiration_threshold
                    )

                    if expired_servers:
                        await self._redis.zrem("expirations", *expired_servers)
                        await self._redis.zrem("sessions_capacity", *expired_servers)
                        logging.info(
                            f"Cleaned up {len(expired_servers)} expired servers"
                        )

                    await self._redis.expire(lock_key, lock_timeout)

                    await asyncio.sleep(5)
            else:
                # Lock not acquired, wait and retry
                await asyncio.sleep(1)

    async def query_available_servers(self) -> list[str]:
        servers = await self._redis.zrange("sessions_capacity", 0, 4)
        decoded = [s.decode() for s in servers]
        servers = [
            s
            for s in decoded
            if s != f"{self._internal_connection_base_url}:{self._internal_listen_port}"
        ]
        print("NEIL available servers", servers)
        return servers

    async def _report_status_loop(self):
        while not self._closed:
            await self._update_status()
            await asyncio.sleep(self._update_interval)

    async def _update_status(self):
        # Create ServerHealth object

        # Serialize the entire ServerHealth object
        server_data = f"{self._config.internal_connection_base_url}:{self._config.internal_listen_port}"
        current_time = time.time()

        capacity_score = (
            self._sessions - self._max_sessions
        )  # negative number of sessions available
        await self._redis.zadd("sessions_capacity", {server_data: capacity_score})
        await self._redis.zadd("expirations", {server_data: current_time})

    async def add_session(self):
        self._sessions += 1
        await self._update_status()

    async def remove_session(self):
        self._sessions = max(0, self._sessions - 1)
        await self._update_status()

    async def can_accept_session(self) -> bool:
        if self._closed:
            return False
        return self._sessions < self._max_sessions

    async def close(self):
        self._closed = True
        if self._report_status_task:
            try:
                self._report_status_task.cancel()
                await self._report_status_task
            except asyncio.CancelledError:
                pass
        await self._redis.close()
        if self._cleanup_expired_servers_task:
            await self._cleanup_expired_servers_task
