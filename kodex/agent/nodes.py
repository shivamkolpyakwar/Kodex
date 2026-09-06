"""
Kodex Agent Nodes.

Each function is a LangGraph node — it receives the current AgentState,
performs work, and returns a partial state update dict. Nodes are pure
functions with structured error handling throughout.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from kodex.agent.state import (
    AgentState,
    CodeError,
    ProposedFix,
    SessionEvent,
    TestResult,
)
from kodex.config import MODEL_COSTS, get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Helper: Create LLM Instance
# =============================================================================
def _get_llm() -> ChatOpenAI:
    """Create a configured ChatOpenAI instance."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0.1,
        max_retries=2,
        request_timeout=60,
    )


def _create_event(event_type: str, data: dict[str, Any], duration_ms: float = 0.0) -> SessionEvent:
    """Create a timestamped session event for the audit trail."""
    return SessionEvent(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=event_type,
        data=data,
        duration_ms=duration_ms,
    )


def _update_token_usage(
    current: dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
) -> dict[str, Any]:
    """Calculate updated token usage and costs."""
    settings = get_settings()
    prompt_cost = (prompt_tokens / 1000) * settings.cost_per_1k_prompt_tokens
    completion_cost = (completion_tokens / 1000) * settings.cost_per_1k_completion_tokens

    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + prompt_tokens,
        "completion_tokens": current.get("completion_tokens", 0) + completion_tokens,
        "embedding_tokens": current.get("embedding_tokens", 0),
        "total_cost": current.get("total_cost", 0.0) + prompt_cost + completion_cost,
        "llm_calls": current.get("llm_calls", 0) + 1,
    }


# =============================================================================
# Node: detect_errors
# =============================================================================
def detect_errors(state: AgentState) -> dict[str, Any]:
    """
    Run linting and tests to detect errors in the repository.

    Uses Ruff for linting and pytest for test failures.
    Returns detected errors in the state.
    """
    start = time.time()
    repo_path = state["repo_path"]
    logger.info("🔍 Detecting errors in: %s", repo_path)

    errors: list[CodeError] = []

    # ─── Run Ruff Linter ────────────────────────────────────────────────
    try:
        from kodex.tools.lint_tool import LintTool
        lint_tool = LintTool()
        lint_result = lint_tool.execute({"path": repo_path})

        for err in lint_result.get("errors", []):
            errors.append(CodeError(
                file_path=err.get("file", ""),
                line=err.get("line", 0),
                column=err.get("column", 0),
                code=err.get("code", ""),
                message=err.get("message", ""),
                severity="error" if err.get("code", "").startswith("E") else "warning",
                source="ruff",
            ))
        logger.info("  Ruff found %d issues", len(lint_result.get("errors", [])))

    except Exception as e:
        logger.error("  Ruff linting failed: %s", str(e))
        errors.append(CodeError(
            file_path=repo_path,
            line=0,
            column=0,
            code="LINT_ERROR",
            message=f"Linting failed: {str(e)}",
            severity="error",
            source="ruff",
        ))

    # ─── Run pytest ─────────────────────────────────────────────────────
    try:
        from kodex.tools.test_tool import TestTool
        test_tool = TestTool()
        test_result = test_tool.execute({"path": repo_path})

        for failure in test_result.get("failures", []):
            errors.append(CodeError(
                file_path=failure.get("file", ""),
                line=failure.get("line", 0),
                column=0,
                code="TEST_FAIL",
                message=failure.get("message", "Test failed"),
                severity="error",
                source="pytest",
            ))
        logger.info("  pytest found %d failures", len(test_result.get("failures", [])))

    except Exception as e:
        logger.warning("  pytest execution skipped: %s", str(e))

    duration = (time.time() - start) * 1000
    event = _create_event("ERROR_DETECTED", {
        "total_errors": len(errors),
        "by_source": {
            "ruff": sum(1 for e in errors if e["source"] == "ruff"),
            "pytest": sum(1 for e in errors if e["source"] == "pytest"),
        },
    }, duration)

    logger.info("✅ Detection complete: %d errors found", len(errors))

    return {
        "errors": errors,
        "current_error_index": 0,
        "current_error": errors[0] if errors else None,
        "session_events": state["session_events"] + [event],
        "status": "running" if errors else "complete",
    }


# =============================================================================
# Node: retrieve_context
# =============================================================================
def retrieve_context(state: AgentState) -> dict[str, Any]:
    """
    Retrieve relevant multi-file context for the current error using RAG.

    Queries the vector store with the error context and also traces
    import dependencies to retrieve cross-file context.
    """
    start = time.time()
    current_error = state["current_error"]

    if not current_error:
        logger.warning("⚠️  No current error to retrieve context for")
        return {"retrieved_context": []}

    logger.info(
        "📚 Retrieving context for %s:%d [%s]",
        current_error["file_path"],
        current_error["line"],
        current_error["code"],
    )

    context_chunks: list[dict[str, Any]] = []

    try:
        from kodex.rag.engine import RAGEngine
        engine = RAGEngine()

        # Build a rich query from the error
        query = (
            f"Error in {current_error['file_path']} at line {current_error['line']}: "
            f"[{current_error['code']}] {current_error['message']}"
        )

        # Retrieve relevant chunks
        results = engine.query(query, top_k=8)
        context_chunks = results

        logger.info("  Retrieved %d context chunks", len(context_chunks))

    except Exception as e:
        logger.error("  RAG retrieval failed: %s", str(e))
        # Fallback: read the error file directly
        try:
            from kodex.tools.file_tool import FileTool
            file_tool = FileTool()
            content = file_tool.execute({
                "action": "read",
                "path": current_error["file_path"],
            })
            context_chunks = [{
                "content": content.get("content", ""),
                "metadata": {
                    "file_path": current_error["file_path"],
                    "source": "fallback_direct_read",
                },
                "score": 1.0,
            }]
            logger.info("  Fallback: loaded file directly")
        except Exception as fallback_err:
            logger.error("  Fallback read also failed: %s", str(fallback_err))

    duration = (time.time() - start) * 1000
    event = _create_event("CONTEXT_RETRIEVED", {
        "error_code": current_error["code"],
        "chunks_retrieved": len(context_chunks),
        "files": list({c.get("metadata", {}).get("file_path", "") for c in context_chunks}),
    }, duration)

    return {
        "retrieved_context": context_chunks,
        "session_events": state["session_events"] + [event],
    }


# =============================================================================
# Node: reason_fix
# =============================================================================
@retry(
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def reason_fix(state: AgentState) -> dict[str, Any]:
    """
    Use the LLM to reason about and propose a fix for the current error.

    Sends the error details and retrieved context to the LLM.
    Parses the response into a structured ProposedFix with confidence.
    """
    start = time.time()
    current_error = state["current_error"]
    context = state["retrieved_context"]

    if not current_error:
        logger.warning("⚠️  No error to reason about")
        return {"proposed_fix": None}

    logger.info(
        "🧠 Reasoning about fix for %s [%s]",
        current_error["file_path"],
        current_error["code"],
    )

    # ─── Build Context String ───────────────────────────────────────────
    context_str = ""
    for i, chunk in enumerate(context[:8]):  # Limit to top 8 chunks
        meta = chunk.get("metadata", {})
        file_path = meta.get("file_path", "unknown")
        content = chunk.get("content", "")
        score = chunk.get("score", 0.0)
        context_str += (
            f"\n--- Context Chunk {i + 1} (file: {file_path}, relevance: {score:.2f}) ---\n"
            f"{content}\n"
        )

    # ─── Read Current File Content ──────────────────────────────────────
    current_content = ""
    try:
        from kodex.tools.file_tool import FileTool
        file_tool = FileTool()
        result = file_tool.execute({
            "action": "read",
            "path": current_error["file_path"],
        })
        current_content = result.get("content", "")
    except Exception as e:
        logger.warning("  Could not read current file: %s", str(e))

    # ─── LLM Prompt ────────────────────────────────────────────────────
    system_prompt = """You are Kodex, an expert AI code repair agent. Your job is to analyze
code errors, understand the surrounding context, and propose precise, minimal fixes.

RULES:
1. Only change what is necessary to fix the error. Do not refactor unrelated code.
2. Preserve all existing comments and docstrings.
3. Maintain the original coding style (indentation, naming conventions).
4. If the fix requires changes to multiple files, note them in affected_files.
5. Rate your confidence from 0-100 based on how certain you are the fix is correct.

Respond with a JSON object (no markdown fences) with these exact keys:
{
    "patched_content": "<full file content with the fix applied>",
    "explanation": "<clear explanation of what was wrong and how you fixed it>",
    "confidence": <integer 0-100>,
    "affected_files": ["<list of other files that might need changes>"]
}"""

    user_prompt = f"""## Error Details
- **File:** {current_error['file_path']}
- **Line:** {current_error['line']}
- **Code:** {current_error['code']}
- **Message:** {current_error['message']}
- **Source:** {current_error['source']}

## Current File Content
```
{current_content}
```

## Related Context (from other files)
{context_str if context_str.strip() else "No additional context available."}

## Previous Retry Context
{f"This is retry #{state['current_retry']}. Previous attempts failed." if state['current_retry'] > 0 else "First attempt."}

Please analyze the error and propose a fix."""

    # ─── Call LLM ──────────────────────────────────────────────────────
    llm = _get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        response = llm.invoke(messages)

        # Track tokens
        prompt_tokens = response.usage_metadata.get("input_tokens", 0) if response.usage_metadata else 0
        completion_tokens = response.usage_metadata.get("output_tokens", 0) if response.usage_metadata else 0

        token_usage = _update_token_usage(
            state["token_usage"],
            prompt_tokens,
            completion_tokens,
        )

        # ─── Parse LLM Response ────────────────────────────────────────
        response_text = response.content
        # Try to extract JSON from the response
        try:
            # Handle possible markdown code fences
            clean_text = response_text
            if "```json" in clean_text:
                clean_text = clean_text.split("```json")[1].split("```")[0]
            elif "```" in clean_text:
                clean_text = clean_text.split("```")[1].split("```")[0]

            fix_data = json.loads(clean_text.strip())

        except json.JSONDecodeError:
            logger.warning("  Failed to parse LLM JSON, using regex fallback")
            # Fallback: treat entire response as explanation
            fix_data = {
                "patched_content": current_content,
                "explanation": response_text[:500],
                "confidence": 25,
                "affected_files": [],
            }

        # ─── Build Diff ────────────────────────────────────────────────
        import difflib
        diff_lines = difflib.unified_diff(
            current_content.splitlines(keepends=True),
            fix_data.get("patched_content", current_content).splitlines(keepends=True),
            fromfile=f"a/{current_error['file_path']}",
            tofile=f"b/{current_error['file_path']}",
        )
        diff_str = "".join(diff_lines)

        proposed_fix = ProposedFix(
            file_path=current_error["file_path"],
            original_content=current_content,
            patched_content=fix_data.get("patched_content", current_content),
            explanation=fix_data.get("explanation", "No explanation provided."),
            confidence=int(fix_data.get("confidence", 50)),
            diff=diff_str,
            affected_files=fix_data.get("affected_files", []),
        )

        duration = (time.time() - start) * 1000
        event = _create_event("FIX_PROPOSED", {
            "confidence": proposed_fix["confidence"],
            "explanation": proposed_fix["explanation"][:200],
            "has_diff": bool(diff_str.strip()),
        }, duration)

        logger.info(
            "  Proposed fix with %d%% confidence",
            proposed_fix["confidence"],
        )

        return {
            "proposed_fix": proposed_fix,
            "token_usage": token_usage,
            "messages": state["messages"] + [
                HumanMessage(content=user_prompt),
                AIMessage(content=response_text),
            ],
            "session_events": state["session_events"] + [event],
        }

    except Exception as e:
        logger.error("  LLM call failed: %s", str(e))
        duration = (time.time() - start) * 1000
        event = _create_event("FIX_FAILED", {
            "error": str(e),
        }, duration)

        return {
            "proposed_fix": None,
            "session_events": state["session_events"] + [event],
            "status": "error",
        }


# =============================================================================
# Node: human_review
# =============================================================================
def human_review(state: AgentState) -> dict[str, Any]:
    """
    Pause execution for human review of the proposed fix.

    In 'review' mode, the graph will interrupt before this node.
    The UI sets fix_approved in the state before resuming.
    In 'auto' mode, this node auto-approves.
    """
    logger.info("👤 Awaiting human review...")

    if state["mode"] == "auto":
        logger.info("  Auto-mode: auto-approving fix")
        event = _create_event("FIX_AUTO_APPROVED", {
            "confidence": state["proposed_fix"]["confidence"] if state["proposed_fix"] else 0,
        })
        return {
            "fix_approved": True,
            "session_events": state["session_events"] + [event],
        }

    # In review mode, the state already has fix_approved set by the UI
    # via the LangGraph interrupt mechanism
    approved = state.get("fix_approved")
    event_type = "FIX_APPROVED" if approved else "FIX_REJECTED"
    event = _create_event(event_type, {
        "confidence": state["proposed_fix"]["confidence"] if state["proposed_fix"] else 0,
    })

    logger.info("  Review result: %s", "approved" if approved else "rejected")

    return {
        "session_events": state["session_events"] + [event],
    }


# =============================================================================
# Node: apply_fix
# =============================================================================
def apply_fix(state: AgentState) -> dict[str, Any]:
    """
    Apply the proposed fix by writing the patched content to the file.
    """
    start = time.time()
    proposed_fix = state["proposed_fix"]

    if not proposed_fix:
        logger.warning("⚠️  No fix to apply")
        return {}

    logger.info("📝 Applying fix to %s", proposed_fix["file_path"])

    try:
        from kodex.tools.file_tool import FileTool
        file_tool = FileTool()
        file_tool.execute({
            "action": "write",
            "path": proposed_fix["file_path"],
            "content": proposed_fix["patched_content"],
        })

        duration = (time.time() - start) * 1000
        event = _create_event("FIX_APPLIED", {
            "file": proposed_fix["file_path"],
        }, duration)

        logger.info("  ✅ Fix applied successfully")

        return {
            "session_events": state["session_events"] + [event],
        }

    except Exception as e:
        logger.error("  ❌ Failed to apply fix: %s", str(e))
        event = _create_event("FIX_APPLY_FAILED", {
            "error": str(e),
        }, (time.time() - start) * 1000)

        return {
            "session_events": state["session_events"] + [event],
            "status": "error",
        }


# =============================================================================
# Node: verify_fix
# =============================================================================
def verify_fix(state: AgentState) -> dict[str, Any]:
    """
    Run targeted tests in the Docker sandbox to verify the fix works.
    """
    start = time.time()
    proposed_fix = state["proposed_fix"]

    if not proposed_fix:
        return {"test_results": TestResult(
            passed=False, total=0, failures=0, errors=1,
            duration=0.0, output="No fix to verify", failed_tests=[],
        )}

    logger.info("🧪 Verifying fix in sandbox...")

    try:
        from kodex.tools.sandbox_tool import SandboxTool
        sandbox_tool = SandboxTool()
        result = sandbox_tool.execute({
            "action": "run_tests",
            "repo_path": state["repo_path"],
            "test_path": proposed_fix["file_path"],
        })

        test_result = TestResult(
            passed=result.get("passed", False),
            total=result.get("total", 0),
            failures=result.get("failures", 0),
            errors=result.get("errors", 0),
            duration=result.get("duration", 0.0),
            output=result.get("output", ""),
            failed_tests=result.get("failed_tests", []),
        )

        duration = (time.time() - start) * 1000
        event_type = "TEST_PASSED" if test_result["passed"] else "TEST_FAILED"
        event = _create_event(event_type, {
            "total": test_result["total"],
            "failures": test_result["failures"],
        }, duration)

        logger.info(
            "  Test result: %s (%d/%d passed)",
            "PASS" if test_result["passed"] else "FAIL",
            test_result["total"] - test_result["failures"],
            test_result["total"],
        )

        return {
            "test_results": test_result,
            "session_events": state["session_events"] + [event],
        }

    except Exception as e:
        logger.error("  Sandbox test execution failed: %s", str(e))
        duration = (time.time() - start) * 1000
        event = _create_event("TEST_ERROR", {"error": str(e)}, duration)

        return {
            "test_results": TestResult(
                passed=False, total=0, failures=0, errors=1,
                duration=0.0, output=str(e), failed_tests=[],
            ),
            "session_events": state["session_events"] + [event],
        }


# =============================================================================
# Node: regression_test
# =============================================================================
def regression_test(state: AgentState) -> dict[str, Any]:
    """
    Run the full test suite to check for regressions.
    """
    start = time.time()
    logger.info("🔄 Running regression tests...")

    try:
        from kodex.tools.sandbox_tool import SandboxTool
        sandbox_tool = SandboxTool()
        result = sandbox_tool.execute({
            "action": "run_tests",
            "repo_path": state["repo_path"],
        })

        regression_result = TestResult(
            passed=result.get("passed", False),
            total=result.get("total", 0),
            failures=result.get("failures", 0),
            errors=result.get("errors", 0),
            duration=result.get("duration", 0.0),
            output=result.get("output", ""),
            failed_tests=result.get("failed_tests", []),
        )

        duration = (time.time() - start) * 1000
        event_type = "REGRESSION_CLEAR" if regression_result["passed"] else "REGRESSION_FOUND"
        event = _create_event(event_type, {
            "total": regression_result["total"],
            "failures": regression_result["failures"],
            "failed_tests": regression_result["failed_tests"],
        }, duration)

        logger.info(
            "  Regression result: %s",
            "CLEAR" if regression_result["passed"] else "REGRESSIONS FOUND",
        )

        return {
            "regression_results": regression_result,
            "session_events": state["session_events"] + [event],
        }

    except Exception as e:
        logger.error("  Regression test failed: %s", str(e))
        return {
            "regression_results": TestResult(
                passed=False, total=0, failures=0, errors=1,
                duration=0.0, output=str(e), failed_tests=[],
            ),
            "session_events": state["session_events"] + [_create_event(
                "REGRESSION_ERROR", {"error": str(e)},
                (time.time() - start) * 1000,
            )],
        }


# =============================================================================
# Node: git_commit
# =============================================================================
def git_commit(state: AgentState) -> dict[str, Any]:
    """
    Create a Git branch, commit the fix, and generate a PR description.
    """
    start = time.time()
    proposed_fix = state["proposed_fix"]
    current_error = state["current_error"]

    if not proposed_fix or not current_error:
        return {}

    logger.info("🔀 Creating Git branch and committing fix...")

    try:
        from kodex.tools.git_tool import GitTool
        git_tool = GitTool()

        branch_name = (
            f"kodex/fix-{current_error['code'].lower()}-"
            f"{current_error['file_path'].split('/')[-1].split('.')[0]}-"
            f"{state['session_id'][:8]}"
        )

        result = git_tool.execute({
            "action": "commit_fix",
            "repo_path": state["repo_path"],
            "branch_name": branch_name,
            "file_path": proposed_fix["file_path"],
            "commit_message": (
                f"fix({current_error['code']}): {current_error['message'][:50]}\n\n"
                f"Auto-fix by Kodex (confidence: {proposed_fix['confidence']}%)\n"
                f"Explanation: {proposed_fix['explanation'][:200]}"
            ),
            "pr_description": (
                f"## 🤖 Kodex Auto-Fix\n\n"
                f"**Error:** `{current_error['code']}` in `{current_error['file_path']}`\n"
                f"**Line:** {current_error['line']}\n"
                f"**Message:** {current_error['message']}\n\n"
                f"### Fix Explanation\n{proposed_fix['explanation']}\n\n"
                f"### Confidence: {proposed_fix['confidence']}%\n\n"
                f"### Test Results\n"
                f"- Targeted tests: ✅ Passed\n"
                f"- Regression tests: ✅ Passed\n"
            ),
        })

        duration = (time.time() - start) * 1000
        event = _create_event("GIT_COMMITTED", {
            "branch": branch_name,
            "file": proposed_fix["file_path"],
        }, duration)

        # Add to fix history
        fix_record = {
            "error": current_error,
            "fix": {
                "explanation": proposed_fix["explanation"],
                "confidence": proposed_fix["confidence"],
                "diff": proposed_fix["diff"],
            },
            "branch": branch_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("  ✅ Committed to branch: %s", branch_name)

        return {
            "fix_history": state["fix_history"] + [fix_record],
            "session_events": state["session_events"] + [event],
        }

    except Exception as e:
        logger.error("  Git commit failed: %s", str(e))
        # Still record the fix even if git fails
        fix_record = {
            "error": current_error,
            "fix": {
                "explanation": proposed_fix["explanation"],
                "confidence": proposed_fix["confidence"],
                "diff": proposed_fix["diff"],
            },
            "branch": "git-failed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        return {
            "fix_history": state["fix_history"] + [fix_record],
            "session_events": state["session_events"] + [_create_event(
                "GIT_FAILED", {"error": str(e)},
                (time.time() - start) * 1000,
            )],
        }


# =============================================================================
# Node: rollback
# =============================================================================
def rollback(state: AgentState) -> dict[str, Any]:
    """
    Revert the applied fix and increment the retry counter.
    """
    start = time.time()
    proposed_fix = state["proposed_fix"]

    if not proposed_fix:
        return {"current_retry": state["current_retry"] + 1}

    logger.info("⏪ Rolling back fix for %s", proposed_fix["file_path"])

    try:
        from kodex.tools.file_tool import FileTool
        file_tool = FileTool()
        file_tool.execute({
            "action": "write",
            "path": proposed_fix["file_path"],
            "content": proposed_fix["original_content"],
        })
        logger.info("  Rollback successful")

    except Exception as e:
        logger.error("  Rollback failed: %s", str(e))

    duration = (time.time() - start) * 1000
    event = _create_event("ROLLBACK", {
        "file": proposed_fix["file_path"],
        "retry": state["current_retry"] + 1,
    }, duration)

    return {
        "current_retry": state["current_retry"] + 1,
        "proposed_fix": None,
        "test_results": None,
        "regression_results": None,
        "session_events": state["session_events"] + [event],
    }


# =============================================================================
# Node: next_error
# =============================================================================
def next_error(state: AgentState) -> dict[str, Any]:
    """
    Advance to the next error in the queue.
    """
    next_index = state["current_error_index"] + 1
    errors = state["errors"]

    if next_index < len(errors):
        logger.info(
            "➡️  Moving to error %d/%d",
            next_index + 1, len(errors),
        )
        return {
            "current_error_index": next_index,
            "current_error": errors[next_index],
            "current_retry": 0,
            "proposed_fix": None,
            "fix_approved": None,
            "test_results": None,
            "regression_results": None,
            "retrieved_context": [],
        }
    else:
        logger.info("🏁 All errors processed")
        return {
            "current_error": None,
            "status": "complete",
        }


# =============================================================================
# Node: finalize
# =============================================================================
def finalize(state: AgentState) -> dict[str, Any]:
    """
    Generate the final session summary.
    """
    total_errors = len(state["errors"])
    fixes_applied = len(state["fix_history"])

    logger.info(
        "📊 Session complete — %d/%d errors fixed",
        fixes_applied, total_errors,
    )

    event = _create_event("SESSION_COMPLETE", {
        "total_errors": total_errors,
        "fixes_applied": fixes_applied,
        "token_usage": state["token_usage"],
    })

    return {
        "status": "complete",
        "session_events": state["session_events"] + [event],
    }


# =============================================================================
# Routing Functions (for conditional edges)
# =============================================================================
def check_errors_route(state: AgentState) -> str:
    """Route after error detection: process errors or finalize."""
    if state["errors"]:
        return "retrieve_context"
    return "finalize"


def check_confidence_route(state: AgentState) -> str:
    """Route based on confidence score and mode."""
    settings = get_settings()
    proposed_fix = state["proposed_fix"]

    if not proposed_fix:
        return "skip_error"

    confidence = proposed_fix["confidence"]

    if confidence < settings.confidence_threshold:
        logger.info(
            "  ⚠️  Low confidence (%d%% < %d%%) — skipping",
            confidence, settings.confidence_threshold,
        )
        return "skip_error"

    if state["mode"] == "review":
        return "human_review"

    return "apply_fix"


def verify_route(state: AgentState) -> str:
    """Route after test verification."""
    test_results = state["test_results"]

    if test_results and test_results["passed"]:
        return "regression_test"

    # Tests failed — retry or skip
    if state["current_retry"] < state["max_retries"]:
        return "rollback"

    return "skip_error"


def regression_route(state: AgentState) -> str:
    """Route after regression testing."""
    results = state["regression_results"]

    if results and results["passed"]:
        return "git_commit"

    # Regressions found — rollback
    if state["current_retry"] < state["max_retries"]:
        return "rollback"

    return "skip_error"


def review_route(state: AgentState) -> str:
    """Route after human review."""
    if state.get("fix_approved"):
        return "apply_fix"
    return "skip_error"


def next_error_route(state: AgentState) -> str:
    """Route after processing an error: next error or finalize."""
    if state.get("status") == "complete" or state.get("current_error") is None:
        return "finalize"
    return "retrieve_context"
