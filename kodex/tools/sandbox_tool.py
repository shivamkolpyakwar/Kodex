"""
Kodex Sandbox Tool.

Wraps the DockerSandbox for use within the tool registry.
"""

from __future__ import annotations

import logging
from typing import Any

from kodex.sandbox.docker_sandbox import DockerSandbox
from kodex.tools.registry import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class SandboxTool(BaseTool):
    """Execute commands and tests in a secure Docker sandbox."""

    def __init__(self) -> None:
        """Initialize with a DockerSandbox instance."""
        self._sandbox = DockerSandbox()

    @property
    def name(self) -> str:
        return "sandbox_execute"

    @property
    def description(self) -> str:
        return "Execute commands or run tests in a secure Docker sandbox."

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a sandbox operation.

        Args:
            args: Must contain 'action' and 'repo_path'.
                Actions:
                - 'run_command': Execute a shell command.
                - 'run_tests': Run pytest.
                - 'run_linter': Run Ruff linter.
                - 'status': Get sandbox status.

        Returns:
            Dict with operation results.
        """
        action = args.get("action", "")
        repo_path = args.get("repo_path", ".")

        try:
            if action == "run_command":
                command = args.get("command", "")
                if not command:
                    raise ToolExecutionError(self.name, "No command provided")
                return self._sandbox.run_command(
                    command=command,
                    repo_path=repo_path,
                    timeout=args.get("timeout"),
                )

            elif action == "run_tests":
                return self._sandbox.run_tests(
                    repo_path=repo_path,
                    test_path=args.get("test_path"),
                    timeout=args.get("timeout"),
                )

            elif action == "run_linter":
                return self._sandbox.run_linter(
                    repo_path=repo_path,
                    file_path=args.get("file_path"),
                )

            elif action == "status":
                return self._sandbox.get_status()

            else:
                raise ToolExecutionError(
                    self.name,
                    f"Unknown action: {action}. Available: run_command, run_tests, run_linter, status",
                )

        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(self.name, str(e))
