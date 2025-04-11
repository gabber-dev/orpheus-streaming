import logging
import numpy as np

MAGIC_NUMBER_THRESHOLD = 0.004


# TODO: fades, append new inference, etc.
class SilenceRemover:
    """orpheus tends to generate silence at the beginning. Here we remove it to reduce head-of-line latency"""

    def __init__(self):
        self._started = False
        self._silence_time = 0
        self._window = b""

    def push_bytes(self, audio_bytes: bytes):
        if self._started:
            return audio_bytes

        self._silence_time += len(audio_bytes) / 2 / 24000.0
        frame = np.frombuffer(audio_bytes, dtype=np.int16)
        float_arr = frame.astype(np.float32) / 32768.0
        rms = np.sqrt(np.mean(np.square(float_arr)))
        if rms < MAGIC_NUMBER_THRESHOLD:
            return b""

        logging.info(f"Removed {self._silence_time} from beginning")
        self._started = True
        return audio_bytes
