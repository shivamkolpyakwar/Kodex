"""
Kodex Git Tool.

Manages Git operations: branch creation, commits, and PR descriptions.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import git
from git.exc import GitCommandError, InvalidGitRepositoryError

from kodex.tools.registry import BaseTool, ToolExecutionError

logger = logging.getLogger(__name__)


class GitTool(BaseTool):
    """Git integration for branch management and commits."""

    @property
    def name(self) -> str:
        return "git_operations"

    @property
    def description(self) -> str:
        return "Manage Git operations: create branches, commit changes, generate PR descriptions."

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a Git operation.

        Args:
            args: Must contain 'action' and 'repo_path'.
                Actions:
                - 'commit_fix': Create branch, stage, commit.
                - 'create_branch': Create a new branch.
                - 'get_status': Get repo status.
                - 'get_diff': Get working tree diff.

        Returns:
            Dict with operation results.
        """
        action = args.get("action", "")
        repo_path = args.get("repo_path", ".")

        try:
            repo = git.Repo(repo_path)
        except InvalidGitRepositoryError:
            raise ToolExecutionError(
                self.name,
                f"Not a Git repository: {repo_path}",
            )

        actions = {
            "commit_fix": self._commit_fix,
            "create_branch": self._create_branch,
            "get_status": self._get_status,
            "get_diff": self._get_diff,
        }

        handler = actions.get(action)
        if not handler:
            raise ToolExecutionError(
                self.name,
                f"Unknown action: {action}. Available: {list(actions.keys())}",
            )

        return handler(repo, args)

    def _commit_fix(self, repo: git.Repo, args: dict[str, Any]) -> dict[str, Any]:
        """Create a branch, stage changes, and commit."""
        branch_name = args.get("branch_name", "kodex/fix")
        file_path = args.get("file_path", "")
        commit_message = args.get("commit_message", "Fix by Kodex")
        pr_description = args.get("pr_description", "")

        try:
            # Stash any existing changes on the current branch
            original_branch = repo.active_branch.name

            # Create and checkout new branch
            if branch_name in [b.name for b in repo.branches]:
                # Branch exists — checkout it
                repo.git.checkout(branch_name)
                logger.info("  Checked out existing branch: %s", branch_name)
            else:
                new_branch = repo.create_head(branch_name)
                new_branch.checkout()
                logger.info("  Created branch: %s", branch_name)

            # Stage the fixed file
            if file_path:
                abs_path = Path(file_path)
                if abs_path.is_absolute():
                    rel_path = str(abs_path.relative_to(Path(repo.working_dir)))
                else:
                    rel_path = file_path
                repo.index.add([rel_path])
            else:
                repo.git.add(A=True)

            # Commit
            repo.index.commit(commit_message)
            logger.info("  Committed: %s", commit_message[:50])

            result: dict[str, Any] = {
                "branch": branch_name,
                "commit": str(repo.head.commit),
                "commit_message": commit_message,
                "pr_description": pr_description,
                "original_branch": original_branch,
            }

            # Try to push (may fail if no remote)
            try:
                repo.git.push("--set-upstream", "origin", branch_name)
                result["pushed"] = True
                logger.info("  Pushed to origin/%s", branch_name)
            except GitCommandError:
                result["pushed"] = False
                logger.info("  Push skipped (no remote or auth required)")

            return result

        except GitCommandError as e:
            raise ToolExecutionError(self.name, f"Git command failed: {str(e)}")

    def _create_branch(self, repo: git.Repo, args: dict[str, Any]) -> dict[str, Any]:
        """Create a new branch without committing."""
        branch_name = args.get("branch_name", "kodex/new-branch")

        try:
            if branch_name in [b.name for b in repo.branches]:
                return {"branch": branch_name, "created": False, "message": "Already exists"}

            new_branch = repo.create_head(branch_name)
            new_branch.checkout()

            return {"branch": branch_name, "created": True}

        except GitCommandError as e:
            raise ToolExecutionError(self.name, str(e))

    def _get_status(self, repo: git.Repo, args: dict[str, Any]) -> dict[str, Any]:
        """Get repository status."""
        return {
            "branch": repo.active_branch.name,
            "is_dirty": repo.is_dirty(),
            "untracked": repo.untracked_files,
            "modified": [d.a_path for d in repo.index.diff(None)],
            "staged": [d.a_path for d in repo.index.diff("HEAD")],
        }

    def _get_diff(self, repo: git.Repo, args: dict[str, Any]) -> dict[str, Any]:
        """Get the current working tree diff."""
        file_path = args.get("file_path")

        try:
            if file_path:
                diff = repo.git.diff(file_path)
            else:
                diff = repo.git.diff()

            return {"diff": diff, "has_changes": bool(diff.strip())}

        except GitCommandError as e:
            raise ToolExecutionError(self.name, str(e))
