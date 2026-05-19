"""Embedding interface and implementations for AI indexing.

Provides:
- Embedder Protocol: Abstract interface for embedding models
- OpenAIEmbedder: Implementation using OpenAI's text-embedding API
- get_embed_api_key: Fallback logic for API key resolution
"""
from typing import Protocol
from functools import lru_cache

import structlog
from openai import AsyncOpenAI

from app.config import Settings, get_settings

logger = structlog.get_logger(__name__)


class Embedder(Protocol):
    """Protocol for embedding models.
    
    Implementations must provide:
    - dim: int — embedding dimension (e.g., 1536 for text-embedding-3-small)
    - embed: async method that takes list of texts and returns list of vectors
    """

    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.
        
        Args:
            texts: List of text strings to embed
            
        Returns:
            List of embedding vectors (each vector is list[float] of length self.dim)
        """
        ...


class OpenAIEmbedder:
    """OpenAI embedding implementation using text-embedding-3-small (or configured model).
    
    Attributes:
        dim: Embedding dimension from settings.EMBED_DIM
        client: AsyncOpenAI client configured with EMBED_BASE_URL and API key
        model: Model name from settings.EMBED_MODEL
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize OpenAI embedder with settings.
        
        Args:
            settings: Application settings containing EMBED_* configuration
        """
        self.dim = settings.EMBED_DIM
        self.model = settings.EMBED_MODEL
        
        api_key = get_embed_api_key(settings)
        self.client = AsyncOpenAI(
            base_url=settings.EMBED_BASE_URL,
            api_key=api_key,
        )
        
        logger.info(
            "embedder.initialized",
            model=self.model,
            dim=self.dim,
            base_url=settings.EMBED_BASE_URL,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via OpenAI API.
        
        Args:
            texts: List of text strings to embed (max 2048 per batch recommended)
            
        Returns:
            List of embedding vectors in same order as input texts
            
        Raises:
            openai.OpenAIError: If API call fails
        """
        if not texts:
            return []
        
        logger.debug("embedder.embed.start", count=len(texts))
        
        response = await self.client.embeddings.create(
            model=self.model,
            input=texts,
            encoding_format="float",
        )
        
        # Extract embeddings in order (response.data is sorted by index)
        embeddings = [item.embedding for item in response.data]
        
        logger.debug(
            "embedder.embed.complete",
            count=len(embeddings),
            tokens=response.usage.total_tokens,
        )
        
        return embeddings


def get_embed_api_key(settings: Settings) -> str:
    """Get embedding API key with fallback to LLM API key.
    
    Per D1 in CONFIRMED-DECISIONS.md:
    - If EMBED_API_KEY is empty string, fallback to LLM_API_KEY
    - This allows using same API key for both LLM and embeddings
    
    Args:
        settings: Application settings
        
    Returns:
        API key to use for embedding requests
    """
    embed_key = settings.EMBED_API_KEY.get_secret_value()
    if embed_key:
        return embed_key
    
    # Fallback to LLM API key
    llm_key = settings.LLM_API_KEY.get_secret_value()
    logger.debug("embedder.api_key.fallback", source="LLM_API_KEY")
    return llm_key


@lru_cache(maxsize=1)
def get_embedder() -> OpenAIEmbedder:
    """Get cached embedder instance.
    
    Returns:
        Singleton OpenAIEmbedder instance
    """
    settings = get_settings()
    return OpenAIEmbedder(settings)
