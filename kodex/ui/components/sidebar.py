"""
Kodex UI — Sidebar Component.

Navigation, configuration, session controls, and theme management.
"""

from __future__ import annotations

import uuid
from typing import Any

import streamlit as st


def render_sidebar() -> dict[str, Any]:
    """
    Render the sidebar with all controls.

    Returns:
        Dict with user-selected configuration values.
    """
    with st.sidebar:
        # ─── Logo & Title ───────────────────────────────────────────
        st.markdown(
            """
            <div style="text-align: center; padding: 1rem 0 0.5rem;">
                <h1 style="margin: 0; font-size: 2rem;">🧬 KODEX</h1>
                <p style="color: #9CA3AF; font-size: 0.8rem; margin-top: 4px;">
                    Self-Healing Codebase Agent
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.divider()

        # ─── Repository Configuration ───────────────────────────────
        st.markdown("#### ⚙️ Configuration")

        repo_path = st.text_input(
            "Repository Path",
            value=st.session_state.get("repo_path", ""),
            placeholder="/path/to/your/repo",
            help="Absolute path to the Git repository to heal.",
        )

        mode = st.selectbox(
            "Agent Mode",
            options=["review", "auto"],
            index=0 if st.session_state.get("mode", "review") == "review" else 1,
            help=(
                "**Review:** Pause for approval before applying fixes.\n"
                "**Auto:** Apply fixes automatically when confidence is sufficient."
            ),
        )

        confidence_threshold = st.slider(
            "Confidence Threshold",
            min_value=0,
            max_value=100,
            value=st.session_state.get("confidence_threshold", 60),
            step=5,
            help="Minimum confidence score (0-100%) to proceed with a fix.",
        )

        max_retries = st.number_input(
            "Max Retries",
            min_value=1,
            max_value=10,
            value=st.session_state.get("max_retries", 3),
            help="Maximum fix attempts per error before skipping.",
        )

        st.divider()

        # ─── Session Controls ───────────────────────────────────────
        st.markdown("#### 🎮 Session Controls")

        col1, col2 = st.columns(2)

        with col1:
            start_btn = st.button(
                "▶️ Start",
                use_container_width=True,
                type="primary",
                disabled=not repo_path,
            )

        with col2:
            stop_btn = st.button(
                "⏹️ Stop",
                use_container_width=True,
                disabled=st.session_state.get("status") != "running",
            )

        index_btn = st.button(
            "📁 Index Repository",
            use_container_width=True,
            disabled=not repo_path,
            help="Index the repository into the vector store for RAG retrieval.",
        )

        st.divider()

        # ─── Session History ────────────────────────────────────────
        st.markdown("#### 📂 Session History")

        sessions = st.session_state.get("session_list", [])
        if sessions:
            for session in sessions[:5]:
                session_id = session.get("session_id", "")[:8]
                status = session.get("status", "unknown")
                fixes = session.get("fixes_applied", 0)
                errors = session.get("total_errors", 0)

                status_emoji = {
                    "complete": "✅",
                    "running": "🔄",
                    "error": "❌",
                    "paused": "⏸️",
                }.get(status, "❓")

                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(
                        f"{status_emoji} `{session_id}` — {fixes}/{errors} fixed",
                    )
                with col_b:
                    if st.button("📂", key=f"load_{session_id}"):
                        st.session_state["load_session_id"] = session.get("session_id")
        else:
            st.caption("No previous sessions")

        st.divider()

        # ─── Theme Toggle ──────────────────────────────────────────
        st.markdown("#### 🎨 Appearance")

        theme = st.selectbox(
            "Theme",
            options=["🌙 Dark", "☀️ Light"],
            index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
            label_visibility="collapsed",
        )

        # ─── Version Info ───────────────────────────────────────────
        st.divider()
        st.caption("Kodex v1.0.0 • Built by Shivam Kolpyakwar")

    # ─── Handle Actions ─────────────────────────────────────────────
    if start_btn:
        session_id = str(uuid.uuid4())[:12]
        st.session_state["session_id"] = session_id
        st.session_state["status"] = "running"
        st.session_state["start_requested"] = True

    if stop_btn:
        st.session_state["status"] = "stopped"

    if index_btn:
        st.session_state["index_requested"] = True

    return {
        "repo_path": repo_path,
        "mode": mode,
        "confidence_threshold": confidence_threshold,
        "max_retries": max_retries,
        "theme": "dark" if "Dark" in theme else "light",
    }
