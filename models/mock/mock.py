import asyncio
from typing import Optional, Dict, AsyncIterator
from ..base import BaseModel, BaseSessionHandle  # Assuming these are in a base module


class MockModel(BaseModel):
    def __init__(self):
        self._sessions: Dict[str, MockSessionHandle] = {}
        self._closed = False

    def create_session(self, session_id: str, voice: Optional[str] = None):
        if self._closed:
            raise RuntimeError("MockModel is closed")

        session = MockSessionHandle()
        self._sessions[session_id] = session
        return session

    def close(self):
        self._closed = True
        for session in self._sessions.values():
            session.eos()


class MockSessionHandle(BaseSessionHandle):
    def __init__(self):
        self._input_queue = asyncio.Queue[str | None]()
        self._output_queue = asyncio.Queue[bytes | None]()
        self._run_task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            prompt = await self._input_queue.get()
            print("NEIL prompt", prompt)
            if prompt is None:
                break

            # Mock processing: simulate some work and return zeros regardless of input
            await asyncio.sleep(0.1)
            data = b"\x00" * 1024
            self._output_queue.put_nowait(data)

        await self._output_queue.put(None)

    def push(self, text: str):
        self._input_queue.put_nowait(text)

    def eos(self):
        self._input_queue.put_nowait(None)

    async def wait_for_complete(self):
        await self._run_task

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        output = await self._output_queue.get()
        if output is None:
            raise StopAsyncIteration
        return output
