"""On-device local SLM inference engine powered by onnxruntime-genai.

Runs local on-device models with:
- Zero external network requests
- Zero API keys
- 100% private on-device generation
- Strict grounding via system directives and deterministic calculations
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../models/sme-finance-lora",
    )
)


class LocalSLMEngine:
    """Singleton runner for local ONNX Small Language Model."""

    _instance: Optional[LocalSLMEngine] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._model = None
        self._tokenizer = None
        self._load_attempted = False
        self._is_ready = False

    @classmethod
    def get_instance(cls) -> LocalSLMEngine:
        with cls._lock:
            if cls._instance is None:
                cls._instance = LocalSLMEngine()
            return cls._instance

    def is_available(self) -> bool:
        """Checks if model files are present on disk."""
        if not os.path.exists(MODEL_DIR):
            return False
        model_data = os.path.join(MODEL_DIR, "model.onnx.data")
        return os.path.exists(model_data) and os.path.getsize(model_data) > 100 * 1024 * 1024

    def _ensure_loaded(self) -> bool:
        if self._is_ready:
            return True
        if self._load_attempted and not self._is_ready:
            return False

        with self._lock:
            if self._is_ready:
                return True
            self._load_attempted = True

            if not self.is_available():
                logger.info("Local SLM weights not found at %s. Using deterministic fallback.", MODEL_DIR)
                return False

            try:
                import onnxruntime_genai as og

                logger.info("Loading local ONNX model from %s...", MODEL_DIR)
                self._model = og.Model(MODEL_DIR)
                self._tokenizer = og.Tokenizer(self._model)
                self._is_ready = True
                logger.info("Local ONNX model loaded successfully into memory.")
                return True
            except Exception as exc:
                logger.error("Failed to load local ONNX model: %s", exc)
                self._is_ready = False
                return False

    def generate(
        self,
        prompt: str,
        system_instruction: str,
        history: Optional[List[Any]] = None,
        max_new_tokens: int = 256,
        temperature: float = 0.2,
    ) -> Optional[str]:
        """Generates contextual natural response using local engine."""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return None
        if not self._ensure_loaded():
            return None

        try:
            import onnxruntime_genai as og

            messages: List[dict] = [{"role": "system", "content": system_instruction}]

            if history:
                for h in history[-4:]:
                    r = h.get("role", "") if isinstance(h, dict) else getattr(h, "role", "")
                    role = "assistant" if r == "agent" else "user"
                    txt = h.get("text", "") if isinstance(h, dict) else getattr(h, "text", "")
                    if txt:
                        messages.append({"role": role, "content": txt})

            messages.append({"role": "user", "content": prompt})

            # Format using model chat template
            json_messages = json.dumps(messages)
            formatted_prompt = self._tokenizer.apply_chat_template(
                json_messages, add_generation_prompt=True
            )

            input_tokens = self._tokenizer.encode(formatted_prompt)

            params = og.GeneratorParams(self._model)
            params.set_search_options(
                max_length=len(input_tokens) + max_new_tokens,
                temperature=temperature,
                top_p=0.9,
            )

            generator = og.Generator(self._model, params)
            generator.append_tokens(input_tokens)

            output_tokens = []
            while not generator.is_done():
                generator.generate_next_token()
                next_tokens = generator.get_next_tokens()
                if next_tokens:
                    output_tokens.append(next_tokens[0])

            generated_text = self._tokenizer.decode(output_tokens).strip()

            # Clean any trailing special tokens
            for stop_tok in ["<|im_end|>", "<|endoftext|>", "<|eot_id|>", "<|end_of_text|>", "</s>"]:
                if stop_tok in generated_text:
                    generated_text = generated_text.replace(stop_tok, "").strip()

            return generated_text if generated_text else None
        except Exception as exc:
            logger.warning("Local SLM generation error: %s", exc)
            return None


def generate_local_reply(
    prompt: str,
    system_instruction: str,
    history: Optional[List[Any]] = None,
    max_new_tokens: int = 512,
    temperature: float = 0.1,
    model_name: Optional[str] = None,
) -> Optional[str]:
    """Generates an offline response using the fine-tuned 3B LoRA adapter via the local engine."""
    from services.agent.local_transformers import LocalTransformersEngine
    trans_engine = LocalTransformersEngine.get_instance()

    target_model = model_name
    if trans_engine.is_available(target_model):
        return trans_engine.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            history=history,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            model_name=target_model,
        )

    engine = LocalSLMEngine.get_instance()
    if engine.is_available():
        return engine.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            history=history,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
        )
    return None
