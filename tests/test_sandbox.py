"""
Tests for the Kodex Sandbox module.

Tests Docker sandbox initialization, status checking,
and local fallback behavior.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from kodex.sandbox.docker_sandbox import DockerSandbox


class TestDockerSandbox:
    """Tests for the DockerSandbox."""

    def test_sandbox_initialization(self) -> None:
        """Test that sandbox initializes without crashing."""
        sandbox = DockerSandbox()
        # Should not raise, even if Docker is not available
        assert isinstance(sandbox.is_available, bool)

    def test_get_status(self) -> None:
        """Test getting sandbox status."""
        sandbox = DockerSandbox()
        status = sandbox.get_status()

        assert "docker_available" in status
        assert "image_name" in status
        assert "config" in status
        assert "timeout" in status["config"]
        assert "memory_limit" in status["config"]

    def test_local_fallback_echo(self) -> None:
        """Test local fallback execution with echo command."""
        sandbox = DockerSandbox()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = sandbox._run_local_fallback(
                command="echo hello_sandbox",
                working_dir=tmpdir,
                timeout=10,
            )

            assert result["exit_code"] == 0
            assert "hello_sandbox" in result["stdout"]
            assert result["sandbox"] == "local_fallback"

    def test_local_fallback_timeout(self) -> None:
        """Test local fallback handles timeout."""
        sandbox = DockerSandbox()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = sandbox._run_local_fallback(
                command="sleep 30",
                working_dir=tmpdir,
                timeout=1,
            )

            assert result["exit_code"] == -1
            assert "timed out" in result["stderr"].lower()

    def test_local_fallback_failing_command(self) -> None:
        """Test local fallback with a failing command."""
        sandbox = DockerSandbox()

        with tempfile.TemporaryDirectory() as tmpdir:
            result = sandbox._run_local_fallback(
                command="exit 1",
                working_dir=tmpdir,
                timeout=10,
            )

            assert result["exit_code"] == 1

    def test_run_command_uses_fallback_when_docker_unavailable(self) -> None:
        """Test that run_command falls back when Docker is not available."""
        sandbox = DockerSandbox()

        # Force Docker unavailable
        sandbox._available = False

        with tempfile.TemporaryDirectory() as tmpdir:
            result = sandbox.run_command(
                command="echo fallback_test",
                repo_path=tmpdir,
                timeout=10,
            )

            assert result["sandbox"] == "local_fallback"
            assert "fallback_test" in result["stdout"]

    def test_run_tests_parses_exit_code(self) -> None:
        """Test that run_tests interprets exit codes correctly."""
        sandbox = DockerSandbox()
        sandbox._available = False  # Force local fallback

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple passing test
            test_file = Path(tmpdir) / "test_simple.py"
            test_file.write_text(
                "def test_passing():\n    assert True\n",
                encoding="utf-8",
            )

            result = sandbox.run_tests(
                repo_path=tmpdir,
                test_path="test_simple.py",
                timeout=30,
            )

            # Result should be structured
            assert "passed" in result
            assert "output" in result

    def test_cleanup_doesnt_crash(self) -> None:
        """Test that cleanup doesn't crash even without Docker."""
        sandbox = DockerSandbox()
        sandbox._available = False
        sandbox.cleanup()  # Should not raise
