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
        self._input_queue = asyncio.Queue()
        self._output_queue = asyncio.Queue()
        self._run_task = asyncio.create_task(self.run())

    async def run(self):
        while True:
            prompt = await self._input_queue.get()
            if prompt is None:
                break

            # Mock processing: return zeros regardless of input
            await asyncio.sleep(0.1)  # Simulate processing delay
            await self._output_queue.put(b"\x00" * 1024)  # 1KB of zeros

        await self._output_queue.put(None)

    def push(self, text: str):
        """Add text to the input queue"""
        self._input_queue.put_nowait(text)

    def eos(self):
        """Signal end of session"""
        self._input_queue.put_nowait(None)

    async def wait_for_complete(self):
        """Wait for all processing to complete"""
        await self._run_task

    def __aiter__(self) -> AsyncIterator[bytes]:
        """Return self as an async iterator"""
        return self

    async def __anext__(self) -> bytes:
        """Get the next output chunk"""
        output = await self._output_queue.get()
        if output is None:
            raise StopAsyncIteration
        return output

    # Additional mock methods
    async def _start_inference(self, prompt):
        # Mock inference job that just returns zeros
        class MockInferenceJob:
            finished = True

            async def output_audio_stream(self):
                yield b"\x00" * 1024
                yield None

            async def output_token_stream(self):
                yield 0  # Mock token
                yield None

        return MockInferenceJob()

    async def _inference_task(self, job):
        async for audio in job.output_audio_stream():
            if audio is not None:
                await self._output_queue.put(audio)
