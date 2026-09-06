"""
Kodex UI — Dashboard Component.

Metric cards, progress indicators, and token usage visualization.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_dashboard(
    errors: list[dict[str, Any]] | None = None,
    fix_history: list[dict[str, Any]] | None = None,
    token_usage: dict[str, Any] | None = None,
    status: str = "idle",
) -> None:
    """
    Render the dashboard metrics section.

    Args:
        errors: List of detected errors.
        fix_history: List of applied fixes.
        token_usage: Token usage statistics.
        status: Current agent status.
    """
    errors = errors or []
    fix_history = fix_history or []
    usage = token_usage or {}

    total_errors = len(errors)
    fixes_applied = len(fix_history)
    fix_rate = (fixes_applied / total_errors * 100) if total_errors > 0 else 0
    total_tokens = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
    total_cost = usage.get("total_cost", 0.0)

    # ─── Status Bar ─────────────────────────────────────────────────
    status_config = {
        "idle": ("⚪", "Idle", "#6B7280"),
        "running": ("🟢", "Running", "#00D68F"),
        "paused": ("🟡", "Awaiting Review", "#FFAA00"),
        "complete": ("🔵", "Complete", "#6C63FF"),
        "error": ("🔴", "Error", "#FF3D71"),
        "stopped": ("⚪", "Stopped", "#6B7280"),
    }

    emoji, label, color = status_config.get(status, ("⚪", "Unknown", "#6B7280"))

    st.markdown(
        f"""
        <div style="
            display: flex; align-items: center; gap: 8px;
            padding: 8px 16px; margin-bottom: 1rem;
            background: rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, 0.1);
            border: 1px solid {color}33;
            border-radius: 8px;
        ">
            <span style="font-size: 1.2rem;">{emoji}</span>
            <span style="color: {color}; font-weight: 600;">{label}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── Metric Cards ──────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        _render_metric_card(
            "Errors Detected",
            str(total_errors),
            icon="🔍",
            color="#FF3D71" if total_errors > 0 else "#6B7280",
        )

    with col2:
        _render_metric_card(
            "Fixes Applied",
            str(fixes_applied),
            delta=f"{fix_rate:.0f}% fix rate" if total_errors > 0 else None,
            icon="🔧",
            color="#00D68F",
        )

    with col3:
        _render_metric_card(
            "Total Tokens",
            f"{total_tokens:,}",
            icon="🔤",
            color="#00B4D8",
        )

    with col4:
        _render_metric_card(
            "API Cost",
            f"${total_cost:.4f}",
            icon="💰",
            color="#FFAA00",
        )

    # ─── Progress Bar ───────────────────────────────────────────────
    if total_errors > 0 and status in ("running", "paused"):
        current_idx = st.session_state.get("current_error_index", 0)
        progress = (current_idx + 1) / total_errors

        st.markdown(
            f"""
            <div style="margin: 0.5rem 0;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                    <span style="color: #9CA3AF; font-size: 0.8rem;">
                        Processing error {current_idx + 1} of {total_errors}
                    </span>
                    <span style="color: #9CA3AF; font-size: 0.8rem;">
                        {progress * 100:.0f}%
                    </span>
                </div>
                <div class="progress-container">
                    <div class="progress-bar" style="width: {progress * 100}%;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    icon: str = "",
    color: str = "#6C63FF",
) -> None:
    """Render a single metric card with glassmorphism styling."""
    delta_html = ""
    if delta:
        delta_html = f'<div class="metric-delta positive">{delta}</div>'

    st.markdown(
        f"""
        <div class="metric-card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="metric-label">{label}</span>
                <span style="font-size: 1.5rem;">{icon}</span>
            </div>
            <div class="metric-value" style="
                background: linear-gradient(135deg, {color}, {color}AA);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            ">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
