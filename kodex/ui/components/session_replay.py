"""
Kodex UI — Session Replay Component.

Timeline viewer for replaying agent decision traces.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_session_replay(
    events: list[dict[str, Any]] | None = None,
) -> None:
    """
    Render the session replay timeline.

    Args:
        events: List of session events to display.
    """
    st.markdown("#### 🔄 Session Replay")

    events = events or []

    if not events:
        st.info("No session data to replay. Complete a session first.")
        return

    # ─── Timeline Slider ────────────────────────────────────────────
    total_events = len(events)

    step = st.slider(
        "Step through events",
        min_value=1,
        max_value=total_events,
        value=total_events,
        key="replay_step",
    )

    visible_events = events[:step]

    # ─── Event Stats ────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Events", f"{step}/{total_events}")

    with col2:
        total_duration = sum(
            e.get("duration_ms", 0) for e in visible_events
        )
        st.metric("Duration", f"{total_duration / 1000:.1f}s")

    with col3:
        event_types = set(e.get("event_type", "") for e in visible_events)
        st.metric("Unique Events", len(event_types))

    # ─── Timeline ──────────────────────────────────────────────────
    timeline_html = []

    event_icons = {
        "ERROR_DETECTED": "🔍",
        "CONTEXT_RETRIEVED": "📚",
        "FIX_PROPOSED": "💡",
        "FIX_APPROVED": "✅",
        "FIX_REJECTED": "❌",
        "FIX_AUTO_APPROVED": "🤖",
        "FIX_APPLIED": "📝",
        "FIX_APPLY_FAILED": "⚠️",
        "FIX_FAILED": "❌",
        "TEST_PASSED": "✅",
        "TEST_FAILED": "❌",
        "TEST_ERROR": "⚠️",
        "REGRESSION_CLEAR": "🟢",
        "REGRESSION_FOUND": "🔴",
        "GIT_COMMITTED": "🔀",
        "GIT_FAILED": "⚠️",
        "ROLLBACK": "⏪",
        "SESSION_COMPLETE": "🏁",
        "SESSION_START": "🚀",
    }

    for event in visible_events:
        event_type = event.get("event_type", "UNKNOWN")
        icon = event_icons.get(event_type, "📌")
        timestamp = event.get("timestamp", "")
        duration = event.get("duration_ms", 0)
        data = event.get("data", {})

        # Format time
        time_str = ""
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                time_str = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                time_str = timestamp[:8]

        # Brief detail
        detail_parts = []
        for k, v in list(data.items())[:3]:
            if isinstance(v, (str, int, float, bool)):
                detail_parts.append(f"<span style='color:#9CA3AF;'>{k}:</span> {v}")
        detail = " · ".join(detail_parts) if detail_parts else ""

        duration_str = f"<span style='color:#6B7280;'>{duration:.0f}ms</span>" if duration else ""

        timeline_html.append(
            f"""
            <div class="timeline-item">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div>
                        <span style="font-size: 0.75rem; color: #6B7280;">{time_str}</span>
                        <div style="color: #E0E0E0; font-weight: 500; margin-top: 2px;">
                            {icon} {event_type.replace('_', ' ').title()}
                        </div>
                        <div style="font-size: 0.8rem; margin-top: 4px;">
                            {detail}
                        </div>
                    </div>
                    {duration_str}
                </div>
            </div>
            """
        )

    st.markdown(
        '<div style="padding: 0.5rem 0;">' + "".join(timeline_html) + "</div>",
        unsafe_allow_html=True,
    )
