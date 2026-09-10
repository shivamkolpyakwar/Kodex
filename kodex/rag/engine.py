"""
Kodex RAG Engine.

High-level orchestrator that ties together LlamaIndex, Qdrant,
and the indexer/retriever for code-aware RAG.
"""

from __future__ import annotations

import logging
from typing import Any

import qdrant_client
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

from kodex.config import get_settings
from kodex.rag.indexer import CodeIndexer
from kodex.rag.retriever import MultiFileRetriever

logger = logging.getLogger(__name__)


class RAGEngine:
    """
    Main RAG engine for code-aware retrieval.

    Manages the lifecycle of the vector store, handles indexing
    new repositories, and provides a query interface.
    """

    def __init__(self) -> None:
        """Initialize the RAG engine with Qdrant and LlamaIndex."""
        self._settings = get_settings()
        self._client: qdrant_client.QdrantClient | None = None
        self._index: VectorStoreIndex | None = None
        self._retriever: MultiFileRetriever | None = None
        self._indexer = CodeIndexer()

        self._connect()

    def _connect(self) -> None:
        """Establish connection to Qdrant."""
        try:
            if self._settings.qdrant_url.startswith("http"):
                self._client = qdrant_client.QdrantClient(
                    url=self._settings.qdrant_url,
                    api_key=self._settings.qdrant_api_key or None,
                    timeout=30,
                )
            else:
                # Local file-based storage as fallback
                self._client = qdrant_client.QdrantClient(
                    path=self._settings.qdrant_url,
                )

            logger.info("✅ Connected to Qdrant at %s", self._settings.qdrant_url)

        except Exception as e:
            logger.warning(
                "⚠️  Qdrant connection failed: %s. Using in-memory mode.",
                str(e),
            )
            self._client = qdrant_client.QdrantClient(location=":memory:")

        # Initialize the vector store and index
        self._init_index()

    def _get_embed_model(self) -> Any:
        """Get embedding model (OpenAI, FastEmbed, HuggingFace, or Mock fallback)."""
        if self._settings.openai_api_key:
            return OpenAIEmbedding(
                model_name=self._settings.openai_embedding_model,
                api_key=self._settings.openai_api_key,
            )
        try:
            from llama_index.embeddings.fastembed import FastEmbedEmbedding

            logger.info("ℹ️  Using FastEmbed (local free embeddings)")
            return FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")
        except Exception:
            try:
                from llama_index.embeddings.huggingface import HuggingFaceEmbedding

                return HuggingFaceEmbedding(model_name="BAAI/bge-small-en-v1.5")
            except Exception:
                from llama_index.core.embeddings import MockEmbedding

                logger.warning("⚠️  No embedding model available. Using MockEmbedding.")
                return MockEmbedding(embed_dim=384)

    def _init_index(self) -> None:
        """Initialize the LlamaIndex vector store index."""
        try:
            vector_store = QdrantVectorStore(
                client=self._client,
                collection_name=self._settings.qdrant_collection_name,
            )

            embed_model = self._get_embed_model()

            # Try to load existing index
            self._index = VectorStoreIndex.from_vector_store(
                vector_store=vector_store,
                embed_model=embed_model,
            )

            self._retriever = MultiFileRetriever(self._index)

            logger.info("✅ VectorStoreIndex initialized")

        except Exception as e:
            logger.error("❌ Failed to initialize index: %s", str(e))
            raise

    def index_repository(self, repo_path: str) -> dict[str, Any]:
        """
        Index a code repository into the vector store.

        Args:
            repo_path: Absolute path to the repository.

        Returns:
            Dict with indexing statistics.
        """
        logger.info("📁 Indexing repository: %s", repo_path)

        try:
            # Create documents from the repository
            documents = self._indexer.index_repository(repo_path)

            if not documents:
                logger.warning("  No documents found to index")
                return {"indexed": 0, "status": "empty"}

            # Build the index from documents
            embed_model = self._get_embed_model()

            vector_store = QdrantVectorStore(
                client=self._client,
                collection_name=self._settings.qdrant_collection_name,
            )
            storage_context = StorageContext.from_defaults(
                vector_store=vector_store,
            )

            self._index = VectorStoreIndex.from_documents(
                documents,
                storage_context=storage_context,
                embed_model=embed_model,
                show_progress=True,
            )

            self._retriever = MultiFileRetriever(self._index)

            stats = {
                "indexed": len(documents),
                "status": "success",
                "collection": self._settings.qdrant_collection_name,
            }
            logger.info("✅ Indexed %d documents", len(documents))
            return stats

        except Exception as e:
            logger.error("❌ Indexing failed: %s", str(e))
            return {"indexed": 0, "status": "error", "error": str(e)}

    def query(
        self,
        query: str,
        top_k: int = 8,
        error_file: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query the indexed codebase for relevant context.

        Args:
            query: Natural language query about the code.
            top_k: Number of results to return.
            error_file: Optional path of the file with the error.

        Returns:
            List of relevant code chunks with metadata.
        """
        if not self._retriever:
            logger.warning("⚠️  No retriever available — index a repository first")
            return []

        try:
            results = self._retriever.retrieve(
                query=query,
                error_file=error_file,
                top_k=top_k,
            )
            return results

        except Exception as e:
            logger.error("❌ Query failed: %s", str(e))
            return []

    def get_collection_info(self) -> dict[str, Any]:
        """Get information about the current Qdrant collection."""
        try:
            if self._client:
                info = self._client.get_collection(
                    self._settings.qdrant_collection_name,
                )
                return {
                    "name": self._settings.qdrant_collection_name,
                    "vectors_count": info.vectors_count,
                    "points_count": info.points_count,
                    "status": info.status.value if info.status else "unknown",
                }
        except Exception:
            pass

        return {"name": self._settings.qdrant_collection_name, "status": "not_found"}

    def clear_collection(self) -> bool:
        """Delete and recreate the collection."""
        try:
            if self._client:
                self._client.delete_collection(
                    self._settings.qdrant_collection_name,
                )
                logger.info("🗑️  Collection cleared: %s", self._settings.qdrant_collection_name)
                self._init_index()
                return True
        except Exception as e:
            logger.error("Failed to clear collection: %s", str(e))
        return False
