"""
Kodex Session Store.

Saves and loads complete session state for persistence and replay.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kodex.config import get_settings

logger = logging.getLogger(__name__)


class SessionStore:
    """
    Manages saving, loading, and listing agent sessions.

    Sessions are stored as JSON files containing the complete
    agent state snapshot, enabling session replay and history.
    """

    def __init__(self) -> None:
        """Initialize the session store."""
        self._settings = get_settings()
        self._session_dir = Path(self._settings.session_dir)
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def save_session(
        self,
        session_id: str,
        state: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """
        Save a session state to disk.

        Args:
            session_id: Unique session identifier.
            state: The complete agent state to save.
            metadata: Additional metadata (optional).

        Returns:
            Path to the saved session file.
        """
        session_data = {
            "session_id": session_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "state": self._serialize_state(state),
        }

        file_path = self._session_dir / f"session_{session_id}.json"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(session_data, f, indent=2, default=str)

            logger.info("💾 Session saved: %s", file_path)
            return file_path

        except Exception as e:
            logger.error("Failed to save session: %s", str(e))
            raise

    def load_session(self, session_id: str) -> dict[str, Any]:
        """
        Load a session from disk.

        Args:
            session_id: Session to load.

        Returns:
            The saved session data.

        Raises:
            FileNotFoundError: If session file doesn't exist.
        """
        file_path = self._session_dir / f"session_{session_id}.json"

        if not file_path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            logger.info("📂 Session loaded: %s", session_id)
            return data

        except json.JSONDecodeError as e:
            logger.error("Corrupt session file: %s", str(e))
            raise

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all saved sessions with metadata.

        Returns:
            List of session summaries, sorted by date (newest first).
        """
        sessions: list[dict[str, Any]] = []

        for file_path in self._session_dir.glob("session_*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                state = data.get("state", {})
                sessions.append({
                    "session_id": data.get("session_id", ""),
                    "saved_at": data.get("saved_at", ""),
                    "repo_path": state.get("repo_path", ""),
                    "total_errors": len(state.get("errors", [])),
                    "fixes_applied": len(state.get("fix_history", [])),
                    "status": state.get("status", "unknown"),
                    "file_path": str(file_path),
                })

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Skipping corrupt session: %s (%s)", file_path.name, str(e))

        # Sort by date, newest first
        sessions.sort(key=lambda s: s.get("saved_at", ""), reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """
        Delete a saved session.

        Args:
            session_id: Session to delete.

        Returns:
            True if deleted, False if not found.
        """
        file_path = self._session_dir / f"session_{session_id}.json"

        if file_path.exists():
            file_path.unlink()
            logger.info("🗑️  Session deleted: %s", session_id)
            return True

        return False

    def get_session_events(self, session_id: str) -> list[dict[str, Any]]:
        """
        Get the event timeline for a session (for replay).

        Args:
            session_id: Session to get events for.

        Returns:
            List of session events in chronological order.
        """
        data = self.load_session(session_id)
        state = data.get("state", {})
        return state.get("session_events", [])

    @staticmethod
    def _serialize_state(state: dict[str, Any]) -> dict[str, Any]:
        """
        Serialize agent state for JSON storage.

        Handles non-serializable objects by converting them to strings.
        """
        serialized: dict[str, Any] = {}

        for key, value in state.items():
            # Skip LangChain message objects (not JSON serializable)
            if key == "messages":
                serialized[key] = [
                    {
                        "type": type(m).__name__,
                        "content": m.content if hasattr(m, "content") else str(m),
                    }
                    for m in (value or [])
                ]
            else:
                try:
                    json.dumps(value, default=str)
                    serialized[key] = value
                except (TypeError, ValueError):
                    serialized[key] = str(value)

        return serialized
