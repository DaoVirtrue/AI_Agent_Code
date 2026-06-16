"""SentencePiece-based token encoder for Llama, Mistral, Qwen models."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class SentencePieceEncoder:
    """Token counting via sentencepiece for open-weight models.

    Models with publicly available sentencepiece tokenizers (e.g. Llama 3,
    Mistral, Qwen) are lazily loaded and cached.
    """

    SP_MODEL_MAP: dict[str, str] = {
        "llama-3": "meta-llama/Meta-Llama-3-8B",
        "llama-3-8b": "meta-llama/Meta-Llama-3-8B",
        "llama-3-70b": "meta-llama/Meta-Llama-3-70B",
        "llama-3.1-8b": "meta-llama/Llama-3.1-8B",
        "llama-3.1-70b": "meta-llama/Llama-3.1-70B",
        "llama-2-7b": "meta-llama/Llama-2-7b-hf",
        "llama-2-13b": "meta-llama/Llama-2-13b-hf",
        "llama-2-70b": "meta-llama/Llama-2-70b-hf",
        "mistral": "mistralai/Mistral-7B-v0.1",
        "mistral-7b": "mistralai/Mistral-7B-v0.1",
        "mistral-8x7b": "mistralai/Mixtral-8x7B-v0.1",
        "mistral-nemo": "mistralai/Mistral-Nemo-Instruct-2407",
        "qwen": "Qwen/Qwen-7B",
        "qwen-7b": "Qwen/Qwen-7B",
        "qwen-14b": "Qwen/Qwen-14B",
        "qwen-72b": "Qwen/Qwen-72B",
        "qwen-2-7b": "Qwen/Qwen2-7B",
        "yi-6b": "01-ai/Yi-6B",
        "yi-34b": "01-ai/Yi-34B",
        "deepseek": "deepseek-ai/deepseek-llm-7b-base",
        "deepseek-chat": "deepseek-ai/deepseek-llm-7b-base",
        "deepseek-reasoner": "deepseek-ai/deepseek-llm-7b-base",
    }

    def __init__(self) -> None:
        self._sp_cache: dict[str, Any] = {}
        self._model_map_lower: dict[str, str] = {
            k.lower(): v for k, v in self.SP_MODEL_MAP.items()
        }

    def _get_sp_model(self, model: str) -> Any:
        """Lazily load and cache sentencepiece model."""
        model_lower = model.lower()

        sp_model_id = self._model_map_lower.get(model_lower)
        if sp_model_id is None:
            for key, value in self._model_map_lower.items():
                if model_lower.startswith(key):
                    sp_model_id = value
                    break

        if sp_model_id is None:
            raise ValueError(
                f"No sentencepiece model mapping for '{model}'. "
                f"Supported: {list(self.SP_MODEL_MAP.keys())}"
            )

        if sp_model_id not in self._sp_cache:
            try:
                import sentencepiece as spm  # type: ignore[import-untyped]

                from huggingface_hub import hf_hub_download

                tokenizer_file = hf_hub_download(
                    repo_id=sp_model_id,
                    filename="tokenizer.model",
                )
                sp = spm.SentencePieceProcessor()
                sp.load(tokenizer_file)
                self._sp_cache[sp_model_id] = sp
            except Exception as exc:
                logger.error(
                    "Failed to load sentencepiece model '%s': %s",
                    sp_model_id,
                    exc,
                )
                raise RuntimeError(
                    f"Could not load sentencepiece model for {model}"
                ) from exc

        return self._sp_cache[sp_model_id]

    def count(self, text: str, model: str) -> int:
        """Count tokens for text using the model's sentencepiece tokenizer.

        Args:
            text: Input text to tokenize.
            model: Model identifier (e.g. "llama-3", "mistral", "qwen").

        Returns:
            Integer token count.
        """
        if not text:
            return 0
        sp = self._get_sp_model(model)
        return len(sp.encode(text))

    def count_messages(self, messages: list[dict[str, Any]], model: str) -> int:
        """Count tokens for a messages array.

        Uses the Llama/Mistral chat template convention for estimating
        token overhead around the content.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Model identifier.

        Returns:
            Total token count.
        """
        sp = self._get_sp_model(model)
        total = 0

        # BOS token
        total += 1

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, str):
                role_tokens = len(sp.encode(f"<|start_header_id|>{role}<|end_header_id|>"))
                content_tokens = len(sp.encode(content))
                eot_tokens = len(sp.encode("<|eot_id|>"))
                total += role_tokens + content_tokens + eot_tokens
            elif isinstance(content, list):
                role_tokens = len(sp.encode(f"<|start_header_id|>{role}<|end_header_id|>"))
                total += role_tokens
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        total += len(sp.encode(part.get("text", "")))
                    elif isinstance(part, str):
                        total += len(sp.encode(part))
                total += len(sp.encode("<|eot_id|>"))
            else:
                total += len(sp.encode(str(content)))

        # Generate-start token
        total += len(sp.encode("<|start_header_id|>assistant<|end_header_id|>"))

        return total

    def supports_model(self, model: str) -> bool:
        """Check whether this encoder has a mapping for the given model."""
        model_lower = model.lower()
        if model_lower in self._model_map_lower:
            return True
        return any(model_lower.startswith(key) for key in self._model_map_lower)
