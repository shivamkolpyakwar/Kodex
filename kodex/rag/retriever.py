"""
Kodex RAG Retriever.

Retrieves relevant multi-file context for a given error by querying
the vector store and tracing import dependencies.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class MultiFileRetriever:
    """
    Retrieves context across multiple files for error resolution.

    Strategy:
    1. Query the vector store with the error context.
    2. Identify the error file's imports from metadata.
    3. Retrieve additional chunks from imported modules.
    4. Rank all chunks by relevance and return top-K.
    """

    def __init__(self, index: Any, top_k: int = 8) -> None:
        """
        Initialize the retriever.

        Args:
            index: LlamaIndex VectorStoreIndex instance.
            top_k: Number of top chunks to return.
        """
        self._index = index
        self._top_k = top_k
        self._retriever = index.as_retriever(similarity_top_k=top_k)

    def retrieve(
        self,
        query: str,
        error_file: str | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieve relevant code chunks for an error.

        Args:
            query: Natural language description of the error.
            error_file: Path of the file containing the error.
            top_k: Override default top-K.

        Returns:
            List of context chunks with content, metadata, and scores.
        """
        k = top_k or self._top_k
        results: list[dict[str, Any]] = []

        try:
            # ─── Primary Retrieval: Query the vector store ──────────
            if top_k and top_k != self._top_k:
                retriever = self._index.as_retriever(similarity_top_k=k)
            else:
                retriever = self._retriever

            nodes = retriever.retrieve(query)

            for node in nodes:
                chunk = {
                    "content": node.get_content(),
                    "metadata": node.metadata if hasattr(node, "metadata") else {},
                    "score": node.get_score() if hasattr(node, "get_score") else 0.0,
                }
                results.append(chunk)

            logger.info(
                "  Primary retrieval: %d chunks (query: %s...)",
                len(results),
                query[:60],
            )

            # ─── Secondary Retrieval: Import-based context ──────────
            if error_file:
                imported_chunks = self._retrieve_import_context(
                    results, error_file, k // 2,
                )
                results.extend(imported_chunks)

        except Exception as e:
            logger.error("  Retrieval failed: %s", str(e))

        # ─── Deduplicate and Sort ───────────────────────────────────
        seen_content: set[str] = set()
        unique_results: list[dict[str, Any]] = []

        for chunk in sorted(results, key=lambda x: x.get("score", 0.0), reverse=True):
            content_hash = hash(chunk["content"][:200])
            if content_hash not in seen_content:
                seen_content.add(content_hash)
                unique_results.append(chunk)

        return unique_results[:k]

    def _retrieve_import_context(
        self,
        primary_results: list[dict[str, Any]],
        error_file: str,
        max_chunks: int,
    ) -> list[dict[str, Any]]:
        """
        Retrieve context from files imported by the error file.

        Looks at the metadata of primary results to find imports,
        then queries for those specific modules.
        """
        import_chunks: list[dict[str, Any]] = []

        # Find imports from the error file's metadata
        imports: list[str] = []
        for chunk in primary_results:
            meta = chunk.get("metadata", {})
            if meta.get("file_path", "").endswith(error_file.split("/")[-1]):
                imports = meta.get("imports", [])
                break

        if not imports:
            return []

        logger.info("  Tracing %d imports for cross-file context", len(imports))

        # Query for each imported module (limited)
        for module_name in imports[:5]:  # Limit to top 5 imports
            try:
                query = f"Module: {module_name}"
                retriever = self._index.as_retriever(similarity_top_k=2)
                nodes = retriever.retrieve(query)

                for node in nodes:
                    import_chunks.append({
                        "content": node.get_content(),
                        "metadata": {
                            **(node.metadata if hasattr(node, "metadata") else {}),
                            "source": "import_trace",
                            "imported_by": error_file,
                        },
                        "score": (node.get_score() if hasattr(node, "get_score") else 0.0) * 0.8,
                    })

            except Exception as e:
                logger.debug("  Import trace failed for %s: %s", module_name, str(e))

        return import_chunks[:max_chunks]
