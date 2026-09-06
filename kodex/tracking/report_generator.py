"""
Kodex Report Generator.

Generates Markdown audit reports from session data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kodex.config import get_settings

logger = logging.getLogger(__name__)


class ReportGenerator:
    """
    Generates Markdown audit reports from session data.

    Creates detailed reports including:
    - Session overview and metrics
    - Error detection results
    - Fix explanations and diffs
    - Test results
    - Token usage and costs
    """

    def __init__(self) -> None:
        """Initialize the report generator."""
        self._settings = get_settings()

    def generate_markdown(
        self,
        session_data: dict[str, Any],
        output_path: str | None = None,
    ) -> str:
        """
        Generate a Markdown audit report.

        Args:
            session_data: Complete session data (from SessionStore).
            output_path: Optional path to write the report file.

        Returns:
            The generated Markdown string.
        """
        state = session_data.get("state", {})
        metadata = session_data.get("metadata", {})

        sections = [
            self._header(session_data),
            self._overview(state),
            self._errors_section(state),
            self._fixes_section(state),
            self._test_results_section(state),
            self._token_usage_section(state),
            self._event_timeline(state),
            self._footer(),
        ]

        report = "\n\n".join(sections)

        # Write to file if path provided
        if output_path:
            try:
                path = Path(output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(report, encoding="utf-8")
                logger.info("📄 Report saved: %s", output_path)
            except Exception as e:
                logger.error("Failed to save report: %s", str(e))

        return report

    def _header(self, session_data: dict[str, Any]) -> str:
        """Generate the report header."""
        session_id = session_data.get("session_id", "unknown")
        saved_at = session_data.get("saved_at", "unknown")

        return f"""# 🧬 Kodex Audit Report

**Session ID:** `{session_id}`
**Generated:** {saved_at}
**Report Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

---"""

    def _overview(self, state: dict[str, Any]) -> str:
        """Generate the session overview section."""
        errors = state.get("errors", [])
        fixes = state.get("fix_history", [])
        token_usage = state.get("token_usage", {})

        fix_rate = (
            f"{(len(fixes) / len(errors) * 100):.1f}%"
            if errors
            else "N/A"
        )

        return f"""## 📊 Session Overview

| Metric | Value |
|--------|-------|
| Repository | `{state.get('repo_path', 'N/A')}` |
| Mode | `{state.get('mode', 'N/A')}` |
| Status | `{state.get('status', 'N/A')}` |
| Total Errors Detected | {len(errors)} |
| Fixes Applied | {len(fixes)} |
| Fix Rate | {fix_rate} |
| Total Tokens | {token_usage.get('prompt_tokens', 0) + token_usage.get('completion_tokens', 0):,} |
| Total Cost | ${token_usage.get('total_cost', 0):.4f} |
| LLM Calls | {token_usage.get('llm_calls', 0)} |"""

    def _errors_section(self, state: dict[str, Any]) -> str:
        """Generate the detected errors section."""
        errors = state.get("errors", [])

        if not errors:
            return "## 🔍 Detected Errors\n\nNo errors detected."

        lines = ["## 🔍 Detected Errors\n"]
        lines.append("| # | File | Line | Code | Message | Source |")
        lines.append("|---|------|------|------|---------|--------|")

        for i, err in enumerate(errors, 1):
            msg = err.get("message", "")[:60]
            lines.append(
                f"| {i} | `{err.get('file_path', '')}` | "
                f"{err.get('line', 0)} | `{err.get('code', '')}` | "
                f"{msg} | {err.get('source', '')} |"
            )

        return "\n".join(lines)

    def _fixes_section(self, state: dict[str, Any]) -> str:
        """Generate the applied fixes section."""
        fixes = state.get("fix_history", [])

        if not fixes:
            return "## 🔧 Applied Fixes\n\nNo fixes were applied."

        lines = ["## 🔧 Applied Fixes\n"]

        for i, fix in enumerate(fixes, 1):
            error = fix.get("error", {})
            fix_data = fix.get("fix", {})

            lines.append(f"### Fix #{i}")
            lines.append(f"**File:** `{error.get('file_path', '')}`")
            lines.append(f"**Error:** `{error.get('code', '')}` — {error.get('message', '')}")
            lines.append(f"**Confidence:** {fix_data.get('confidence', 0)}%")
            lines.append(f"**Branch:** `{fix.get('branch', '')}`\n")
            lines.append(f"**Explanation:**\n{fix_data.get('explanation', 'N/A')}\n")

            diff = fix_data.get("diff", "")
            if diff:
                lines.append(f"**Diff:**\n```diff\n{diff}\n```\n")

            lines.append("---")

        return "\n".join(lines)

    def _test_results_section(self, state: dict[str, Any]) -> str:
        """Generate the test results section."""
        test_results = state.get("test_results")
        regression_results = state.get("regression_results")

        lines = ["## 🧪 Test Results\n"]

        if test_results:
            status = "✅ PASSED" if test_results.get("passed") else "❌ FAILED"
            lines.append(f"### Targeted Tests: {status}")
            lines.append(f"- Total: {test_results.get('total', 0)}")
            lines.append(f"- Failures: {test_results.get('failures', 0)}")
            lines.append(f"- Duration: {test_results.get('duration', 0):.2f}s\n")
        else:
            lines.append("### Targeted Tests: Not run\n")

        if regression_results:
            status = "✅ PASSED" if regression_results.get("passed") else "❌ FAILED"
            lines.append(f"### Regression Tests: {status}")
            lines.append(f"- Total: {regression_results.get('total', 0)}")
            lines.append(f"- Failures: {regression_results.get('failures', 0)}")
            lines.append(f"- Duration: {regression_results.get('duration', 0):.2f}s")
        else:
            lines.append("### Regression Tests: Not run")

        return "\n".join(lines)

    def _token_usage_section(self, state: dict[str, Any]) -> str:
        """Generate the token usage section."""
        usage = state.get("token_usage", {})

        return f"""## 💰 Token Usage & Costs

| Metric | Value |
|--------|-------|
| Prompt Tokens | {usage.get('prompt_tokens', 0):,} |
| Completion Tokens | {usage.get('completion_tokens', 0):,} |
| Embedding Tokens | {usage.get('embedding_tokens', 0):,} |
| Total Tokens | {usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0) + usage.get('embedding_tokens', 0):,} |
| Total Cost | ${usage.get('total_cost', 0):.4f} |
| LLM Calls | {usage.get('llm_calls', 0)} |"""

    def _event_timeline(self, state: dict[str, Any]) -> str:
        """Generate the event timeline section."""
        events = state.get("session_events", [])

        if not events:
            return "## 📜 Event Timeline\n\nNo events recorded."

        lines = ["## 📜 Event Timeline\n"]
        lines.append("| Time | Event | Duration | Details |")
        lines.append("|------|-------|----------|---------|")

        for event in events:
            timestamp = event.get("timestamp", "")
            if timestamp:
                # Show only time portion
                try:
                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%H:%M:%S")
                except ValueError:
                    time_str = timestamp[:19]
            else:
                time_str = "—"

            event_type = event.get("event_type", "")
            duration = event.get("duration_ms", 0)
            duration_str = f"{duration:.0f}ms" if duration else "—"

            # Brief detail from event data
            data = event.get("data", {})
            detail_parts = []
            for k, v in list(data.items())[:2]:
                if isinstance(v, (str, int, float, bool)):
                    detail_parts.append(f"{k}={v}")
            detail = ", ".join(detail_parts) if detail_parts else "—"

            lines.append(f"| {time_str} | `{event_type}` | {duration_str} | {detail} |")

        return "\n".join(lines)

    def _footer(self) -> str:
        """Generate the report footer."""
        return """---

*Generated by [Kodex](https://github.com/shivam-kolpyakwar/Kodex) — Self-Healing Codebase Agent*
"""
