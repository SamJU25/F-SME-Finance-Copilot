"""SME Finance Copilot — Google Colab Cloud Training Script.

Engineered to run on a free Google Colab NVIDIA T4 GPU (16GB VRAM) with:
- Zero laptop heat or power draw
- 4-Bit NF4 Quantization (BitsAndBytes)
- LoRA Rank 16 on all linear attention/MLP projections
- Automatic packaging of the trained weights into 'sme-finance-lora.zip' (~85 MB)
"""

import os
import shutil
import sys
import torch

try:
    from google.colab import files
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer


def run_colab_training(
    model_id: str = "Qwen/Qwen2.5-3B-Instruct",
    train_file: str = "finetune_train.jsonl",
    val_file: str = "finetune_val.jsonl",
    output_dir: str = "sme-finance-lora",
    epochs: int = 1,
    batch_size: int = 2,
    grad_accum: int = 8,
    max_length: int = 1024,
):
    import os, signal, gc
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        free_gb = torch.cuda.mem_get_info()[0] / (1024**3)
        if free_gb < 10.0:
            print(f"[RESET] Dirty GPU memory ({free_gb:.2f} GB free). Killing process to force clean restart...")
            os.kill(os.getpid(), signal.SIGKILL)

    print("=" * 70)
    print("SME Finance Copilot — Google Colab QLoRA Training Pipeline")
    print(f"CUDA Device:      {torch.cuda.get_device_name(0)}")
    print(f"CUDA Memory:      {round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)} GB VRAM")
    print(f"Base Model:       {model_id}")
    print(f"Training Dataset: {train_file}")
    print("=" * 70)

    if not os.path.exists(train_file):
        raise FileNotFoundError(f"Training file '{train_file}' not found. Did you unzip colab_dataset.zip?")

    # 1. 4-Bit NormalFloat4 Configuration
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )

    # 2. Tokenizer and 4-Bit Base Model pinned to GPU 0
    print("\n[1/5] Loading tokenizer and base model in 4-bit...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        quantization_config=bnb_config,
        torch_dtype=torch.float16,
        device_map={"": 0},
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()
    model.config.use_cache = False

    # 3. LoRA Configuration on All Linear Projections
    print("\n[2/5] Attaching LoRA adapters to all attention and MLP projections...")
    peft_config = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Load ChatML Dataset
    print("\n[3/5] Loading and formatting ChatML conversations...")
    train_dataset = load_dataset("json", data_files=train_file, split="train")

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

    # 5. SFTTrainer Execution
    print("\n[4/5] Starting supervised fine-tuning...")
    sft_config = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=grad_accum,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_steps=20,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=2,
        dataloader_pin_memory=True,
        fp16=False,
        bf16=False,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to="none",
        max_length=max_length,
        dataset_text_field="text",
        eval_strategy="no",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        processing_class=tokenizer,
        args=sft_config,
    )

    trainer.train()

    # 6. Save LoRA Adapter
    print(f"\n[5/5] Saving fine-tuned LoRA weights to: {output_dir}")
    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # 7. Package and Download
    zip_path = "sme-finance-lora"
    shutil.make_archive(zip_path, "zip", output_dir)
    print(f"\n[OK] Adapter packaged into '{zip_path}.zip' (~85 MB)!")

    if IN_COLAB:
        print("Initiating automatic download to your browser...")
        files.download(f"{zip_path}.zip")
        print("Download started! Once downloaded, extract it to 'models/sme-finance-lora' on your laptop.")
    else:
        print(f"Weights ready at {zip_path}.zip")


if __name__ == "__main__":
    run_colab_training()
