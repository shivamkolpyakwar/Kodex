"""
Tests for the Kodex Agent module.

Tests state creation, node functions, and graph building.
"""

from __future__ import annotations

import pytest

from kodex.agent.state import AgentState, CodeError, ProposedFix, create_initial_state


class TestAgentState:
    """Tests for the AgentState schema and factory."""

    def test_create_initial_state_defaults(self) -> None:
        """Test that initial state has correct default values."""
        state = create_initial_state(
            repo_path="/tmp/test-repo",
            session_id="test-123",
        )

        assert state["repo_path"] == "/tmp/test-repo"
        assert state["session_id"] == "test-123"
        assert state["mode"] == "review"
        assert state["max_retries"] == 3
        assert state["current_retry"] == 0
        assert state["current_error_index"] == 0
        assert state["status"] == "running"
        assert state["errors"] == []
        assert state["fix_history"] == []
        assert state["messages"] == []
        assert state["current_error"] is None
        assert state["proposed_fix"] is None

    def test_create_initial_state_custom_values(self) -> None:
        """Test that initial state respects custom values."""
        state = create_initial_state(
            repo_path="/home/user/project",
            session_id="custom-456",
            mode="auto",
            max_retries=5,
        )

        assert state["mode"] == "auto"
        assert state["max_retries"] == 5
        assert state["session_id"] == "custom-456"

    def test_token_usage_initial_values(self) -> None:
        """Test that token usage starts at zero."""
        state = create_initial_state(
            repo_path="/tmp/repo",
            session_id="token-test",
        )

        usage = state["token_usage"]
        assert usage["prompt_tokens"] == 0
        assert usage["completion_tokens"] == 0
        assert usage["embedding_tokens"] == 0
        assert usage["total_cost"] == 0.0
        assert usage["llm_calls"] == 0


class TestCodeError:
    """Tests for the CodeError TypedDict."""

    def test_code_error_creation(self) -> None:
        """Test creating a CodeError instance."""
        error = CodeError(
            file_path="src/main.py",
            line=42,
            column=10,
            code="E501",
            message="Line too long (120 > 79 characters)",
            severity="warning",
            source="ruff",
        )

        assert error["file_path"] == "src/main.py"
        assert error["line"] == 42
        assert error["code"] == "E501"
        assert error["source"] == "ruff"


class TestProposedFix:
    """Tests for the ProposedFix TypedDict."""

    def test_proposed_fix_creation(self) -> None:
        """Test creating a ProposedFix instance."""
        fix = ProposedFix(
            file_path="src/main.py",
            original_content="x = 1",
            patched_content="x: int = 1",
            explanation="Added type hint.",
            confidence=85,
            diff="+x: int = 1\n-x = 1",
            affected_files=[],
        )

        assert fix["confidence"] == 85
        assert fix["file_path"] == "src/main.py"
        assert fix["affected_files"] == []


class TestNodeRouting:
    """Tests for the routing functions."""

    def test_check_errors_route_with_errors(self) -> None:
        """Test routing when errors are found."""
        from kodex.agent.nodes import check_errors_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["errors"] = [
            CodeError(
                file_path="test.py", line=1, column=0,
                code="E001", message="Error", severity="error", source="ruff",
            ),
        ]

        assert check_errors_route(state) == "retrieve_context"

    def test_check_errors_route_no_errors(self) -> None:
        """Test routing when no errors are found."""
        from kodex.agent.nodes import check_errors_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["errors"] = []

        assert check_errors_route(state) == "finalize"

    def test_verify_route_tests_pass(self) -> None:
        """Test routing when tests pass."""
        from kodex.agent.nodes import verify_route
        from kodex.agent.state import TestResult

        state = create_initial_state("/tmp/repo", "test-id")
        state["test_results"] = TestResult(
            passed=True, total=5, failures=0, errors=0,
            duration=1.5, output="", failed_tests=[],
        )

        assert verify_route(state) == "regression_test"

    def test_verify_route_tests_fail_with_retries(self) -> None:
        """Test routing when tests fail and retries are available."""
        from kodex.agent.nodes import verify_route
        from kodex.agent.state import TestResult

        state = create_initial_state("/tmp/repo", "test-id")
        state["test_results"] = TestResult(
            passed=False, total=5, failures=2, errors=0,
            duration=1.5, output="", failed_tests=["test_a"],
        )
        state["current_retry"] = 0
        state["max_retries"] = 3

        assert verify_route(state) == "rollback"

    def test_review_route_approved(self) -> None:
        """Test routing when fix is approved."""
        from kodex.agent.nodes import review_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["fix_approved"] = True

        assert review_route(state) == "apply_fix"

    def test_review_route_rejected(self) -> None:
        """Test routing when fix is rejected."""
        from kodex.agent.nodes import review_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["fix_approved"] = False

        assert review_route(state) == "skip_error"

    def test_next_error_route_more_errors(self) -> None:
        """Test routing to next error when more exist."""
        from kodex.agent.nodes import next_error_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["errors"] = [
            CodeError(
                file_path="a.py", line=1, column=0,
                code="E001", message="Error 1", severity="error", source="ruff",
            ),
            CodeError(
                file_path="b.py", line=2, column=0,
                code="E002", message="Error 2", severity="error", source="ruff",
            ),
        ]
        state["current_error_index"] = 0

        assert next_error_route(state) == "retrieve_context"

    def test_next_error_route_all_done(self) -> None:
        """Test routing to finalize when all errors processed."""
        from kodex.agent.nodes import next_error_route

        state = create_initial_state("/tmp/repo", "test-id")
        state["errors"] = [
            CodeError(
                file_path="a.py", line=1, column=0,
                code="E001", message="Error", severity="error", source="ruff",
            ),
        ]
        state["current_error_index"] = 0

        assert next_error_route(state) == "finalize"


class TestGraphBuild:
    """Tests for graph compilation."""

    def test_graph_compiles(self) -> None:
        """Test that the graph compiles without errors."""
        from kodex.agent.graph import build_graph

        graph = build_graph(interrupt_before_review=False)
        assert graph is not None
