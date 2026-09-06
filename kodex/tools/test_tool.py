"""
Kodex Test Tool.

Runs pytest and parses results into structured format.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from kodex.tools.registry import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class TestTool(BaseTool):
    """Run pytest test suite and return structured results."""

    @property
    def name(self) -> str:
        return "run_tests"

    @property
    def description(self) -> str:
        return "Run pytest on a file or directory and return structured test results."

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute pytest.

        Args:
            args: Must contain 'path' (test file/directory).
                Optional: 'markers' (pytest markers to filter),
                         'verbose' (bool).

        Returns:
            Dict with pass/fail status, failures list, and output.
        """
        path = args.get("path", ".")
        markers = args.get("markers", "")
        verbose = args.get("verbose", False)
        timeout = args.get("timeout", 120)

        try:
            cmd = [
                "python", "-m", "pytest",
                path,
                "--tb=short",
                "--no-header",
                "-q",
                "--json-report",
                "--json-report-file=-",
            ]

            if markers:
                cmd.extend(["-m", markers])
            if verbose:
                cmd.append("-v")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            # Try to parse JSON report from stdout
            try:
                report = json.loads(result.stdout)
                summary = report.get("summary", {})
                tests = report.get("tests", [])

                failures = []
                for test in tests:
                    if test.get("outcome") == "failed":
                        call_info = test.get("call", {})
                        failures.append({
                            "nodeid": test.get("nodeid", ""),
                            "file": test.get("nodeid", "").split("::")[0],
                            "line": call_info.get("lineno", 0),
                            "message": call_info.get("longrepr", "")[:500],
                        })

                return {
                    "passed": result.returncode == 0,
                    "total": summary.get("total", 0),
                    "failures": failures,
                    "num_passed": summary.get("passed", 0),
                    "num_failed": summary.get("failed", 0),
                    "num_errors": summary.get("error", 0),
                    "duration": summary.get("duration", 0.0),
                    "output": result.stdout[:2000],
                }

            except json.JSONDecodeError:
                # Fallback: parse from exit code and stderr
                return {
                    "passed": result.returncode == 0,
                    "total": 0,
                    "failures": [],
                    "num_passed": 0,
                    "num_failed": 0 if result.returncode == 0 else 1,
                    "num_errors": 0,
                    "duration": 0.0,
                    "output": result.stdout + result.stderr,
                }

        except FileNotFoundError:
            raise ToolExecutionError(
                self.name,
                "pytest is not installed. Install with: pip install pytest",
            )
        except subprocess.TimeoutExpired:
            raise ToolExecutionError(
                self.name,
                f"Tests timed out after {timeout}s",
            )
        except Exception as e:
            raise ToolExecutionError(self.name, str(e))
