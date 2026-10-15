"""Download Llama-3.2-1B-Instruct-GENAI-ONNX CPU INT4 model weights."""

import os
import sys
from huggingface_hub import hf_hub_download

REPO_ID = "onnx-community/Llama-3.2-1B-Instruct-GENAI-ONNX"
SUBFOLDER = "cpu_and_mobile/cpu-int4-rtn-block-32-acc-level-4"
TARGET_DIR = os.path.abspath("models/llama-3.2-1b-instruct-onnx")

FILES = [
    "config.json",
    "genai_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "model.onnx",
    "model.onnx.data",
]


def download_model():
    print(f"Downloading {REPO_ID} [{SUBFOLDER}]...")
    print(f"Target directory: {TARGET_DIR}")
    for fname in FILES:
        print(f"Downloading {fname}...")
        p = hf_hub_download(
            repo_id=REPO_ID,
            filename=fname,
            subfolder=SUBFOLDER,
            local_dir=TARGET_DIR,
        )
        print(f"  [OK] {fname} ready: {p}")

    model_dir = os.path.join(TARGET_DIR, SUBFOLDER)
    print("\nVerifying onnxruntime-genai load...")
    import onnxruntime_genai as og
    model = og.Model(model_dir)
    tokenizer = og.Tokenizer(model)
    print("[OK] Model and Tokenizer loaded successfully into onnxruntime-genai!")


if __name__ == "__main__":
    download_model()
