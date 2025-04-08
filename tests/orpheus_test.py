import pytest
import os
from server import Config
from models.orpheus import OrpheusModel
import whisper
import torchaudio
import jiwer
import numpy as np
import torch
import soundfile as sf


@pytest.mark.asyncio
async def test_basic_model():
    model = OrpheusModel(model_directory="data/finetune-fp16")
    session = model.create_session(session_id="test_session_123", voice="en")

    # Define the reference text (what was actually said)
    input_texts = [
        "Hello world. Is this working?",
        "Th",
        "is is a test.",
        SCRIPT,
    ]
    # input_texts = [
    #     "Okay well it's kind of working. Just missing the last sentence right? Not any other sentences? test 123"
    # ]

    reference_text = "".join(input_texts).replace("\n", " ")

    for text in input_texts:
        session.push(text)
    session.eos()

    accumulated_audio = b""
    async for audio in session:
        accumulated_audio += audio

    audio_np = np.frombuffer(accumulated_audio, dtype=np.int16)

    # Convert to float32 and normalize to [-1, 1]
    audio_float = audio_np.astype(np.float32) / 32768.0

    # Save the audio to file (using 24kHz sample rate as original)
    output_path = "/tmp/test.wav"
    sf.write(output_path, audio_float, 24000, format="WAV")
    print(f"Audio saved to {output_path}")

    # Convert to torch tensor
    audio_tensor = torch.from_numpy(audio_float)

    # Resample to 16kHz (Whisper expects 16kHz)
    resampler = torchaudio.transforms.Resample(orig_freq=24000, new_freq=16000)
    audio_tensor = resampler(audio_tensor)

    whisper_model = whisper.load_model("tiny.en")
    result = whisper_model.transcribe(
        audio_tensor.numpy(), language="en", fp16=torch.cuda.is_available()
    )

    hypothesis_text = result["text"]
    print("Transcribed text:", hypothesis_text)

    # Calculate WER
    wer = jiwer.wer(reference_text, hypothesis_text)
    print(f"Word Error Rate (WER): {wer:.4f}")

    # Optional: Print more detailed metrics
    measures = jiwer.compute_measures(reference_text, hypothesis_text)
    print(f"WER: {measures['wer']:.4f}")
    print(f"Insertions: {measures['insertions']}")
    print(f"Deletions: {measures['deletions']}")
    print(f"Substitutions: {measures['substitutions']}")

    assert wer < 0.20, f"Word Error Rate is too high: {wer:.4f}"


SCRIPT = """In a quiet village nestled between mountains, a young girl named Lila discovered a hidden cave shimmering with strange light. She stepped inside, her curiosity outweighing her fear, and found an ancient book bound in leather that pulsed with warmth. As she opened it, words floated off the pages, whispering secrets of a forgotten world where dragons soared and rivers sang. Lila read aloud, her voice trembling, and the cave rumbled as a golden dragon materialized before her, its eyes kind yet fierce roaring. The dragon bowed, calling her its keeper, destined to protect the balance between realms. Each night, she returned, learning spells and histories, her ordinary life unraveling into something extraordinary. The village noticed changes—crops flourished, storms softened—and whispered of a guardian among them. Lila kept her secret, but the dragon’s shadow sometimes danced across the moonlit sky. One day, a dark mist crept toward the village, and Lila knew her true test was near echoing in her mind. With the book in hand and the dragon at her side, she stepped forward, ready to face the unknown."""
