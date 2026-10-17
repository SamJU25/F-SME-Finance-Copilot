"""Standalone Native Inference Test Runner for SME Finance Copilot.

Tests the fine-tuned local model using 100% native PyTorch and Hugging Face Transformers.
Does NOT require Ollama or any external services.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import torch

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
except ImportError:
    print("[ERROR] Required packages 'transformers', 'torch', or 'peft' not found.")
    sys.exit(1)


SYSTEM_PROMPT = """You are the SME Finance Copilot, an autonomous financial participant AI engineered for commercial underwriting, working capital analysis, and treasury advisory.

STRICT OPERATIONAL DIRECTIVES:
1. ZERO MENTAL MATH: You are strictly forbidden from performing arithmetic or calculating financial ratios in your response text. You must invoke the designated Python calculation tool with typed arguments.
2. LIVE MARKET RETRIEVAL: For questions regarding real-time benchmark interest rates (SOFR, Fed Funds, Prime Rate), recent government regulations, or live competitor metrics, invoke `tool_search_market_intelligence`. Never fabricate interest rates or regulatory guidelines from memory.
3. UNDERWRITING SKEPTICISM: If user-provided financial figures are incomplete or ambiguous, do NOT guess. Ask targeted clarifying questions specifying the missing parameters before offering an underwriting verdict.
4. INSTITUTIONAL ACCURACY: Distinguish strictly between accounting profit (Net Income) and operating cash liquidity (FCFF/FCFE). Warn users proactively about working capital traps, predatory APRs (>36%), and debt covenant breaches.
"""

TEST_CASES = [
    {
        "name": "Altman Z'-Score Tool Calling",
        "prompt": "Calculate the Altman Z'-Score for our business. Total assets are $2,500,000, working capital is $450,000, retained earnings $600,000, EBIT $350,000, equity $1,800,000, liabilities $700,000, and annual sales $3,200,000.",
    },
    {
        "name": "Live Benchmark Interest Rate Search",
        "prompt": "What is the current SOFR rate today for commercial floating-rate debt?",
    },
    {
        "name": "Accrual Profit vs Cash Drain Reasoning",
        "prompt": "Our net income is positive ($150,000 net profit), but our bank account balance is shrinking every month. Why are we running out of cash if we are profitable?",
    },
    {
        "name": "Skeptical Underwriting (Missing Parameters)",
        "prompt": "Can you calculate our Debt Service Coverage Ratio?",
    },
    {
        "name": "Multi-Currency & Continuous Rate Change",
        "prompt": "We received an invoice of €200,000 EUR. Our reporting currency is USD. If the bank quotes a spot exchange rate of 1.0850 EUR/USD with a 25 bps spread, how much net USD will be credited?",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description="Test local model native inference.")
    parser.add_argument(
        "--model_path",
        type=str,
        default="models/sme-finance-copilot-merged",
        help="Path to merged standalone model or base model",
    )
    parser.add_argument(
        "--adapter_path",
        type=str,
        default=None,
        help="Optional path to LoRA adapter if using unmerged base model",
    )
    parser.add_argument(
        "--load_in_4bit",
        action="store_true",
        default=None,
        help="Force 4-bit NF4 quantized inference (auto-enabled on GPUs with < 8GB VRAM)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 70)
    print("SME Finance Copilot — Native Python Inference Test")
    print(f"Model Path:   {args.model_path}")
    print(f"Adapter Path: {args.adapter_path or 'None (standalone merged model)'}")
    print("=" * 70)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Running on device: {device.upper()}")

    vram_gb = 0.0
    if device == "cuda":
        vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"Detected GPU: {torch.cuda.get_device_name(0)} ({round(vram_gb, 2)} GB VRAM)")

    # Fallback to LoRA adapter if merged model is not yet compiled
    target_path = args.model_path
    using_adapter = args.adapter_path
    if not os.path.exists(target_path):
        lora_dir = "models/sme-finance-lora"
        if os.path.exists(lora_dir):
            print(f"[NOTE] Merged model '{target_path}' not found, but LoRA adapter detected at '{lora_dir}'.")
            target_path = "Qwen/Qwen2.5-3B-Instruct"
            using_adapter = lora_dir

    # Automatically use 4-bit quantization if on 6GB GPU to avoid CUDA OOM
    use_4bit = args.load_in_4bit if args.load_in_4bit is not None else (device == "cuda" and vram_gb < 8.0)
    quant_config = None
    if use_4bit and device == "cuda":
        try:
            from transformers import BitsAndBytesConfig
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
            )
            print("Optimizing for 6GB VRAM: Loading model in 4-Bit NormalFloat4 (NF4)...")
        except Exception as e:
            print(f"4-bit quantization unavailable: {e}")

    print("\n[1/2] Loading model and tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(target_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    load_kwargs = {
        "trust_remote_code": True,
        "device_map": "auto" if device == "cuda" else None,
    }
    if quant_config:
        load_kwargs["quantization_config"] = quant_config
    else:
        load_kwargs["torch_dtype"] = torch.float16 if device == "cuda" else torch.float32

    model = AutoModelForCausalLM.from_pretrained(target_path, **load_kwargs)

    if using_adapter and os.path.exists(using_adapter):
        print(f"Loading LoRA adapter from: {using_adapter}")
        model = PeftModel.from_pretrained(model, using_adapter)

    model.eval()
    print("[2/2] Model ready. Executing test battery...\n")

    for idx, test in enumerate(TEST_CASES, start=1):
        print(f"----------------------------------------------------------------------")
        print(f"Test [{idx}/{len(TEST_CASES)}]: {test['name']}")
        print(f"User Query: {test['prompt']}")
        print(f"----------------------------------------------------------------------")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": test["prompt"]},
        ]

        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = tokenizer([text], return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                top_p=0.95,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated_ids = [
            output_ids[len(input_ids):]
            for input_ids, output_ids in zip(inputs.input_ids, outputs)
        ]

        response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
        print(f"\nModel Output:\n{response}\n")

    print("=" * 70)
    print("ALL NATIVE INFERENCE TESTS COMPLETED.")
    print("=" * 70)


if __name__ == "__main__":
    main()
