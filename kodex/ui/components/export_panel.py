"""
Kodex UI — Export Panel Component.

Audit log export controls for Markdown reports.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from kodex.tracking.report_generator import ReportGenerator


def render_export_panel(
    session_data: dict[str, Any] | None = None,
) -> None:
    """
    Render the audit log export panel.

    Args:
        session_data: Complete session data for report generation.
    """
    st.markdown("#### 📤 Export Audit Report")

    if not session_data:
        st.info("Complete a session to generate an audit report.")
        return

    state = session_data.get("state", {})
    session_id = session_data.get("session_id", "unknown")

    # ─── Report Preview ─────────────────────────────────────────────
    col1, col2 = st.columns(2)

    with col1:
        st.metric("Total Events", len(state.get("session_events", [])))

    with col2:
        st.metric("Fixes Applied", len(state.get("fix_history", [])))

    # ─── Generate Report ────────────────────────────────────────────
    generator = ReportGenerator()

    try:
        report_md = generator.generate_markdown(session_data)

        # Preview
        with st.expander("📄 Report Preview", expanded=False):
            st.markdown(report_md[:3000])
            if len(report_md) > 3000:
                st.caption(f"... ({len(report_md)} characters total)")

        # ─── Download Buttons ───────────────────────────────────────
        st.download_button(
            label="📥 Download Markdown Report",
            data=report_md,
            file_name=f"kodex_audit_{session_id}.md",
            mime="text/markdown",
            use_container_width=True,
        )

        # JSON export
        import json
        json_str = json.dumps(session_data, indent=2, default=str)

        st.download_button(
            label="📥 Download JSON Data",
            data=json_str,
            file_name=f"kodex_session_{session_id}.json",
            mime="application/json",
            use_container_width=True,
        )

    except Exception as e:
        st.error(f"Report generation failed: {str(e)}")
