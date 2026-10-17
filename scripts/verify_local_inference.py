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


# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.agent.prompts import (
    get_cash_diagnostic_prompt,
    get_concept_prompt,
    get_credit_underwriting_prompt,
    get_missing_statement_prompt,
    get_conversational_system_prompt,
    numbers_are_grounded,
    sanitize_cfo_reply,
)

TEST_CASES = [
    {
        "name": "Cash Runway Diagnostic (Grounding Verification)",
        "prompt": "What is our current cash runway?",
        "system": get_cash_diagnostic_prompt(
            "RUNWAY",
            "Your current cash runway is 42.5 days based on net monthly burn of $18,450.00 and closing cash balance of $26,137.50.",
        ),
    },
    {
        "name": "Credit Underwriting Qualification",
        "prompt": "Do we qualify for a credit line?",
        "system": get_credit_underwriting_prompt(
            "PRE_QUALIFIED",
            "Based on your 90-day transactions, you pre-qualify for a $50,000 working capital line of credit at 14.5% APR.",
        ),
    },
    {
        "name": "Accrual Profit vs Cash Drain (Concept Explainer)",
        "prompt": "Our net income is positive ($150,000 net profit), but our bank account balance is shrinking every month. Why are we running out of cash if we are profitable?",
        "system": get_concept_prompt(
            "Accrual profit records revenue when earned, while cash only increases when collected. Working capital tied up in accounts receivable or inventory can cause cash drain despite positive net income.",
        ),
    },
    {
        "name": "Skeptical Underwriting (Missing Statement Guard)",
        "prompt": "Can you calculate our Debt Service Coverage Ratio?",
        "system": get_missing_statement_prompt(
            "No bank statement has been uploaded. You must upload a statement CSV or PDF before a Debt Service Coverage Ratio can be calculated.",
        ),
    },
    {
        "name": "Prudent Debt Capacity (Quantitative Routine)",
        "prompt": "How much additional debt can we safely take on?",
        "system": get_conversational_system_prompt(
            "Based on annual EBITDA of $180,000.00 and existing debt service of $35,000.00, your prudent additional debt capacity is $145,000.00 at a 1.25x minimum DSCR floor.",
        ),
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

        system_prompt = test["system"]
        messages = [
            {"role": "system", "content": system_prompt},
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

        grounded = numbers_are_grounded(system_prompt, response)
        sanitized = sanitize_cfo_reply(response)
        clean = (sanitized == response)
        print(f"Grounding Audit: {'PASS' if grounded else 'FAIL (unsupported numbers detected)'}")
        print(f"Sanitizer Audit: {'PASS' if clean else 'FAIL (slop/formatting violations detected)'}\n")

    print("=" * 70)
    print("ALL NATIVE INFERENCE TESTS COMPLETED.")
    print("=" * 70)


if __name__ == "__main__":
    main()
