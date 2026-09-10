"""
Kodex UI — Main Streamlit Application.

The Command Center that ties together all UI components,
manages session state, and orchestrates the agent.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any

# ─── Ensure project root is on sys.path (required for Streamlit Cloud) ───
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import streamlit as st

# ─── Configure logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# =============================================================================
# Page Configuration
# =============================================================================
st.set_page_config(
    page_title="Kodex — Self-Healing Codebase Agent",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Load Custom CSS
# =============================================================================
def load_css() -> None:
    """Load custom CSS styles."""
    css_path = Path(__file__).parent / "styles" / "custom.css"
    if css_path.exists():
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

    # Google Fonts
    st.markdown(
        """
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
        <style>
            html, body, [class*="css"] {
                font-family: 'Inter', sans-serif;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


load_css()


# =============================================================================
# Initialize Session State
# =============================================================================
def init_session_state() -> None:
    """Initialize all session state variables."""
    defaults: dict[str, Any] = {
        "session_id": None,
        "repo_path": "",
        "mode": "review",
        "confidence_threshold": 60,
        "max_retries": 3,
        "status": "idle",
        "errors": [],
        "current_error_index": 0,
        "current_error": None,
        "proposed_fix": None,
        "fix_history": [],
        "token_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "embedding_tokens": 0,
            "total_cost": 0.0,
            "llm_calls": 0,
        },
        "session_events": [],
        "terminal_logs": [],
        "session_list": [],
        "theme": "dark",
        "start_requested": False,
        "index_requested": False,
        "load_session_id": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# =============================================================================
# Sidebar
# =============================================================================
from kodex.ui.components.sidebar import render_sidebar

config = render_sidebar()

# Update session state from sidebar
st.session_state["repo_path"] = config["repo_path"]
st.session_state["mode"] = config["mode"]
st.session_state["confidence_threshold"] = config["confidence_threshold"]
st.session_state["max_retries"] = config["max_retries"]
st.session_state["theme"] = config["theme"]


# =============================================================================
# Main Content Area
# =============================================================================
from kodex.ui.components.dashboard import render_dashboard
from kodex.ui.components.diff_viewer import render_diff_viewer
from kodex.ui.components.export_panel import render_export_panel
from kodex.ui.components.review_panel import render_review_panel
from kodex.ui.components.session_replay import render_session_replay
from kodex.ui.components.terminal import add_terminal_log, render_terminal


# ─── Dashboard Metrics ──────────────────────────────────────────────────
render_dashboard(
    errors=st.session_state.get("errors"),
    fix_history=st.session_state.get("fix_history"),
    token_usage=st.session_state.get("token_usage"),
    status=st.session_state.get("status", "idle"),
)

# ─── Tab Layout ─────────────────────────────────────────────────────────
tab_diff, tab_terminal, tab_replay, tab_export = st.tabs([
    "📝 Code Diff",
    "💻 Terminal",
    "🔄 Session Replay",
    "📤 Export",
])

with tab_diff:
    proposed_fix = st.session_state.get("proposed_fix")

    if proposed_fix:
        render_diff_viewer(
            diff_text=proposed_fix.get("diff"),
            file_path=proposed_fix.get("file_path", ""),
            additions=proposed_fix.get("diff", "").count("\n+") if proposed_fix.get("diff") else 0,
            deletions=proposed_fix.get("diff", "").count("\n-") if proposed_fix.get("diff") else 0,
        )

        # Review panel (below diff)
        if st.session_state.get("mode") == "review" and st.session_state.get("status") == "paused":
            review_action = render_review_panel(
                proposed_fix=proposed_fix,
                current_error=st.session_state.get("current_error"),
            )

            if review_action == "approve":
                st.session_state["fix_approved"] = True
                st.session_state["status"] = "running"
                add_terminal_log("✅ Fix approved by user", "success")
                st.rerun()

            elif review_action == "reject":
                st.session_state["fix_approved"] = False
                st.session_state["status"] = "running"
                add_terminal_log("❌ Fix rejected by user", "warning")
                st.rerun()

    else:
        st.info(
            "No code diff to display yet. "
            "Start a healing session from the sidebar to begin."
        )

with tab_terminal:
    render_terminal()

with tab_replay:
    render_session_replay(
        events=st.session_state.get("session_events"),
    )

with tab_export:
    session_data = None
    if st.session_state.get("status") in ("complete", "error", "stopped"):
        session_data = {
            "session_id": st.session_state.get("session_id", ""),
            "saved_at": "",
            "state": {
                "repo_path": st.session_state.get("repo_path", ""),
                "errors": st.session_state.get("errors", []),
                "fix_history": st.session_state.get("fix_history", []),
                "token_usage": st.session_state.get("token_usage", {}),
                "session_events": st.session_state.get("session_events", []),
                "test_results": st.session_state.get("test_results"),
                "regression_results": st.session_state.get("regression_results"),
                "mode": st.session_state.get("mode", ""),
                "status": st.session_state.get("status", ""),
            },
        }

    render_export_panel(session_data=session_data)


# =============================================================================
# Handle Agent Execution
# =============================================================================
def run_agent_session() -> None:
    """Run the Kodex agent session."""
    from kodex.agent.graph import build_graph
    from kodex.agent.state import create_initial_state
    from kodex.config import ensure_directories, get_settings

    settings = get_settings()
    ensure_directories(settings)

    session_id = st.session_state.get("session_id", str(uuid.uuid4())[:12])
    repo_path = st.session_state["repo_path"]

    add_terminal_log(f"🚀 Starting Kodex session: {session_id}", "info")
    add_terminal_log(f"📁 Repository: {repo_path}", "info")
    add_terminal_log(f"⚙️  Mode: {st.session_state['mode']}", "info")

    try:
        # Build the agent graph
        graph = build_graph(
            checkpointer_path=f"./sessions/checkpoints_{session_id}.db",
            interrupt_before_review=(st.session_state["mode"] == "review"),
        )

        # Create initial state
        initial_state = create_initial_state(
            repo_path=repo_path,
            session_id=session_id,
            mode=st.session_state["mode"],
            max_retries=st.session_state["max_retries"],
        )

        add_terminal_log("🔨 Agent graph compiled", "success")

        # Run the graph
        config = {"configurable": {"thread_id": session_id}}

        for event in graph.stream(initial_state, config=config):
            # Update UI state from graph events
            for node_name, node_output in event.items():
                add_terminal_log(f"🔄 Node: {node_name}", "info")

                # Sync relevant state
                if "errors" in node_output:
                    st.session_state["errors"] = node_output["errors"]
                    add_terminal_log(
                        f"🔍 Found {len(node_output['errors'])} errors",
                        "warning" if node_output["errors"] else "success",
                    )

                if "proposed_fix" in node_output and node_output["proposed_fix"]:
                    st.session_state["proposed_fix"] = node_output["proposed_fix"]
                    confidence = node_output["proposed_fix"]["confidence"]
                    add_terminal_log(
                        f"💡 Fix proposed (confidence: {confidence}%)",
                        "info",
                    )

                if "fix_history" in node_output:
                    st.session_state["fix_history"] = node_output["fix_history"]

                if "token_usage" in node_output:
                    st.session_state["token_usage"] = node_output["token_usage"]

                if "session_events" in node_output:
                    st.session_state["session_events"] = node_output["session_events"]

                if "current_error" in node_output:
                    st.session_state["current_error"] = node_output["current_error"]

                if "current_error_index" in node_output:
                    st.session_state["current_error_index"] = node_output["current_error_index"]

                if "status" in node_output:
                    st.session_state["status"] = node_output["status"]

                    if node_output["status"] == "complete":
                        add_terminal_log("🏁 Session complete!", "success")

        # Save session
        try:
            from kodex.tracking.session_store import SessionStore
            store = SessionStore()
            store.save_session(session_id, dict(st.session_state))
            add_terminal_log("💾 Session saved", "success")
        except Exception as e:
            add_terminal_log(f"⚠️ Session save failed: {e}", "warning")

    except Exception as e:
        logger.error("Agent session failed: %s", str(e))
        st.session_state["status"] = "error"
        add_terminal_log(f"❌ Session error: {str(e)}", "error")


def index_repository() -> None:
    """Index the repository for RAG."""
    repo_path = st.session_state["repo_path"]

    add_terminal_log(f"📁 Indexing repository: {repo_path}", "info")

    try:
        from kodex.rag.engine import RAGEngine
        engine = RAGEngine()
        stats = engine.index_repository(repo_path)

        add_terminal_log(
            f"✅ Indexed {stats.get('indexed', 0)} files",
            "success",
        )

    except Exception as e:
        add_terminal_log(f"❌ Indexing failed: {str(e)}", "error")


# ─── Execute Pending Actions ───────────────────────────────────────────
if st.session_state.get("start_requested"):
    st.session_state["start_requested"] = False
    run_agent_session()
    st.rerun()

if st.session_state.get("index_requested"):
    st.session_state["index_requested"] = False
    index_repository()
    st.rerun()
