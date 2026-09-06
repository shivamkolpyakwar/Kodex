"""
Kodex UI — Diff Viewer Component.

Side-by-side code diff with syntax highlighting.
"""

from __future__ import annotations

from typing import Any

import streamlit as st


def render_diff_viewer(
    diff_text: str | None = None,
    file_path: str = "",
    additions: int = 0,
    deletions: int = 0,
) -> None:
    """
    Render a code diff with syntax highlighting.

    Args:
        diff_text: Unified diff string.
        file_path: Path of the file being diffed.
        additions: Number of added lines.
        deletions: Number of deleted lines.
    """
    st.markdown("#### 📝 Code Diff")

    if not diff_text:
        st.info("No diff to display. Start a healing session to see code changes.")
        return

    # ─── Diff Header ────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="
            display: flex; justify-content: space-between;
            align-items: center; margin-bottom: 0.5rem;
        ">
            <span style="
                color: #E0E0E0; font-family: monospace;
                font-size: 0.85rem;
            ">📄 {_escape_html(file_path)}</span>
            <span>
                <span style="color: #00D68F; font-size: 0.85rem; margin-right: 12px;">
                    +{additions}
                </span>
                <span style="color: #FF3D71; font-size: 0.85rem;">
                    -{deletions}
                </span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ─── Render Diff Lines ──────────────────────────────────────────
    lines_html = []
    for line in diff_text.splitlines():
        escaped = _escape_html(line)

        if line.startswith("+++") or line.startswith("---"):
            lines_html.append(
                f'<span class="diff-line-header">{escaped}</span>'
            )
        elif line.startswith("@@"):
            lines_html.append(
                f'<span class="diff-line-header">{escaped}</span>'
            )
        elif line.startswith("+"):
            lines_html.append(
                f'<span class="diff-line-add">{escaped}</span>'
            )
        elif line.startswith("-"):
            lines_html.append(
                f'<span class="diff-line-del">{escaped}</span>'
            )
        else:
            lines_html.append(
                f'<span class="diff-line-context">{escaped}</span>'
            )

    diff_html = "\n".join(lines_html)

    st.markdown(
        f"""
        <div class="diff-container">
            <pre style="margin: 0; white-space: pre-wrap;">{diff_html}</pre>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
