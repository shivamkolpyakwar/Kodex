"""
Kodex Audit Logger.

Provides structured event logging for the entire agent lifecycle.
Events are logged to both the console and a JSON file.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from kodex.config import get_settings

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Structured audit logger for Kodex sessions.

    Logs events in JSON format to a session-specific file,
    providing a complete audit trail of agent actions.
    """

    # Valid event types
    EVENT_TYPES = {
        "SESSION_START",
        "SESSION_COMPLETE",
        "ERROR_DETECTED",
        "CONTEXT_RETRIEVED",
        "FIX_PROPOSED",
        "FIX_APPROVED",
        "FIX_REJECTED",
        "FIX_AUTO_APPROVED",
        "FIX_APPLIED",
        "FIX_APPLY_FAILED",
        "FIX_FAILED",
        "TEST_PASSED",
        "TEST_FAILED",
        "TEST_ERROR",
        "REGRESSION_CLEAR",
        "REGRESSION_FOUND",
        "REGRESSION_ERROR",
        "GIT_COMMITTED",
        "GIT_FAILED",
        "ROLLBACK",
    }

    def __init__(self, session_id: str) -> None:
        """
        Initialize the audit logger for a session.

        Args:
            session_id: Unique session identifier.
        """
        self._session_id = session_id
        self._settings = get_settings()
        self._events: list[dict[str, Any]] = []

        # Set up file-based logging
        log_dir = Path(self._settings.audit_log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = log_dir / f"audit_{session_id}.jsonl"

        # Configure structlog
        self._structlog = structlog.get_logger(
            session_id=session_id,
        )

        logger.info("📋 Audit logger initialized: %s", self._log_file)

    def log_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
    ) -> dict[str, Any]:
        """
        Log a structured event.

        Args:
            event_type: Type of event (must be a valid EVENT_TYPE).
            data: Event-specific data.
            duration_ms: Duration of the operation in milliseconds.

        Returns:
            The logged event dict.
        """
        if event_type not in self.EVENT_TYPES:
            logger.warning("Unknown event type: %s", event_type)

        event: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self._session_id,
            "event_type": event_type,
            "data": data or {},
            "duration_ms": round(duration_ms, 2),
        }

        self._events.append(event)

        # Write to JSONL file
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", str(e))

        # Also log via structlog
        self._structlog.info(
            event_type,
            **{k: v for k, v in (data or {}).items() if not isinstance(v, (list, dict))},
        )

        return event

    def get_events(
        self,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get logged events, optionally filtered by type.

        Args:
            event_type: Filter by this event type (optional).

        Returns:
            List of event dicts.
        """
        if event_type:
            return [e for e in self._events if e["event_type"] == event_type]
        return list(self._events)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of the session's audit trail."""
        event_counts: dict[str, int] = {}
        for event in self._events:
            et = event["event_type"]
            event_counts[et] = event_counts.get(et, 0) + 1

        total_duration = sum(e.get("duration_ms", 0) for e in self._events)

        return {
            "session_id": self._session_id,
            "total_events": len(self._events),
            "event_counts": event_counts,
            "total_duration_ms": round(total_duration, 2),
            "log_file": str(self._log_file),
        }

    def load_from_file(self) -> list[dict[str, Any]]:
        """Load events from the JSONL file."""
        events: list[dict[str, Any]] = []

        if not self._log_file.exists():
            return events

        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        events.append(json.loads(line))
        except Exception as e:
            logger.error("Failed to load audit log: %s", str(e))

        self._events = events
        return events
