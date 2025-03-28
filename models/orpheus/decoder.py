import asyncio
import torch
from snac import SNAC
import numpy as np
from typing import Any

snac_device = "cuda"
snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").eval()
snac = torch.compile(snac.to(snac_device), mode="max-autotune")


class Decoder:
    def __init__(self):
        self.model = snac
        self._buffer_queue = asyncio.Queue[list[int] | None]()
        self._output_queue = asyncio.Queue[bytes | None]()
        self._buffer: list[int] = []
        self._used_tokens: list[int] = []
        self._run_task = asyncio.create_task(self.run())
        self._count = 0

    def convert_to_audio(self, multiframe: list[int]):
        if len(multiframe) < 7:
            return

        codes_0 = torch.tensor([], device=snac_device, dtype=torch.int32)
        codes_1 = torch.tensor([], device=snac_device, dtype=torch.int32)
        codes_2 = torch.tensor([], device=snac_device, dtype=torch.int32)

        num_frames = len(multiframe) // 7
        frame = multiframe[: num_frames * 7]

        for j in range(num_frames):
            i = 7 * j
            if codes_0.shape[0] == 0:
                codes_0 = torch.tensor(
                    [frame[i]], device=snac_device, dtype=torch.int32
                )
            else:
                codes_0 = torch.cat(
                    [
                        codes_0,
                        torch.tensor([frame[i]], device=snac_device, dtype=torch.int32),
                    ]
                )

            if codes_1.shape[0] == 0:
                codes_1 = torch.tensor(
                    [frame[i + 1]], device=snac_device, dtype=torch.int32
                )
                codes_1 = torch.cat(
                    [
                        codes_1,
                        torch.tensor(
                            [frame[i + 4]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
            else:
                codes_1 = torch.cat(
                    [
                        codes_1,
                        torch.tensor(
                            [frame[i + 1]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_1 = torch.cat(
                    [
                        codes_1,
                        torch.tensor(
                            [frame[i + 4]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )

            if codes_2.shape[0] == 0:
                codes_2 = torch.tensor(
                    [frame[i + 2]], device=snac_device, dtype=torch.int32
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 3]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 5]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 6]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
            else:
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 2]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 3]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 5]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )
                codes_2 = torch.cat(
                    [
                        codes_2,
                        torch.tensor(
                            [frame[i + 6]], device=snac_device, dtype=torch.int32
                        ),
                    ]
                )

        codes = [codes_0.unsqueeze(0), codes_1.unsqueeze(0), codes_2.unsqueeze(0)]
        # check that all tokens are between 0 and 4096 otherwise return *
        if (
            torch.any(codes[0] < 0)
            or torch.any(codes[0] > 4096)
            or torch.any(codes[1] < 0)
            or torch.any(codes[1] > 4096)
            or torch.any(codes[2] < 0)
            or torch.any(codes[2] > 4096)
        ):
            return

        with torch.inference_mode():
            audio_hat = self.model.decode(codes)

        audio_slice = audio_hat[:, :, 2048:4096]
        detached_audio = audio_slice.detach().cpu()
        audio_np = detached_audio.numpy()
        audio_int16 = (audio_np * 32767).astype(np.int16)
        audio_bytes = audio_int16.tobytes()
        return audio_bytes

    def token_to_snac_decoder_input(self, token: int, index: int):
        token = token - 128256  # <custom_token_0>
        return token - 10 - ((index % 7) * 4096)

    async def run(self):
        while True:
            buffer = await self._buffer_queue.get()
            if buffer is None:
                break
            audio_samples = self.convert_to_audio(buffer)
            if audio_samples is not None:
                self._output_queue.put_nowait(audio_samples)

        self._output_queue.put_nowait(None)

    def push_token(self, token: int) -> bool:
        token = self.token_to_snac_decoder_input(token, self._count)
        if token is None:
            return False

        if token < 0:
            return False

        self._buffer.append(token)
        self._count += 1

        if self._count % 7 == 0 and self._count > 27:
            self._buffer_queue.put_nowait(self._buffer[-28:])

        return True

    def eos(self):
        self._buffer_queue.put_nowait(None)

    def __aiter__(self):
        return self

    async def __anext__(self):
        audio = await self._output_queue.get()
        if audio is None:
            raise StopAsyncIteration
        return audio

    def get_used_tokens(self):
        return self._used_tokens


# This is the magic number during testing that we use to determine if a frame is loud enough
# to possibly contain speech. It's very conservative.
MAGIC_NUMBER_THRESHOLD = 0.004


class BasicAudioEnergyFilter:
    def __init__(self, *, cooldown_seconds: float = 1, sample_rate: int):
        self._cooldown_seconds = cooldown_seconds
        self._cooldown = cooldown_seconds
        self._sample_rate = sample_rate

    def push_frame(self, frame: np.ndarray[Any, np.dtype[np.int16]]) -> bool:
        float_arr = frame.astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(np.square(float_arr)))
        if rms > MAGIC_NUMBER_THRESHOLD:
            self._cooldown = self._cooldown_seconds
            return True

        duration_seconds = frame.shape[0] / self._sample_rate
        self._cooldown -= duration_seconds
        if self._cooldown > 0:
            return True

        return False
