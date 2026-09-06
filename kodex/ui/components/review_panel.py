"""
Kodex UI — Review Panel Component.

Human-in-the-Loop approval interface with confidence scoring.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_review_panel(
    proposed_fix: dict[str, Any] | None = None,
    current_error: dict[str, Any] | None = None,
) -> str | None:
    """
    Render the human-in-the-loop review panel.

    Args:
        proposed_fix: The proposed fix to review.
        current_error: The error being fixed.

    Returns:
        'approve', 'reject', or None if no action taken.
    """
    if not proposed_fix:
        return None

    st.markdown("#### 👤 Review & Approve")

    confidence = proposed_fix.get("confidence", 0)

    # ─── Confidence Badge ───────────────────────────────────────────
    if confidence >= 80:
        badge_class = "confidence-high"
        badge_icon = "🟢"
    elif confidence >= 50:
        badge_class = "confidence-medium"
        badge_icon = "🟡"
    else:
        badge_class = "confidence-low"
        badge_icon = "🔴"

    st.markdown(
        f"""
        <div class="review-panel">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                <span style="color: #E0E0E0; font-weight: 600; font-size: 1rem;">
                    Proposed Fix
                </span>
                <span class="confidence-badge {badge_class}">
                    {badge_icon} {confidence}% Confidence
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── Error Context ──────────────────────────────────────────────
    if current_error:
        with st.expander("🔍 Error Details", expanded=False):
            st.markdown(f"**File:** `{current_error.get('file_path', '')}`")
            st.markdown(f"**Line:** {current_error.get('line', 0)}")
            st.markdown(f"**Code:** `{current_error.get('code', '')}`")
            st.markdown(f"**Message:** {current_error.get('message', '')}")
            st.markdown(f"**Source:** {current_error.get('source', '')}")

    # ─── Fix Explanation ────────────────────────────────────────────
    with st.expander("🧠 Agent Reasoning", expanded=True):
        st.markdown(proposed_fix.get("explanation", "No explanation available."))

    # ─── Affected Files ─────────────────────────────────────────────
    affected = proposed_fix.get("affected_files", [])
    if affected:
        with st.expander(f"📁 Affected Files ({len(affected)})"):
            for f in affected:
                st.markdown(f"- `{f}`")

    # ─── Action Buttons ─────────────────────────────────────────────
    st.markdown("")  # Spacer

    col1, col2, col3 = st.columns(3)

    action = None

    with col1:
        if st.button(
            "✅ Approve",
            type="primary",
            use_container_width=True,
            key="review_approve",
        ):
            action = "approve"

    with col2:
        if st.button(
            "❌ Reject",
            use_container_width=True,
            key="review_reject",
        ):
            action = "reject"

    with col3:
        if st.button(
            "⏭️ Skip",
            use_container_width=True,
            key="review_skip",
        ):
            action = "reject"

    return action
