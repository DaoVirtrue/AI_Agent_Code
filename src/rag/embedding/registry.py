"""Embedding model registry with provider abstraction."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingModelConfig:
    """Configuration for an embedding model."""
    name: str
    dim: int
    provider: str = "local"  # local, openai, cohere, voyage, jina
    model_path: str = ""
    supports_sparse: bool = False
    max_batch_size: int = 32
    max_seq_length: int = 512


class BaseEmbedder(ABC):
    """Abstract base for embedding model implementations."""

    def __init__(self, config: EmbeddingModelConfig):
        self.config = config

    @abstractmethod
    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts. Returns (n, dim) array."""
        ...

    @abstractmethod
    async def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query text. Returns (dim,) array."""
        ...

    @property
    def dim(self) -> int:
        return self.config.dim

    @property
    def name(self) -> str:
        return self.config.name


class LocalSentenceTransformer(BaseEmbedder):
    """Embedder using sentence-transformers (HuggingFace)."""

    def __init__(self, config: EmbeddingModelConfig):
        super().__init__(config)
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                config.model_path or config.name,
                trust_remote_code=True,
            )
            actual_dim = self._model.get_sentence_embedding_dimension()
            if actual_dim != config.dim:
                logger.info("Model %s actual dim=%d (config=%d)", config.name, actual_dim, config.dim)
                config.dim = actual_dim
            logger.info("Loaded SentenceTransformer: %s (dim=%d)", config.name, config.dim)
        except ImportError:
            logger.error("sentence-transformers not installed")
            self._model = None
        except Exception as e:
            logger.error("Failed to load model %s: %s", config.name, e)
            self._model = None

    async def embed(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            raise RuntimeError(f"Model {self.config.name} not loaded")
        import asyncio
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                texts,
                batch_size=self.config.max_batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
        )
        return np.array(embeddings)

    async def embed_query(self, query: str) -> np.ndarray:
        result = await self.embed([query])
        return result[0]


class OpenAIEmbedder(BaseEmbedder):
    """Embedder using OpenAI API."""

    def __init__(self, config: EmbeddingModelConfig):
        super().__init__(config)
        try:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI()
            logger.info("OpenAI embedder initialized: %s", config.name)
        except ImportError:
            logger.error("openai package not installed")
            self._client = None

    async def embed(self, texts: list[str]) -> np.ndarray:
        if self._client is None:
            raise RuntimeError("OpenAI client not initialized")
        response = await self._client.embeddings.create(
            model=self.config.name,
            input=texts,
        )
        embeddings = [item.embedding for item in response.data]
        return np.array(embeddings)

    async def embed_query(self, query: str) -> np.ndarray:
        result = await self.embed([query])
        return result[0]


class CohereEmbedder(BaseEmbedder):
    """Embedder using Cohere API."""

    def __init__(self, config: EmbeddingModelConfig):
        super().__init__(config)
        try:
            import cohere
            self._client = cohere.AsyncClient()
            logger.info("Cohere embedder initialized: %s", config.name)
        except ImportError:
            logger.error("cohere package not installed")
            self._client = None

    async def embed(self, texts: list[str]) -> np.ndarray:
        if self._client is None:
            raise RuntimeError("Cohere client not initialized")
        response = await self._client.embed(
            texts=texts,
            model=self.config.name,
            input_type="search_document",
        )
        return np.array(response.embeddings)

    async def embed_query(self, query: str) -> np.ndarray:
        if self._client is None:
            raise RuntimeError("Cohere client not initialized")
        response = await self._client.embed(
            texts=[query],
            model=self.config.name,
            input_type="search_query",
        )
        return np.array(response.embeddings[0])


class EmbeddingRegistry:
    """Registry of available embedding models with lazy loading."""

    MODELS: dict[str, EmbeddingModelConfig] = {
        "bge-m3": EmbeddingModelConfig(
            name="bge-m3",
            dim=1024,
            provider="local",
            model_path="BAAI/bge-m3",
            supports_sparse=True,
            max_batch_size=32,
            max_seq_length=8192,
        ),
        "bge-large-en-v1.5": EmbeddingModelConfig(
            name="bge-large-en-v1.5",
            dim=1024,
            provider="local",
            model_path="BAAI/bge-large-en-v1.5",
            max_batch_size=32,
            max_seq_length=512,
        ),
        "openai-text-3-small": EmbeddingModelConfig(
            name="text-embedding-3-small",
            dim=1536,
            provider="openai",
            max_batch_size=2048,
            max_seq_length=8191,
        ),
        "openai-text-3-large": EmbeddingModelConfig(
            name="text-embedding-3-large",
            dim=3072,
            provider="openai",
            max_batch_size=2048,
            max_seq_length=8191,
        ),
        "cohere-embed-v3": EmbeddingModelConfig(
            name="embed-english-v3.0",
            dim=1024,
            provider="cohere",
            max_batch_size=96,
            max_seq_length=512,
        ),
        "all-MiniLM-L6-v2": EmbeddingModelConfig(
            name="all-MiniLM-L6-v2",
            dim=384,
            provider="local",
            model_path="sentence-transformers/all-MiniLM-L6-v2",
            max_batch_size=64,
            max_seq_length=256,
        ),
        "e5-large-v2": EmbeddingModelConfig(
            name="e5-large-v2",
            dim=1024,
            provider="local",
            model_path="intfloat/e5-large-v2",
            max_batch_size=32,
            max_seq_length=512,
        ),
    }

    _PROVIDER_MAP = {
        "local": LocalSentenceTransformer,
        "openai": OpenAIEmbedder,
        "cohere": CohereEmbedder,
    }

    def __init__(self):
        self._instances: dict[str, BaseEmbedder] = {}
        logger.info("EmbeddingRegistry initialized with %d models", len(self.MODELS))

    def get_embedder(self, model_name: str) -> BaseEmbedder:
        """Get or create an embedder instance.

        Args:
            model_name: Key in MODELS dict (e.g., "bge-m3", "openai-text-3-small")

        Returns:
            BaseEmbedder instance

        Raises:
            ValueError: If model_name not found in registry
        """
        if model_name not in self.MODELS:
            available = list(self.MODELS.keys())
            raise ValueError(
                f"Unknown model: {model_name}. Available: {available}"
            )

        if model_name not in self._instances:
            config = self.MODELS[model_name]
            provider_class = self._PROVIDER_MAP.get(config.provider)
            if provider_class is None:
                raise ValueError(f"Unknown provider: {config.provider}")
            self._instances[model_name] = provider_class(config)

        return self._instances[model_name]

    def list_models(self) -> list[dict]:
        """List all registered models with their config."""
        return [
            {
                "name": name,
                "dim": cfg.dim,
                "provider": cfg.provider,
                "supports_sparse": cfg.supports_sparse,
                "max_batch_size": cfg.max_batch_size,
                "max_seq_length": cfg.max_seq_length,
            }
            for name, cfg in self.MODELS.items()
        ]

    def register_model(self, name: str, config: EmbeddingModelConfig) -> None:
        """Register a custom embedding model."""
        self.MODELS[name] = config
        logger.info("Registered custom model: %s (dim=%d, provider=%s)", name, config.dim, config.provider)

    def get_model_config(self, model_name: str) -> EmbeddingModelConfig:
        """Get the config for a model without instantiating it."""
        if model_name not in self.MODELS:
            raise ValueError(f"Unknown model: {model_name}")
        return self.MODELS[model_name]
