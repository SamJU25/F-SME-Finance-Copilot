"""Standalone Model Weight Merger for SME Finance Copilot.

Merges fine-tuned LoRA adapters directly into the base foundation model
producing a single, self-contained Hugging Face directory for native Python inference
without relying on Ollama or external daemons.
"""

from __future__ import annotations

import argparse
import os
import sys
import torch

try:
    from peft import AutoPeftModelForCausalLM
    from transformers import AutoTokenizer
except ImportError:
    print("[ERROR] Required packages 'peft' and 'transformers' are not installed.")
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Merge LoRA adapter into standalone base model.")
    parser.add_argument(
        "--adapter_dir",
        type=str,
        default="models/sme-finance-lora",
        help="Path to trained LoRA adapter directory",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="models/sme-finance-copilot-merged",
        help="Path to save merged standalone model",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help="Device to perform weight merging on ('cpu' recommended to avoid 6GB VRAM OOM, or 'cuda')",
    )
    return parser.parse_args()



def main():
    args = parse_args()
    print("=" * 70)
    print("SME Finance Copilot — Standalone Model Weight Merger")
    print(f"LoRA Adapter: {args.adapter_dir}")
    print(f"Target Output: {args.output_dir}")
    print(f"Compute Device: {args.device.upper()}")
    print("=" * 70)

    if not os.path.exists(args.adapter_dir):
        print(f"[ERROR] Adapter directory '{args.adapter_dir}' not found.")
        sys.exit(1)

    print(f"\n[1/3] Loading base model with LoRA adapter on {args.device.upper()}...")
    model = AutoPeftModelForCausalLM.from_pretrained(
        args.adapter_dir,
        device_map=args.device,
        torch_dtype=torch.float16,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.adapter_dir)

    print("\n[2/3] Merging LoRA matrices into base weights (merge_and_unload)...")
    merged_model = model.merge_and_unload()

    print(f"\n[3/3] Saving merged standalone model to: {args.output_dir}")
    os.makedirs(args.output_dir, exist_ok=True)
    merged_model.save_pretrained(args.output_dir, safe_serialization=True)
    tokenizer.save_pretrained(args.output_dir)

    print("=" * 70)
    print("MERGE COMPLETE: Self-contained model is ready for 100% native Python inference.")
    print(f"Model path: {args.output_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
