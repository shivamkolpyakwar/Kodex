"""
Kodex — Main Entry Point.

Provides CLI interface for running the Kodex agent.
Can be run directly or via `streamlit run kodex/ui/app.py`.
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

from kodex import __version__


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging for the application."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


def run_cli(args: argparse.Namespace) -> int:
    """
    Run the Kodex agent from the CLI.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    from kodex.agent.graph import build_graph
    from kodex.agent.state import create_initial_state
    from kodex.config import ensure_directories, get_settings
    from kodex.tracking.audit_logger import AuditLogger
    from kodex.tracking.report_generator import ReportGenerator
    from kodex.tracking.session_store import SessionStore

    logger = logging.getLogger("kodex")

    settings = get_settings()
    ensure_directories(settings)

    session_id = str(uuid.uuid4())[:12]
    repo_path = str(Path(args.repo).resolve())

    logger.info("=" * 60)
    logger.info("🧬 KODEX — Self-Healing Codebase Agent v%s", __version__)
    logger.info("=" * 60)
    logger.info("Session:    %s", session_id)
    logger.info("Repository: %s", repo_path)
    logger.info("Mode:       %s", args.mode)
    logger.info("=" * 60)

    # Validate repo path
    if not Path(repo_path).is_dir():
        logger.error("❌ Repository path not found: %s", repo_path)
        return 1

    # Initialize audit logger
    audit = AuditLogger(session_id)
    audit.log_event("SESSION_START", {
        "repo_path": repo_path,
        "mode": args.mode,
    })

    try:
        # Index repository if requested
        if args.index:
            logger.info("📁 Indexing repository...")
            from kodex.rag.engine import RAGEngine
            engine = RAGEngine()
            stats = engine.index_repository(repo_path)
            logger.info("✅ Indexed %d files", stats.get("indexed", 0))

        # Build and run the agent graph
        logger.info("🔨 Building agent graph...")
        graph = build_graph(
            checkpointer_path=f"./sessions/checkpoints_{session_id}.db",
            interrupt_before_review=(args.mode == "review"),
        )

        initial_state = create_initial_state(
            repo_path=repo_path,
            session_id=session_id,
            mode=args.mode,
            max_retries=args.max_retries,
        )

        config = {"configurable": {"thread_id": session_id}}

        logger.info("🚀 Starting healing session...")

        final_state = None
        for event in graph.stream(initial_state, config=config):
            for node_name, node_output in event.items():
                logger.info("  → %s", node_name)

                # Log key events
                if "errors" in node_output:
                    logger.info(
                        "    Found %d errors",
                        len(node_output.get("errors", [])),
                    )

                if "proposed_fix" in node_output and node_output["proposed_fix"]:
                    fix = node_output["proposed_fix"]
                    logger.info(
                        "    Fix proposed: %d%% confidence",
                        fix["confidence"],
                    )

                if "status" in node_output:
                    if node_output["status"] == "complete":
                        logger.info("🏁 Session complete!")

                final_state = node_output

        # Save session
        store = SessionStore()
        store.save_session(session_id, initial_state | (final_state or {}))

        # Generate report if requested
        if args.report:
            report_gen = ReportGenerator()
            report_path = f"./audit_logs/report_{session_id}.md"
            report_gen.generate_markdown(
                session_data={
                    "session_id": session_id,
                    "state": initial_state | (final_state or {}),
                },
                output_path=report_path,
            )
            logger.info("📄 Report saved: %s", report_path)

        return 0

    except KeyboardInterrupt:
        logger.info("⏹️  Session interrupted by user")
        audit.log_event("SESSION_INTERRUPTED", {})
        return 0

    except Exception as e:
        logger.error("❌ Session failed: %s", str(e), exc_info=True)
        audit.log_event("SESSION_ERROR", {"error": str(e)})
        return 1


def run_ui() -> None:
    """Launch the Streamlit UI."""
    import subprocess

    ui_path = Path(__file__).parent / "ui" / "app.py"
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(ui_path)],
    )


def main() -> None:
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        prog="kodex",
        description="🧬 Kodex — Self-Healing Codebase Agent",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ─── CLI Command ────────────────────────────────────────────────
    cli_parser = subparsers.add_parser("heal", help="Run the healing agent on a repository")
    cli_parser.add_argument(
        "repo",
        type=str,
        help="Path to the repository to heal",
    )
    cli_parser.add_argument(
        "--mode",
        choices=["auto", "review"],
        default="auto",
        help="Agent mode (default: auto)",
    )
    cli_parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max fix retries per error (default: 3)",
    )
    cli_parser.add_argument(
        "--index",
        action="store_true",
        help="Index the repository before healing",
    )
    cli_parser.add_argument(
        "--report",
        action="store_true",
        help="Generate an audit report after completion",
    )
    cli_parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)",
    )

    # ─── UI Command ─────────────────────────────────────────────────
    subparsers.add_parser("ui", help="Launch the Streamlit Command Center")

    # ─── Index Command ──────────────────────────────────────────────
    index_parser = subparsers.add_parser("index", help="Index a repository for RAG")
    index_parser.add_argument(
        "repo",
        type=str,
        help="Path to the repository to index",
    )

    # ─── Parse and Execute ──────────────────────────────────────────
    args = parser.parse_args()

    if args.command == "heal":
        setup_logging(args.log_level)
        sys.exit(run_cli(args))

    elif args.command == "ui":
        run_ui()

    elif args.command == "index":
        setup_logging("INFO")
        logger = logging.getLogger("kodex")

        from kodex.rag.engine import RAGEngine
        engine = RAGEngine()
        repo_path = str(Path(args.repo).resolve())
        stats = engine.index_repository(repo_path)
        logger.info("✅ Indexed %d files", stats.get("indexed", 0))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
