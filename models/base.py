from typing import AsyncIterator
from abc import ABC, abstractmethod


class BaseModel(ABC):
    @abstractmethod
    def create_session(
        self, session_id: str, voice: str | None = None
    ) -> "BaseSessionHandle":
        pass

    @abstractmethod
    def close(self):
        pass


class BaseSessionHandle(ABC):
    @abstractmethod
    def push(self, text: str):
        pass

    @abstractmethod
    def eos(self):
        pass

    @abstractmethod
    async def wait_for_complete(self):
        pass

    @abstractmethod
    def __aiter__(self) -> AsyncIterator[bytes]:
        pass

    @abstractmethod
    async def __anext__(self) -> bytes:
        pass
