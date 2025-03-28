import asyncio
from models.orpheus import OrpheusModel
import time
import struct


def create_wav_header(sample_rate=24000, bits_per_sample=16, channels=1):
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8

    data_size = 0

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )
    return header


async def main():
    # Initialize the model inside a function
    m = OrpheusModel()
    # Example usage

    requests = [
        # [
        #     "Hello, how are you?",
        #     "This is a long sentence."
        #     "Let's keep talking for a while so we can measure how fast this model is.",
        #     "Ok I'm crying now because I'm really sad.",
        #     "Ok now I am happy! Let's all be happy together.",
        #     "Ewww, I'm disgusted.",
        #     "Hey! Stop that!",
        #     "Shhh, let's be really quiet.",
        #     "Let's keep talking for a while so we can show how it sounds with longer output audio."
        #     "Ideally we can get it to over one minute long."
        #     "Once upon a time, there was a little mermaid who lived in the sea.",
        #     "She was very beautiful and had a lovely voice.",
        #     "She loved to sing and would often sing to the fish and other sea creatures.",
        # ],
        [
            "I drove past our old house today when I was back at home for the funeral.",
            " It was a looooooonnnnngggg drive."
            " Another short one. The shutters are blue now.",
            " Funny how something so small can make it feel like a stranger’s place.\n",
            " I kept his jacket, even though it doesn’t fit.",
            " It still smells like winter and cigarettes.",
            " Somehow, that’s comforting.\n",
            " There’s still a crack in the wall from when we moved the bed.",
            " I always meant to fix it.",
            " Now I kind of hope it stays.",
        ],
    ]

    # full = ""

    # for r in requests[0]:
    #     full += r

    # full = full.strip()

    # requests.append([full])

    async def session_task(name: str, requests: list[str]):
        sess = m.create_session(name, voice="tara")
        for request in requests:
            sess.push(request)
        sess.eos()

        start_time = time.time()
        first_token = True
        with open(f"{name}.wav", "wb") as f:
            f.write(create_wav_header())

            async for result in sess:
                if first_token:
                    first_token = False
                    print("NEIL first token:", time.time() - start_time)
                f.write(result)

            print("NEIL total time:", time.time() - start_time)

        await sess.wait_for_complete()

    tasks = [
        asyncio.create_task(session_task(f"session_{i}", r))
        for i, r in enumerate(requests)
    ]

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())


# import torch
# from transformers import AutoModelForCausalLM, AutoTokenizer
# import os


# def downcast_and_save_weights(model_path, output_path):
#     # Load the model with float32 (original dtype)
#     model = AutoModelForCausalLM.from_pretrained(
#         model_path,
#         torch_dtype=torch.float32,  # Load as float32 first
#         device_map="auto",  # Load to GPU if available
#     )
#     tokenizer = AutoTokenizer.from_pretrained(model_path)

#     # Downcast to float16
#     model = model.to(dtype=torch.float16)
#     print("Model weights downcasted to torch.float16")

#     # Ensure output directory exists
#     os.makedirs(output_path, exist_ok=True)

#     # Save the model using save_pretrained (handles tied weights)
#     model.save_pretrained(output_path, safe_serialization=True)
#     tokenizer.save_pretrained(output_path)
#     print(f"Downcasted model and tokenizer saved to {output_path}")


# if __name__ == "__main__":
#     original_model_path = "./data/finetune"  # Replace with your original model path
#     output_model_path = "./data/finetune-fp16"  # Replace with your output path
#     downcast_and_save_weights(original_model_path, output_model_path)
