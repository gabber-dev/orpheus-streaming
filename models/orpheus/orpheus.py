import asyncio
from vllm import (
    AsyncLLMEngine,
    AsyncEngineArgs,
    SamplingParams,
    TokensPrompt,
)
from vllm.sampling_params import RequestOutputKind
from transformers import AutoTokenizer, PreTrainedTokenizerBase
import uuid
from dataclasses import dataclass
from .decoder import Decoder
from enum import Enum
import time
from .constants import (
    SNAC_TOKENS_PER_SECOND,
)
from .prompt_window import PromptWindow, PromptWindowInference
from ..base import BaseModel, BaseSessionHandle


class OrpheusModel(BaseModel):
    def __init__(self, *, model_directory: str):
        self._model_directory = model_directory
        self.engine = self._setup_engine()
        self.available_voices = ["zoe", "zac", "jess", "leo", "mia", "julia", "leah"]
        t = AutoTokenizer.from_pretrained(model_directory)
        self.tokenizer = t
        self._sessions: dict[str, SessionHandle] = {}
        self._closed = False

    def _setup_engine(self):
        engine_args = AsyncEngineArgs(
            model=self._model_directory,
            max_model_len=8192,
            gpu_memory_utilization=0.8,
            enforce_eager=True,
        )
        return AsyncLLMEngine.from_engine_args(engine_args)

    def create_session(self, session_id: str, voice: str | None = None):
        if self._closed:
            raise RuntimeError("OrpheusModel is closed")

        session = SessionHandle(
            engine=self.engine,
            tokenizer=self.tokenizer,
            voice=voice,
            identifier=session_id,
        )
        self._sessions[session_id] = session
        return session

    def close(self):
        self._closed = True


class SessionHandle(BaseSessionHandle):
    class State(Enum):
        WARMUP = 0
        RUNNING = 1

    def __init__(
        self,
        *,
        identifier: str,
        engine: AsyncLLMEngine,
        tokenizer: PreTrainedTokenizerBase,
        voice: str | None,
        max_text_context_tokens: int = 256,
        max_audio_context_tokens: int = SNAC_TOKENS_PER_SECOND * 4,
    ):
        self._ttft_threshold = 0.5
        self._max_text_context_tokens = max_text_context_tokens
        self._max_audio_context_tokens = max_audio_context_tokens
        self._identifier = identifier
        self._tokenizer = tokenizer
        self._voice = voice
        self._engine = engine
        self._input_queue = asyncio.Queue[str | None]()
        self._output_queue = asyncio.Queue[bytes | None]()
        self._run_task = asyncio.create_task(self.run())
        self._window = PromptWindow(
            tokenizer=self._tokenizer,
            max_context_text_tokens=self._max_text_context_tokens,
            voice=voice,
            previous_audio_tokens=max_audio_context_tokens,
        )
        self._running_inference_tasks: list[asyncio.Task] = []
        self._running_cache_tasks: list[asyncio.Task] = []

    async def run(self):
        index = -1

        async def noop():
            pass

        inference_task = asyncio.create_task(noop())
        inference_job: InferenceJob = NOOPInferenceJob()
        while True:
            prompt = await self._input_queue.get()
            index += 1
            if prompt is None:
                break

            self._window.push_text(prompt)

            # Let input accumulate
            if not inference_job.finished:
                continue

            inference = self._window.get_next_inference()
            if inference is None:
                continue

            inference_job = await self._start_inference(inference)
            inference_task = asyncio.create_task(self._inference_task(inference_job))

        await inference_task
        inference = self._window.get_next_inference()
        while inference is not None:
            inference_job = await self._start_inference(inference)
            inference_task = asyncio.create_task(self._inference_task(inference_job))
            await inference_task
            inference = self._window.get_next_inference()

        self._output_queue.put_nowait(None)

    async def _start_inference(self, prompt: PromptWindowInference):
        job = InferenceJob(
            engine=self._engine,
            input=prompt,
            max_tokens=2048,
        )
        return job

    async def _inference_task(self, job: "InferenceJob"):
        async def audio_task():
            async for audio in job.output_audio_stream():
                self._output_queue.put_nowait(audio)

        async def token_task():
            token_count = 0
            all_tokens = []
            async for token in job.output_token_stream():
                token_count += 1
                all_tokens.append(token)
            self._window.push_previous_inference(job.input.new_text, all_tokens)

        await asyncio.gather(audio_task(), token_task())

    def eos(self):
        self._input_queue.put_nowait(None)

    def push(self, text: str):
        self._input_queue.put_nowait(text)

    async def wait_for_complete(self):
        await self._run_task

    def __aiter__(self):
        return self

    async def __anext__(self):
        audio = await self._output_queue.get()
        if audio is None:
            raise StopAsyncIteration
        return audio


class InferenceJob:
    def __init__(
        self,
        *,
        engine: AsyncLLMEngine,
        input: PromptWindowInference,
        max_tokens: int,
    ):
        self.input = input
        self.req_id = str(uuid.uuid4())
        self._engine = engine
        self._audio_queue = asyncio.Queue[bytes | None]()
        self._token_queue = asyncio.Queue[int | None]()
        self._max_tokens = max_tokens
        self._cancel_task: asyncio.Task | None = None
        self.finished = False
        self._run_task = asyncio.create_task(self.run())
        self._audio_tokens: list[int] = []
        # The input to this job will be the context on the next so we can optimize
        # by prewarming the cache with the next context. In the future we can be
        # smarter and try to prewarm audio tokens as well but that's difficult
        # at the moment because we don't know where the cutoff will be.
        self._prewarm_kv_cache_task = asyncio.create_task(self.prewarm_kv_cache())
        self._kv_cache_req_id = str(uuid.uuid4())

    def cancel(self):
        if self._cancel_task is not None:
            self._cancel_task = asyncio.create_task(self._engine.abort(self.req_id))

    async def run(self):
        decoder = Decoder()
        sampling_params = SamplingParams(
            temperature=0.6,
            top_p=0.8,
            min_tokens=14,
            max_tokens=self._max_tokens,
            stop_token_ids=[128258],
            repetition_penalty=1.1,
            output_kind=RequestOutputKind.DELTA,
        )

        tp = TokensPrompt(prompt_token_ids=self.input.tokenize())

        async def decode():
            async for audio in decoder:
                self._audio_queue.put_nowait(audio)
            self._audio_queue.put_nowait(None)

        decoder_task = asyncio.create_task(decode())
        token_count = 0
        start_time = time.time()
        async for result in self._engine.generate(
            request_id=self.req_id,
            prompt=tp,
            sampling_params=sampling_params,
        ):
            for token in result.outputs[0].token_ids:
                token_count += 1
                if decoder.push_token(token):
                    self._token_queue.put_nowait(token)
                    self._audio_tokens.append(token)

        self._token_queue.put_nowait(None)
        print("NEIL tps", token_count / (time.time() - start_time))

        decoder.eos()
        await decoder_task
        self._finished = True
        self._prewarm_kv_cache_task = asyncio.create_task(
            self._engine.abort(self._kv_cache_req_id)
        )

    async def prewarm_kv_cache(self):
        prompt = PromptWindowInference(
            context_text="",
            context_audio=[],
            new_text=self.input.new_text,
            tokenizer=self.input.tokenizer,
            voice=self.input.voice,
        )
        tp = TokensPrompt(prompt_token_ids=prompt.tokenize())
        async for _ in self._engine.generate(
            request_id=self._kv_cache_req_id,
            prompt=tp,
            sampling_params=SamplingParams(
                temperature=0.6,
                top_p=0.8,
                min_tokens=1,
                max_tokens=1,
                stop_token_ids=[128258],
                repetition_penalty=1.1,
                output_kind=RequestOutputKind.DELTA,
            ),
        ):
            continue

    async def output_token_stream(self):
        while True:
            t = await self._token_queue.get()
            if t is None:
                break
            yield t

    async def output_audio_stream(self):
        while True:
            audio = await self._audio_queue.get()
            if audio is None:
                break
            yield audio


class NOOPInferenceJob(InferenceJob):
    def __init__(self, *args, **kwargs):
        self.finished = True

    async def run(self):
        pass

    def cancel(self):
        pass


@dataclass
class InferenceResult:
    token_limit_reached: bool
    cancelled: bool
    finished: bool
    input_text: str
    input_prefill_audio: list[int]
    output_audio: list[int]
