"""
Kodex RAG Indexer.

Walks a repository, parses source files into semantically meaningful
chunks using AST-aware splitting, and upserts them into Qdrant.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

from llama_index.core import Document
from llama_index.core.node_parser import CodeSplitter, SentenceSplitter

from kodex.config import EXCLUDED_DIRS, EXCLUDED_FILES, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


class CodeIndexer:
    """
    Indexes a code repository into document chunks for RAG retrieval.

    Walks the file tree, reads source files, extracts metadata
    (imports, classes, functions), and splits into chunks suitable
    for embedding.
    """

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
        max_file_size_kb: int = 500,
    ) -> None:
        """
        Initialize the indexer.

        Args:
            chunk_size: Target chunk size in characters.
            chunk_overlap: Overlap between consecutive chunks.
            max_file_size_kb: Skip files larger than this (KB).
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_size_kb = max_file_size_kb

        # Use CodeSplitter for Python, SentenceSplitter for others
        self._python_splitter = CodeSplitter(
            language="python",
            chunk_lines=40,
            chunk_lines_overlap=5,
            max_chars=chunk_size,
        )
        self._default_splitter = SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def index_repository(self, repo_path: str) -> list[Document]:
        """
        Walk the repository and create LlamaIndex Documents.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            List of Document objects ready for embedding.
        """
        repo = Path(repo_path).resolve()
        if not repo.is_dir():
            raise FileNotFoundError(f"Repository path not found: {repo}")

        documents: list[Document] = []
        file_count = 0
        skip_count = 0

        logger.info("📁 Indexing repository: %s", repo)

        for root, dirs, files in os.walk(repo):
            # Filter excluded directories (in-place to prevent os.walk descent)
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]

            for filename in files:
                file_path = Path(root) / filename

                # Skip excluded files
                if filename in EXCLUDED_FILES:
                    continue

                # Skip unsupported extensions
                if file_path.suffix not in SUPPORTED_EXTENSIONS:
                    continue

                # Skip large files
                try:
                    size_kb = file_path.stat().st_size / 1024
                    if size_kb > self.max_file_size_kb:
                        skip_count += 1
                        logger.debug("  Skipping large file: %s (%.0f KB)", filename, size_kb)
                        continue
                except OSError:
                    continue

                # Read and create document
                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                    if not content.strip():
                        continue

                    # Extract metadata
                    metadata = self._extract_metadata(file_path, content, repo)

                    doc = Document(
                        text=content,
                        metadata=metadata,
                        doc_id=str(file_path.relative_to(repo)),
                    )
                    documents.append(doc)
                    file_count += 1

                except Exception as e:
                    logger.warning("  Failed to read %s: %s", filename, str(e))
                    skip_count += 1

        logger.info(
            "  Indexed %d files, skipped %d",
            file_count, skip_count,
        )

        return documents

    def _extract_metadata(
        self,
        file_path: Path,
        content: str,
        repo_root: Path,
    ) -> dict[str, Any]:
        """
        Extract metadata from a source file.

        For Python files, parses the AST to extract imports,
        class names, and function names.
        """
        relative_path = str(file_path.relative_to(repo_root))
        metadata: dict[str, Any] = {
            "file_path": relative_path,
            "file_name": file_path.name,
            "extension": file_path.suffix,
            "language": self._detect_language(file_path.suffix),
        }

        # Python-specific AST analysis
        if file_path.suffix == ".py":
            try:
                tree = ast.parse(content)
                metadata["imports"] = self._extract_imports(tree)
                metadata["classes"] = [
                    node.name for node in ast.walk(tree)
                    if isinstance(node, ast.ClassDef)
                ]
                metadata["functions"] = [
                    node.name for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                    or isinstance(node, ast.AsyncFunctionDef)
                ]
            except SyntaxError:
                logger.debug("  AST parse failed for %s (syntax error)", file_path.name)
                metadata["imports"] = []
                metadata["classes"] = []
                metadata["functions"] = []

        return metadata

    @staticmethod
    def _extract_imports(tree: ast.Module) -> list[str]:
        """Extract import module names from an AST."""
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    @staticmethod
    def _detect_language(extension: str) -> str:
        """Map file extension to language name."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".rb": "ruby",
            ".php": "php",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".json": "json",
            ".md": "markdown",
        }
        return ext_map.get(extension, "text")

    def get_splitter_for_language(self, language: str) -> Any:
        """Return the appropriate splitter for a language."""
        if language == "python":
            return self._python_splitter
        return self._default_splitter
