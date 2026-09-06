"""
Kodex Lint Tool.

Runs Ruff linter on Python files and returns structured results.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from kodex.tools.registry import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class LintTool(BaseTool):
    """Run Ruff linter to detect code quality issues."""

    @property
    def name(self) -> str:
        return "lint_code"

    @property
    def description(self) -> str:
        return "Run Ruff linter on a file or directory to detect code quality issues."

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute Ruff linting.

        Args:
            args: Must contain 'path' (file or directory to lint).
                Optional: 'fix' (bool) to auto-fix issues.

        Returns:
            Dict with 'errors' list and 'total' count.
        """
        path = args.get("path", ".")
        auto_fix = args.get("fix", False)

        try:
            cmd = ["ruff", "check", path, "--output-format=json"]

            if auto_fix:
                cmd.append("--fix")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Ruff returns exit code 1 when issues found (not an error)
            output = result.stdout.strip()

            if not output or output == "[]":
                return {"errors": [], "total": 0}

            try:
                raw_errors = json.loads(output)
            except json.JSONDecodeError:
                # Fallback: return raw output
                return {
                    "errors": [],
                    "total": 0,
                    "raw_output": output,
                    "stderr": result.stderr,
                }

            errors = []
            for err in raw_errors:
                location = err.get("location", {})
                errors.append({
                    "file": err.get("filename", ""),
                    "line": location.get("row", 0),
                    "column": location.get("column", 0),
                    "code": err.get("code", ""),
                    "message": err.get("message", ""),
                    "url": err.get("url", ""),
                    "fix_available": err.get("fix") is not None,
                })

            return {"errors": errors, "total": len(errors)}

        except FileNotFoundError:
            raise ToolExecutionError(
                self.name,
                "Ruff is not installed. Install with: pip install ruff",
            )
        except subprocess.TimeoutExpired:
            raise ToolExecutionError(self.name, "Linting timed out after 60s")
        except Exception as e:
            raise ToolExecutionError(self.name, str(e))
