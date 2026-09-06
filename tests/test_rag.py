"""
Tests for the Kodex RAG module.

Tests the code indexer, metadata extraction, and retriever logic.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from kodex.rag.indexer import CodeIndexer


class TestCodeIndexer:
    """Tests for the CodeIndexer."""

    def test_indexer_initialization(self) -> None:
        """Test indexer creates with default parameters."""
        indexer = CodeIndexer()
        assert indexer.chunk_size == 1024
        assert indexer.chunk_overlap == 128

    def test_indexer_custom_params(self) -> None:
        """Test indexer with custom chunk parameters."""
        indexer = CodeIndexer(chunk_size=512, chunk_overlap=64)
        assert indexer.chunk_size == 512
        assert indexer.chunk_overlap == 64

    def test_index_repository_with_python_files(self) -> None:
        """Test indexing a directory containing Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a sample Python file
            py_file = Path(tmpdir) / "sample.py"
            py_file.write_text(
                'import os\n\ndef hello():\n    """Say hello."""\n    print("hello")\n',
                encoding="utf-8",
            )

            indexer = CodeIndexer()
            docs = indexer.index_repository(tmpdir)

            assert len(docs) >= 1
            assert any("sample.py" in (d.metadata.get("file_name", "")) for d in docs)

    def test_index_repository_extracts_metadata(self) -> None:
        """Test that Python file metadata includes imports and functions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "example.py"
            py_file.write_text(
                "import json\nfrom pathlib import Path\n\n"
                "class MyClass:\n    pass\n\n"
                "def my_function():\n    pass\n",
                encoding="utf-8",
            )

            indexer = CodeIndexer()
            docs = indexer.index_repository(tmpdir)

            assert len(docs) >= 1
            doc = docs[0]

            assert "json" in doc.metadata.get("imports", [])
            assert "pathlib" in doc.metadata.get("imports", [])
            assert "MyClass" in doc.metadata.get("classes", [])
            assert "my_function" in doc.metadata.get("functions", [])

    def test_index_repository_skips_excluded_dirs(self) -> None:
        """Test that __pycache__ and similar dirs are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file in __pycache__
            cache_dir = Path(tmpdir) / "__pycache__"
            cache_dir.mkdir()
            cached = cache_dir / "module.cpython-310.pyc"
            cached.write_text("cached content", encoding="utf-8")

            # Create a normal file
            normal = Path(tmpdir) / "normal.py"
            normal.write_text("x = 1\n", encoding="utf-8")

            indexer = CodeIndexer()
            docs = indexer.index_repository(tmpdir)

            file_names = [d.metadata.get("file_name", "") for d in docs]
            assert "normal.py" in file_names
            assert "module.cpython-310.pyc" not in file_names

    def test_index_repository_skips_large_files(self) -> None:
        """Test that files exceeding max size are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            large_file = Path(tmpdir) / "large.py"
            # Create a file larger than default 500KB limit
            large_file.write_text("x = 1\n" * 200000, encoding="utf-8")

            indexer = CodeIndexer(max_file_size_kb=1)  # 1KB limit
            docs = indexer.index_repository(tmpdir)

            file_names = [d.metadata.get("file_name", "") for d in docs]
            assert "large.py" not in file_names

    def test_index_empty_directory(self) -> None:
        """Test indexing an empty directory returns no documents."""
        with tempfile.TemporaryDirectory() as tmpdir:
            indexer = CodeIndexer()
            docs = indexer.index_repository(tmpdir)
            assert len(docs) == 0

    def test_index_nonexistent_path(self) -> None:
        """Test indexing a non-existent path raises FileNotFoundError."""
        indexer = CodeIndexer()
        with pytest.raises(FileNotFoundError):
            indexer.index_repository("/nonexistent/path")

    def test_detect_language(self) -> None:
        """Test language detection from file extensions."""
        assert CodeIndexer._detect_language(".py") == "python"
        assert CodeIndexer._detect_language(".js") == "javascript"
        assert CodeIndexer._detect_language(".ts") == "typescript"
        assert CodeIndexer._detect_language(".go") == "go"
        assert CodeIndexer._detect_language(".rs") == "rust"
        assert CodeIndexer._detect_language(".xyz") == "text"

    def test_index_handles_syntax_errors(self) -> None:
        """Test that files with syntax errors are still indexed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad_syntax.py"
            bad_file.write_text("def broken(\n    # missing closing paren\n", encoding="utf-8")

            indexer = CodeIndexer()
            docs = indexer.index_repository(tmpdir)

            # Should still index the file, just without AST metadata
            assert len(docs) >= 1
