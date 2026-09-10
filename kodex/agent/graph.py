"""
Kodex Agent Graph Builder.

Constructs the LangGraph StateGraph with all nodes, edges,
conditional routing, and checkpointer for persistence/replay.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from kodex.agent.nodes import (
    apply_fix,
    check_confidence_route,
    check_errors_route,
    detect_errors,
    finalize,
    git_commit,
    human_review,
    next_error,
    next_error_route,
    reason_fix,
    regression_route,
    regression_test,
    retrieve_context,
    review_route,
    rollback,
    verify_fix,
    verify_route,
)
from kodex.agent.state import AgentState

logger = logging.getLogger(__name__)


def build_graph(
    checkpointer_path: str | None = None,
    interrupt_before_review: bool = True,
) -> StateGraph:
    """
    Build and compile the Kodex agent graph.

    Args:
        checkpointer_path: Path to SQLite file for state persistence.
            If None, uses in-memory checkpointing.
        interrupt_before_review: If True, the graph pauses before
            the human_review node (for HITL in 'review' mode).

    Returns:
        Compiled LangGraph ready for invocation.
    """
    logger.info("🔨 Building Kodex agent graph...")

    # ─── Create State Graph ─────────────────────────────────────────────
    builder = StateGraph(AgentState)

    # ─── Add Nodes ──────────────────────────────────────────────────────
    builder.add_node("detect_errors", detect_errors)
    builder.add_node("retrieve_context", retrieve_context)
    builder.add_node("reason_fix", reason_fix)
    builder.add_node("human_review", human_review)
    builder.add_node("apply_fix", apply_fix)
    builder.add_node("verify_fix", verify_fix)
    builder.add_node("regression_test", regression_test)
    builder.add_node("git_commit", git_commit)
    builder.add_node("rollback", rollback)
    builder.add_node("next_error", next_error)
    builder.add_node("finalize", finalize)

    # ─── Entry Edge ─────────────────────────────────────────────────────
    builder.add_edge(START, "detect_errors")

    # ─── Conditional: After Detection ───────────────────────────────────
    builder.add_conditional_edges(
        "detect_errors",
        check_errors_route,
        {
            "retrieve_context": "retrieve_context",
            "finalize": "finalize",
        },
    )

    # ─── Fixed: Retrieve → Reason ───────────────────────────────────────
    builder.add_edge("retrieve_context", "reason_fix")

    # ─── Conditional: After Reasoning ───────────────────────────────────
    builder.add_conditional_edges(
        "reason_fix",
        check_confidence_route,
        {
            "human_review": "human_review",
            "apply_fix": "apply_fix",
            "skip_error": "next_error",
        },
    )

    # ─── Conditional: After Review ──────────────────────────────────────
    builder.add_conditional_edges(
        "human_review",
        review_route,
        {
            "apply_fix": "apply_fix",
            "skip_error": "next_error",
        },
    )

    # ─── Fixed: Apply → Verify ──────────────────────────────────────────
    builder.add_edge("apply_fix", "verify_fix")

    # ─── Conditional: After Verification ────────────────────────────────
    builder.add_conditional_edges(
        "verify_fix",
        verify_route,
        {
            "regression_test": "regression_test",
            "rollback": "rollback",
            "skip_error": "next_error",
        },
    )

    # ─── Conditional: After Regression ──────────────────────────────────
    builder.add_conditional_edges(
        "regression_test",
        regression_route,
        {
            "git_commit": "git_commit",
            "rollback": "rollback",
            "skip_error": "next_error",
        },
    )

    # ─── Fixed: Git → Next ──────────────────────────────────────────────
    builder.add_edge("git_commit", "next_error")

    # ─── Fixed: Rollback → Reason (retry loop) ──────────────────────────
    builder.add_edge("rollback", "reason_fix")

    # ─── Conditional: Next Error or Finalize ────────────────────────────
    builder.add_conditional_edges(
        "next_error",
        next_error_route,
        {
            "retrieve_context": "retrieve_context",
            "finalize": "finalize",
        },
    )

    # ─── Terminal Edge ──────────────────────────────────────────────────
    builder.add_edge("finalize", END)

    # ─── Set Up Checkpointer ────────────────────────────────────────────
    if checkpointer_path:
        db_path = Path(checkpointer_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        checkpointer = SqliteSaver(conn)
    else:
        checkpointer = MemorySaver()

    # ─── Compile ────────────────────────────────────────────────────────
    compile_kwargs: dict = {"checkpointer": checkpointer}

    if interrupt_before_review:
        compile_kwargs["interrupt_before"] = ["human_review"]

    graph = builder.compile(**compile_kwargs)

    logger.info("✅ Agent graph compiled successfully")
    return graph

