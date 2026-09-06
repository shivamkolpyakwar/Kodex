"""
Kodex File Tool.

Provides file read, write, and diff operations.
"""

from __future__ import annotations

import difflib
import logging
import shutil
from pathlib import Path
from typing import Any

from kodex.tools.registry import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class FileTool(BaseTool):
    """Read, write, and diff file contents."""

    @property
    def name(self) -> str:
        return "file_operations"

    @property
    def description(self) -> str:
        return "Read, write, and generate diffs for source code files."

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a file operation.

        Args:
            args: Must contain 'action' and 'path'.
                Actions:
                - 'read': Read file contents.
                - 'write': Write content to file.
                - 'diff': Generate diff between two contents.
                - 'backup': Create a backup of a file.

        Returns:
            Dict with operation results.
        """
        action = args.get("action", "")

        actions = {
            "read": self._read,
            "write": self._write,
            "diff": self._diff,
            "backup": self._backup,
        }

        handler = actions.get(action)
        if not handler:
            raise ToolExecutionError(
                self.name,
                f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        return handler(args)

    def _read(self, args: dict[str, Any]) -> dict[str, Any]:
        """Read a file and return its contents with line numbers."""
        file_path = args.get("path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")

        path = Path(file_path)
        if not path.exists():
            raise ToolExecutionError(self.name, f"File not found: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
            lines = content.splitlines()
            total_lines = len(lines)

            # Apply line range if specified
            if start_line or end_line:
                s = (start_line or 1) - 1
                e = end_line or total_lines
                lines = lines[s:e]
                numbered = "\n".join(
                    f"{i + s + 1:4d} | {line}"
                    for i, line in enumerate(lines)
                )
            else:
                numbered = "\n".join(
                    f"{i + 1:4d} | {line}"
                    for i, line in enumerate(lines)
                )

            return {
                "content": content,
                "numbered": numbered,
                "total_lines": total_lines,
                "file_path": str(path),
            }

        except Exception as e:
            raise ToolExecutionError(self.name, f"Read failed: {str(e)}")

    def _write(self, args: dict[str, Any]) -> dict[str, Any]:
        """Write content to a file."""
        file_path = args.get("path", "")
        content = args.get("content", "")
        create_backup = args.get("backup", True)

        path = Path(file_path)

        try:
            # Create backup before writing
            if create_backup and path.exists():
                backup_path = path.with_suffix(path.suffix + ".bak")
                shutil.copy2(path, backup_path)
                logger.debug("  Backup created: %s", backup_path)

            # Ensure parent directory exists
            path.parent.mkdir(parents=True, exist_ok=True)

            path.write_text(content, encoding="utf-8")

            return {
                "written": True,
                "file_path": str(path),
                "bytes_written": len(content.encode("utf-8")),
            }

        except Exception as e:
            raise ToolExecutionError(self.name, f"Write failed: {str(e)}")

    def _diff(self, args: dict[str, Any]) -> dict[str, Any]:
        """Generate a unified diff between two contents."""
        original = args.get("original", "")
        modified = args.get("modified", "")
        file_path = args.get("path", "file")

        try:
            diff_lines = list(difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{file_path}",
                tofile=f"b/{file_path}",
            ))

            diff_text = "".join(diff_lines)

            # Count additions and deletions
            additions = sum(1 for l in diff_lines if l.startswith("+") and not l.startswith("+++"))
            deletions = sum(1 for l in diff_lines if l.startswith("-") and not l.startswith("---"))

            return {
                "diff": diff_text,
                "has_changes": bool(diff_text.strip()),
                "additions": additions,
                "deletions": deletions,
            }

        except Exception as e:
            raise ToolExecutionError(self.name, f"Diff failed: {str(e)}")

    def _backup(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a backup of a file."""
        file_path = args.get("path", "")
        path = Path(file_path)

        if not path.exists():
            raise ToolExecutionError(self.name, f"File not found: {file_path}")

        try:
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)

            return {
                "backed_up": True,
                "original": str(path),
                "backup": str(backup_path),
            }

        except Exception as e:
            raise ToolExecutionError(self.name, f"Backup failed: {str(e)}")
