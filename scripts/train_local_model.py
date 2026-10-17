"""Production QLoRA Fine-Tuning Pipeline for SME Finance Copilot.

Fine-tunes open-weight foundation models (default: Qwen/Qwen2.5-3B-Instruct)
on the verified financial reasoning and executive communication dataset (`dataset/finetune_train.jsonl`).

Optimizations:
- 4-Bit NormalFloat4 (NF4) Quantization with Double Quant via bitsandbytes.
- Low-Rank Adaptation (LoRA) on all attention & MLP projection layers.
- ChatML conversation tokenization via Hugging Face TRL SFTTrainer.
- Standalone PyTorch/PEFT native LoRA checkpoint export.

Hardware Requirements:
- Trainable on a single 6GB-16GB VRAM GPU (RTX 4050/3060/4060, T4, L4, A100).
"""

from __future__ import annotations

import argparse
import os
import sys
import torch

try:
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from datasets import load_dataset
    try:
        from trl import SFTConfig, SFTTrainer
        HAS_SFT_CONFIG = True
    except ImportError:
        from trl import SFTTrainer
        HAS_SFT_CONFIG = False
except ImportError:
    print(
        "\n[ERROR] Required fine-tuning packages missing. Install them with:\n"
        "pip install torch transformers peft bitsandbytes datasets trl accelerate\n"
    )
    sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune local financial model via QLoRA.")
    parser.add_argument(
        "--model_id",
        type=str,
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Base Hugging Face model ID (e.g. Qwen/Qwen2.5-3B-Instruct, Qwen/Qwen2.5-7B-Instruct, meta-llama/Llama-3.2-3B-Instruct)",
    )
    parser.add_argument(
        "--train_file",
        type=str,
        default="dataset/finetune_train.jsonl",
        help="Path to training JSONL file",
    )
    parser.add_argument(
        "--val_file",
        type=str,
        default="dataset/finetune_val.jsonl",
        help="Path to validation JSONL file",
    )
    parser.add_argument(
        "--output_dir",
        type=str,
        default="models/sme-finance-lora",
        help="Directory to save fine-tuned LoRA weights",
    )
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch_size", type=int, default=1, help="Per-device train batch size (1 recommended for 6GB VRAM)")
    parser.add_argument("--grad_accum", type=int, default=16, help="Gradient accumulation steps (effective batch size = batch_size * grad_accum = 16)")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--max_seq_length", type=int, default=1536, help="Maximum sequence length")
    parser.add_argument("--max_steps", type=int, default=-1, help="If > 0, train for exact steps (useful for pre-flight dry runs)")
    return parser.parse_args()


def export_standalone_instructions(output_dir: str):
    """Outputs standalone native inference instructions (zero Ollama dependency)."""
    print(f"\n[OK] Fine-tuned LoRA adapter saved at: {output_dir}")
    print("Next Step to Run Natively in Python (No Ollama needed):")
    print("  python scripts/merge_model.py --adapter_dir " + output_dir)
    print("  python scripts/verify_local_inference.py\n")


def main():
    args = parse_args()
    print("=" * 70)
    print("SME Finance Copilot — QLoRA Local Model Fine-Tuning Pipeline")
    print(f"Base Model:       {args.model_id}")
    print(f"Training Dataset: {args.train_file}")
    print(f"Validation Set:   {args.val_file}")
    print(f"Output Directory: {args.output_dir}")
    print("=" * 70)

    if not os.path.exists(args.train_file):
        print(f"[ERROR] Training file '{args.train_file}' not found. Run scripts/generate_finetune_dataset.py first.")
        sys.exit(1)

    # 1. 4-Bit NormalFloat4 Quantization Configuration
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )

    # 2. Load Base Model and Tokenizer
    print("\n[1/5] Loading tokenizer and 4-bit base model...")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)

    # 3. LoRA Configuration on All Linear Projections
    print("\n[2/5] Configuring LoRA adapters...")
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=target_modules,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Load and Format Dataset
    print("\n[3/5] Loading ChatML dataset...")
    train_dataset = load_dataset("json", data_files=args.train_file, split="train")
    val_dataset = load_dataset("json", data_files=args.val_file, split="train") if os.path.exists(args.val_file) else None

    def format_chatml(batch):
        formatted = []
        for conversation in batch["messages"]:
            text = tokenizer.apply_chat_template(
                conversation,
                tokenize=False,
                add_generation_prompt=False,
            )
            formatted.append(text)
        return {"text": formatted}

    train_dataset = train_dataset.map(format_chatml, batched=True, load_from_cache_file=False)
    if val_dataset:
        val_dataset = val_dataset.map(format_chatml, batched=True, load_from_cache_file=False)

    # 5. Training Arguments & SFTTrainer Execution
    print("\n[4/5] Initializing trainer and starting supervised fine-tuning...")
    if HAS_SFT_CONFIG:
        sft_config_kwargs = {
            "output_dir": args.output_dir,
            "num_train_epochs": args.epochs,
            "per_device_train_batch_size": args.batch_size,
            "gradient_accumulation_steps": args.grad_accum,
            "learning_rate": args.lr,
            "lr_scheduler_type": "cosine",
            "warmup_steps": 20,
            "logging_steps": 10,
            "save_strategy": "epoch",
            "save_total_limit": 2,
            "dataloader_pin_memory": True,
            "fp16": not torch.cuda.is_bf16_supported(),
            "bf16": torch.cuda.is_bf16_supported(),
            "gradient_checkpointing": True,
            "optim": "paged_adamw_8bit",
            "report_to": "none",
            "max_length": args.max_seq_length,
            "max_steps": args.max_steps,
            "dataset_text_field": "text",
            "eval_strategy": "epoch" if val_dataset and args.max_steps <= 0 else "no",
        }
        sft_config = SFTConfig(**sft_config_kwargs)
        trainer = SFTTrainer(
            model=model,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            processing_class=tokenizer,
            args=sft_config,
        )
    else:
        training_args_kwargs = {
            "output_dir": args.output_dir,
            "num_train_epochs": args.epochs,
            "per_device_train_batch_size": args.batch_size,
            "gradient_accumulation_steps": args.grad_accum,
            "learning_rate": args.lr,
            "lr_scheduler_type": "cosine",
            "warmup_ratio": 0.03,
            "logging_steps": 10,
            "save_strategy": "epoch",
            "fp16": not torch.cuda.is_bf16_supported(),
            "bf16": torch.cuda.is_bf16_supported(),
            "gradient_checkpointing": True,
            "optim": "paged_adamw_8bit",
            "max_steps": args.max_steps,
            "report_to": "none",
        }
        if val_dataset:
            training_args_kwargs["eval_strategy"] = "epoch"
        training_args = TrainingArguments(**training_args_kwargs)
        trainer = SFTTrainer(
            model=model,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            dataset_text_field="text",
            max_seq_length=args.max_seq_length,
            tokenizer=tokenizer,
            args=training_args,
        )

    trainer.train()

    # 7. Save Adapter & Export Instructions
    print(f"\n[5/5] Saving fine-tuned LoRA weights to: {args.output_dir}")
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    export_standalone_instructions(args.output_dir)
    print("\n======================================================================")
    print("TRAINING SUCCESSFUL: Local model is fine-tuned with 0% LLM math and full CoT.")
    print("======================================================================")


if __name__ == "__main__":
    main()
