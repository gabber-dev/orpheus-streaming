import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import os


def downcast_and_save_weights(model_path, output_path):
    # Load the model with float32 (original dtype)
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        torch_dtype=torch.float32,  # Load as float32 first
        device_map="auto",  # Load to GPU if available
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path)

    # Downcast to float16
    model = model.to(dtype=torch.float16)
    print("Model weights downcasted to torch.float16")

    # Ensure output directory exists
    os.makedirs(output_path, exist_ok=True)

    # Save the model using save_pretrained (handles tied weights)
    model.save_pretrained(output_path, safe_serialization=True)
    tokenizer.save_pretrained(output_path)
    print(f"Downcasted model and tokenizer saved to {output_path}")


if __name__ == "__main__":
    original_model_path = "./data/finetune"  # Replace with your original model path
    output_model_path = "./data/finetune-fp16"  # Replace with your output path
    downcast_and_save_weights(original_model_path, output_model_path)
