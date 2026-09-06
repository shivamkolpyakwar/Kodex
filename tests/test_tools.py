"""
Tests for the Kodex Tools module.

Tests the tool registry, file tool, and custom tool loading.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from kodex.tools.file_tool import FileTool
from kodex.tools.registry import BaseTool, CustomTool, ToolExecutionError, ToolRegistry


class TestToolRegistry:
    """Tests for the ToolRegistry."""

    def test_register_and_get_tool(self) -> None:
        """Test registering and retrieving a tool."""
        registry = ToolRegistry()

        class MockTool(BaseTool):
            @property
            def name(self) -> str:
                return "mock_tool"

            @property
            def description(self) -> str:
                return "A mock tool for testing."

            def execute(self, args: dict[str, Any]) -> dict[str, Any]:
                return {"result": "ok"}

        tool = MockTool()
        registry.register(tool)

        assert registry.get("mock_tool") is tool
        assert registry.get("nonexistent") is None

    def test_list_tools(self) -> None:
        """Test listing all registered tools."""
        registry = ToolRegistry()

        class ToolA(BaseTool):
            @property
            def name(self) -> str:
                return "tool_a"

            @property
            def description(self) -> str:
                return "Tool A"

            def execute(self, args: dict[str, Any]) -> dict[str, Any]:
                return {}

        class ToolB(BaseTool):
            @property
            def name(self) -> str:
                return "tool_b"

            @property
            def description(self) -> str:
                return "Tool B"

            def execute(self, args: dict[str, Any]) -> dict[str, Any]:
                return {}

        registry.register(ToolA())
        registry.register(ToolB())

        tools = registry.list_tools()
        names = [t["name"] for t in tools]

        assert "tool_a" in names
        assert "tool_b" in names
        assert len(tools) == 2

    def test_execute_tool(self) -> None:
        """Test executing a tool by name."""
        registry = ToolRegistry()

        class EchoTool(BaseTool):
            @property
            def name(self) -> str:
                return "echo"

            @property
            def description(self) -> str:
                return "Echo input."

            def execute(self, args: dict[str, Any]) -> dict[str, Any]:
                return {"echoed": args.get("message", "")}

        registry.register(EchoTool())
        result = registry.execute("echo", {"message": "hello"})

        assert result["echoed"] == "hello"

    def test_execute_nonexistent_tool(self) -> None:
        """Test executing a non-existent tool raises ToolExecutionError."""
        registry = ToolRegistry()

        with pytest.raises(ToolExecutionError):
            registry.execute("nonexistent_tool", {})

    def test_load_custom_tools_from_yaml(self) -> None:
        """Test loading custom tools from a YAML file."""
        yaml_content = """
custom_tools:
  - name: "test_custom_tool"
    description: "A test custom tool"
    command: "echo {message}"
    timeout: 5
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False,
        ) as f:
            f.write(yaml_content)
            f.flush()

            registry = ToolRegistry()
            registry.load_custom_tools(f.name)

            tool = registry.get("test_custom_tool")
            assert tool is not None
            assert tool.name == "test_custom_tool"

        Path(f.name).unlink()

    def test_load_custom_tools_missing_file(self) -> None:
        """Test loading from a non-existent YAML file doesn't crash."""
        registry = ToolRegistry()
        registry.load_custom_tools("/nonexistent/path/config.yaml")
        # Should just log and continue
        assert len(registry.list_tools()) == 0


class TestCustomTool:
    """Tests for the CustomTool class."""

    def test_execute_simple_command(self) -> None:
        """Test executing a simple echo command."""
        tool = CustomTool(
            tool_name="test_echo",
            tool_description="Test echo",
            command_template="echo {message}",
            timeout=5,
        )

        result = tool.execute({"message": "hello_world"})
        assert result["exit_code"] == 0
        assert "hello_world" in result["stdout"]

    def test_execute_timeout(self) -> None:
        """Test that timeout is enforced."""
        tool = CustomTool(
            tool_name="slow_tool",
            tool_description="Slow tool",
            command_template="sleep 10",
            timeout=1,
        )

        with pytest.raises(ToolExecutionError):
            tool.execute({})


class TestFileTool:
    """Tests for the FileTool."""

    def test_read_file(self) -> None:
        """Test reading a file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False,
        ) as f:
            f.write("line1\nline2\nline3\n")
            f.flush()

            tool = FileTool()
            result = tool.execute({"action": "read", "path": f.name})

            assert result["content"] == "line1\nline2\nline3\n"
            assert result["total_lines"] == 3

        Path(f.name).unlink()

    def test_write_file(self) -> None:
        """Test writing to a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = str(Path(tmpdir) / "output.py")

            tool = FileTool()
            result = tool.execute({
                "action": "write",
                "path": file_path,
                "content": "x = 42\n",
                "backup": False,
            })

            assert result["written"] is True
            assert Path(file_path).read_text() == "x = 42\n"

    def test_diff_files(self) -> None:
        """Test generating a diff."""
        tool = FileTool()
        result = tool.execute({
            "action": "diff",
            "original": "x = 1\ny = 2\n",
            "modified": "x = 1\ny = 3\n",
            "path": "test.py",
        })

        assert result["has_changes"] is True
        assert result["additions"] >= 1
        assert result["deletions"] >= 1

    def test_read_nonexistent_file(self) -> None:
        """Test reading a non-existent file raises error."""
        tool = FileTool()
        with pytest.raises(ToolExecutionError):
            tool.execute({"action": "read", "path": "/nonexistent/file.py"})

    def test_invalid_action(self) -> None:
        """Test invalid action raises error."""
        tool = FileTool()
        with pytest.raises(ToolExecutionError):
            tool.execute({"action": "invalid_action"})
