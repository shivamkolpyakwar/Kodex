"""
Kodex UI — Terminal Component.

Real-time log viewer with color-coded severity levels.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_terminal(
    logs: list[dict[str, Any]] | None = None,
    max_lines: int = 200,
) -> None:
    """
    Render the real-time terminal log viewer.

    Args:
        logs: List of log entries with 'level', 'message', and 'timestamp'.
        max_lines: Maximum number of lines to display.
    """
    st.markdown("#### 💻 Terminal")

    logs = logs or st.session_state.get("terminal_logs", [])

    if not logs:
        st.markdown(
            """
            <div class="terminal-container">
                <div class="terminal-line debug">
                    <span class="terminal-prompt">kodex $</span> Waiting for session to start...
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # Build terminal HTML
    lines_html = []
    for log in logs[-max_lines:]:
        level = log.get("level", "info").lower()
        message = _escape_html(log.get("message", ""))
        timestamp = log.get("timestamp", "")

        # Time prefix
        time_str = ""
        if timestamp:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                time_str = f'<span style="color: #6B7280;">[{dt.strftime("%H:%M:%S")}]</span> '
            except (ValueError, TypeError):
                pass

        # Level-specific prefix
        level_prefix = {
            "info": '<span class="terminal-prompt">ℹ</span>',
            "success": '<span style="color: #00D68F;">✓</span>',
            "warning": '<span style="color: #FFAA00;">⚠</span>',
            "error": '<span style="color: #FF3D71;">✗</span>',
            "debug": '<span style="color: #6B7280;">·</span>',
        }.get(level, "")

        lines_html.append(
            f'<div class="terminal-line {level}">'
            f'{time_str}{level_prefix} {message}'
            f'</div>'
        )

    terminal_content = "\n".join(lines_html)

    st.markdown(
        f"""
        <div class="terminal-container" id="kodex-terminal">
            {terminal_content}
        </div>
        <script>
            var terminal = document.getElementById('kodex-terminal');
            if (terminal) terminal.scrollTop = terminal.scrollHeight;
        </script>
        """,
        unsafe_allow_html=True,
    )

    # ─── Filter Controls ────────────────────────────────────────────
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        search = st.text_input(
            "Filter logs",
            placeholder="Search...",
            label_visibility="collapsed",
            key="terminal_search",
        )

    with col2:
        level_filter = st.selectbox(
            "Level",
            options=["All", "Info", "Success", "Warning", "Error"],
            label_visibility="collapsed",
            key="terminal_level_filter",
        )

    with col3:
        if st.button("🗑️ Clear", key="clear_terminal"):
            st.session_state["terminal_logs"] = []
            st.rerun()


def add_terminal_log(
    message: str,
    level: str = "info",
) -> None:
    """
    Add a log entry to the terminal.

    Args:
        message: Log message text.
        level: Log level (info, success, warning, error, debug).
    """
    from datetime import datetime, timezone

    if "terminal_logs" not in st.session_state:
        st.session_state["terminal_logs"] = []

    st.session_state["terminal_logs"].append({
        "message": message,
        "level": level,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
