"""
Kodex Docker Sandbox.

Manages ephemeral Docker containers for safe code execution,
linting, and testing. Implements defense-in-depth security.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import docker
from docker.errors import (
    APIError,
    ContainerError,
    DockerException,
    ImageNotFound,
    NotFound,
)

from kodex.config import get_settings

logger = logging.getLogger(__name__)


class DockerSandbox:
    """
    Secure Docker sandbox for running untrusted code.

    Security features:
    - No network access (network_mode=none)
    - Memory and CPU limits
    - Read-only root filesystem with /tmp tmpfs
    - Non-root user execution
    - Auto-removal of containers
    - Configurable timeout
    """

    def __init__(self) -> None:
        """Initialize the Docker client."""
        self._settings = get_settings()
        self._client: docker.DockerClient | None = None
        self._image_name = self._settings.sandbox_image
        self._available = False

        self._connect()

    def _connect(self) -> None:
        """Connect to the Docker daemon."""
        try:
            self._client = docker.from_env()
            self._client.ping()
            self._available = True
            logger.info("✅ Docker daemon connected")
        except DockerException as e:
            logger.warning(
                "⚠️  Docker not available: %s. Sandbox will use local fallback.",
                str(e),
            )
            self._available = False

    @property
    def is_available(self) -> bool:
        """Check if Docker is available."""
        return self._available

    def ensure_image(self) -> bool:
        """
        Ensure the sandbox Docker image exists.

        Returns:
            True if image is ready, False otherwise.
        """
        if not self._available or not self._client:
            return False

        try:
            self._client.images.get(self._image_name)
            logger.info("✅ Sandbox image ready: %s", self._image_name)
            return True
        except ImageNotFound:
            logger.warning(
                "⚠️  Sandbox image '%s' not found. "
                "Build it with: docker-compose build sandbox",
                self._image_name,
            )
            return False
        except APIError as e:
            logger.error("Docker API error: %s", str(e))
            return False

    def run_command(
        self,
        command: str,
        repo_path: str,
        timeout: int | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Run a command inside a sandboxed Docker container.

        Args:
            command: Shell command to execute.
            repo_path: Host path to mount as /workspace.
            timeout: Override default timeout (seconds).
            env_vars: Additional environment variables.

        Returns:
            Dict with exit_code, stdout, stderr, duration.
        """
        effective_timeout = timeout or self._settings.sandbox_timeout

        # ─── Fallback: Local Execution ──────────────────────────────
        if not self._available or not self._client:
            return self._run_local_fallback(command, repo_path, effective_timeout)

        # ─── Docker Execution ───────────────────────────────────────
        import time
        start = time.time()

        try:
            container = self._client.containers.run(
                image=self._image_name,
                command=["sh", "-c", command],
                volumes={
                    str(Path(repo_path).resolve()): {
                        "bind": "/workspace",
                        "mode": "ro",  # Read-only mount
                    },
                },
                working_dir="/workspace",
                network_mode="none",
                mem_limit=self._settings.sandbox_memory_limit,
                cpu_period=100000,
                cpu_quota=self._settings.sandbox_cpu_quota,
                read_only=True,
                tmpfs={"/tmp": ""},
                user="sandbox",
                environment=env_vars or {},
                remove=True,
                detach=False,
                stdout=True,
                stderr=True,
                timeout=effective_timeout,
            )

            duration = time.time() - start

            # container.run with detach=False returns bytes
            output = container.decode("utf-8") if isinstance(container, bytes) else str(container)

            return {
                "exit_code": 0,
                "stdout": output,
                "stderr": "",
                "duration": duration,
                "sandbox": "docker",
            }

        except ContainerError as e:
            duration = time.time() - start
            stderr = e.stderr.decode("utf-8") if e.stderr else str(e)
            return {
                "exit_code": e.exit_status,
                "stdout": "",
                "stderr": stderr,
                "duration": duration,
                "sandbox": "docker",
            }

        except APIError as e:
            logger.error("Docker API error during execution: %s", str(e))
            return self._run_local_fallback(command, repo_path, effective_timeout)

        except Exception as e:
            logger.error("Unexpected sandbox error: %s", str(e))
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": time.time() - start,
                "sandbox": "docker",
            }

    def run_tests(
        self,
        repo_path: str,
        test_path: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """
        Run pytest inside the sandbox and parse results.

        Args:
            repo_path: Path to the repository.
            test_path: Specific test file/directory (optional).
            timeout: Override timeout.

        Returns:
            Structured test results.
        """
        test_target = test_path or "."
        command = (
            f"python -m pytest {test_target} "
            f"--tb=short --no-header -q "
            f"--json-report --json-report-file=/tmp/test_report.json "
            f"2>&1; cat /tmp/test_report.json 2>/dev/null || echo '{{}}'"
        )

        result = self.run_command(command, repo_path, timeout)

        # Parse JSON test report
        try:
            # Try to find JSON report in output
            output = result.get("stdout", "") + result.get("stderr", "")
            json_start = output.rfind("{")
            if json_start >= 0:
                json_str = output[json_start:]
                report = json.loads(json_str)

                summary = report.get("summary", {})
                tests = report.get("tests", [])

                return {
                    "passed": summary.get("failed", 0) == 0 and summary.get("error", 0) == 0,
                    "total": summary.get("total", 0),
                    "failures": summary.get("failed", 0),
                    "errors": summary.get("error", 0),
                    "duration": summary.get("duration", 0.0),
                    "output": output[:2000],
                    "failed_tests": [
                        t.get("nodeid", "") for t in tests
                        if t.get("outcome") == "failed"
                    ],
                }
        except (json.JSONDecodeError, IndexError, KeyError):
            pass

        # Fallback: parse exit code
        return {
            "passed": result.get("exit_code", 1) == 0,
            "total": 0,
            "failures": 0 if result.get("exit_code", 1) == 0 else 1,
            "errors": 0,
            "duration": result.get("duration", 0.0),
            "output": result.get("stdout", "") + result.get("stderr", ""),
            "failed_tests": [],
        }

    def run_linter(
        self,
        repo_path: str,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """
        Run Ruff linter inside the sandbox.

        Args:
            repo_path: Path to the repository.
            file_path: Specific file to lint (optional).

        Returns:
            Structured lint results.
        """
        target = file_path or "."
        command = f"ruff check {target} --output-format=json 2>/dev/null || true"

        result = self.run_command(command, repo_path)

        try:
            output = result.get("stdout", "")
            if output.strip().startswith("["):
                errors = json.loads(output)
                return {
                    "errors": [
                        {
                            "file": e.get("filename", ""),
                            "line": e.get("location", {}).get("row", 0),
                            "column": e.get("location", {}).get("column", 0),
                            "code": e.get("code", ""),
                            "message": e.get("message", ""),
                        }
                        for e in errors
                    ],
                    "total": len(errors),
                }
        except (json.JSONDecodeError, KeyError):
            pass

        return {"errors": [], "total": 0, "raw_output": result.get("stdout", "")}

    def _run_local_fallback(
        self,
        command: str,
        working_dir: str,
        timeout: int,
    ) -> dict[str, Any]:
        """
        Fallback: run command locally when Docker is unavailable.

        WARNING: This is less secure. Only use for development.
        """
        import subprocess
        import time

        logger.warning("⚠️  Using local fallback (Docker unavailable)")
        start = time.time()

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=working_dir,
            )

            duration = time.time() - start
            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "duration": duration,
                "sandbox": "local_fallback",
            }

        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout}s",
                "duration": time.time() - start,
                "sandbox": "local_fallback",
            }

        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": time.time() - start,
                "sandbox": "local_fallback",
            }

    def cleanup(self) -> None:
        """Clean up any lingering sandbox containers."""
        if not self._available or not self._client:
            return

        try:
            containers = self._client.containers.list(
                filters={"ancestor": self._image_name},
            )
            for container in containers:
                try:
                    container.kill()
                    container.remove(force=True)
                    logger.info("  Cleaned up container: %s", container.short_id)
                except NotFound:
                    pass
        except Exception as e:
            logger.warning("Cleanup error: %s", str(e))

    def get_status(self) -> dict[str, Any]:
        """Get the current status of the sandbox system."""
        status: dict[str, Any] = {
            "docker_available": self._available,
            "image_name": self._image_name,
            "image_ready": False,
            "config": {
                "timeout": self._settings.sandbox_timeout,
                "memory_limit": self._settings.sandbox_memory_limit,
                "cpu_quota": self._settings.sandbox_cpu_quota,
            },
        }

        if self._available:
            status["image_ready"] = self.ensure_image()

        return status
