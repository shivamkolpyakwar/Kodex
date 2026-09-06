"""
Kodex Token Tracker.

Tracks API token usage and calculates costs in real-time.
Provides session-level and per-call metrics.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from kodex.config import MODEL_COSTS, get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMCallRecord:
    """Record of a single LLM API call."""

    timestamp: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost: float
    duration_ms: float
    purpose: str  # e.g., "reason_fix", "generate_explanation"


class TokenTracker:
    """
    Thread-safe tracker for LLM token usage and costs.

    Wraps LLM calls to intercept usage metadata and maintains
    a running total of tokens and costs for the session.
    """

    def __init__(self) -> None:
        """Initialize the tracker."""
        self._lock = threading.Lock()
        self._calls: list[LLMCallRecord] = []
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_embedding_tokens = 0
        self._total_cost = 0.0
        self._settings = get_settings()

    def record_llm_call(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float = 0.0,
        purpose: str = "",
    ) -> LLMCallRecord:
        """
        Record a single LLM API call.

        Args:
            model: Model name used.
            prompt_tokens: Number of prompt/input tokens.
            completion_tokens: Number of completion/output tokens.
            duration_ms: Call duration in milliseconds.
            purpose: Description of what this call was for.

        Returns:
            The recorded LLMCallRecord.
        """
        # Calculate cost
        cost_config = MODEL_COSTS.get(model, {
            "prompt": self._settings.cost_per_1k_prompt_tokens,
            "completion": self._settings.cost_per_1k_completion_tokens,
        })

        cost = (
            (prompt_tokens / 1000) * cost_config["prompt"]
            + (completion_tokens / 1000) * cost_config["completion"]
        )

        record = LLMCallRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost=cost,
            duration_ms=duration_ms,
            purpose=purpose,
        )

        with self._lock:
            self._calls.append(record)
            self._total_prompt_tokens += prompt_tokens
            self._total_completion_tokens += completion_tokens
            self._total_cost += cost

        logger.debug(
            "📊 Token usage: +%d prompt, +%d completion ($%.4f) [%s]",
            prompt_tokens, completion_tokens, cost, purpose,
        )

        return record

    def record_embedding_call(
        self,
        model: str,
        tokens: int,
        duration_ms: float = 0.0,
    ) -> None:
        """Record an embedding API call."""
        cost_config = MODEL_COSTS.get(model, {
            "prompt": self._settings.cost_per_1k_embedding_tokens,
            "completion": 0.0,
        })

        cost = (tokens / 1000) * cost_config["prompt"]

        with self._lock:
            self._total_embedding_tokens += tokens
            self._total_cost += cost

    def get_session_stats(self) -> dict[str, Any]:
        """
        Get aggregate session statistics.

        Returns:
            Dict with total tokens, costs, and call count.
        """
        with self._lock:
            return {
                "prompt_tokens": self._total_prompt_tokens,
                "completion_tokens": self._total_completion_tokens,
                "embedding_tokens": self._total_embedding_tokens,
                "total_tokens": (
                    self._total_prompt_tokens
                    + self._total_completion_tokens
                    + self._total_embedding_tokens
                ),
                "total_cost": round(self._total_cost, 6),
                "llm_calls": len(self._calls),
                "avg_tokens_per_call": (
                    round(
                        (self._total_prompt_tokens + self._total_completion_tokens)
                        / len(self._calls),
                    )
                    if self._calls
                    else 0
                ),
            }

    def get_call_history(self) -> list[dict[str, Any]]:
        """Get the full history of LLM calls."""
        with self._lock:
            return [
                {
                    "timestamp": r.timestamp,
                    "model": r.model,
                    "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens,
                    "cost": r.cost,
                    "duration_ms": r.duration_ms,
                    "purpose": r.purpose,
                }
                for r in self._calls
            ]

    def reset(self) -> None:
        """Reset all tracking data."""
        with self._lock:
            self._calls.clear()
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_embedding_tokens = 0
            self._total_cost = 0.0
