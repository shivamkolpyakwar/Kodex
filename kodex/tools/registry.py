"""
Kodex Tool Registry.

Manages the dynamic loading and registration of built-in and
user-defined custom tools. Tools are loaded from Python modules
and from a YAML configuration file.
"""

from __future__ import annotations

import logging
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml

from kodex.config import PROJECT_ROOT

logger = logging.getLogger(__name__)


# =============================================================================
# Base Tool Protocol
# =============================================================================
class BaseTool(ABC):
    """
    Abstract base class for all Kodex tools.

    Every tool must implement:
    - name: Unique identifier
    - description: Human-readable description
    - execute(args): Perform the tool's action
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the tool does."""
        ...

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute the tool with given arguments.

        Args:
            args: Tool-specific arguments.

        Returns:
            Dict with tool results.

        Raises:
            ToolExecutionError: If execution fails.
        """
        ...


class ToolExecutionError(Exception):
    """Raised when a tool execution fails."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' failed: {message}")


# =============================================================================
# Custom Tool (loaded from YAML)
# =============================================================================
class CustomTool(BaseTool):
    """
    A tool defined in tools_config.yaml.

    Executes a shell command template with variable substitution.
    """

    def __init__(
        self,
        tool_name: str,
        tool_description: str,
        command_template: str,
        timeout: int = 30,
        language: str = "",
    ) -> None:
        self._name = tool_name
        self._description = tool_description
        self._command_template = command_template
        self._timeout = timeout
        self._language = language

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def execute(self, args: dict[str, Any]) -> dict[str, Any]:
        """Execute the command template with variable substitution."""
        try:
            # Substitute variables in the command template
            command = self._command_template
            for key, value in args.items():
                command = command.replace(f"{{{key}}}", str(value))

            # Check for unresolved variables
            if "{" in command and "}" in command:
                missing = [
                    s.split("}")[0]
                    for s in command.split("{")[1:]
                    if "}" in s
                ]
                raise ToolExecutionError(
                    self._name,
                    f"Missing variables: {missing}",
                )

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "command": command,
            }

        except subprocess.TimeoutExpired:
            raise ToolExecutionError(
                self._name,
                f"Command timed out after {self._timeout}s",
            )

        except Exception as e:
            raise ToolExecutionError(self._name, str(e))


# =============================================================================
# Tool Registry
# =============================================================================
class ToolRegistry:
    """
    Central registry for all available tools.

    Loads built-in tools and custom tools from YAML configuration.
    Provides lookup by name and listing capabilities.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """
        Register a tool in the registry.

        Args:
            tool: Tool instance to register.
        """
        if tool.name in self._tools:
            logger.warning("Tool '%s' already registered — overwriting", tool.name)

        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """List all registered tools."""
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute.
            args: Arguments to pass to the tool.

        Returns:
            Tool execution results.

        Raises:
            ToolExecutionError: If tool not found or execution fails.
        """
        tool = self.get(tool_name)
        if not tool:
            raise ToolExecutionError(tool_name, "Tool not found in registry")

        try:
            return tool.execute(args)
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(tool_name, str(e))

    def load_builtin_tools(self) -> None:
        """Load all built-in tools."""
        from kodex.tools.file_tool import FileTool
        from kodex.tools.git_tool import GitTool
        from kodex.tools.lint_tool import LintTool
        from kodex.tools.sandbox_tool import SandboxTool
        from kodex.tools.test_tool import TestTool

        builtins = [LintTool(), TestTool(), GitTool(), FileTool(), SandboxTool()]

        for tool in builtins:
            self.register(tool)

        logger.info("Loaded %d built-in tools", len(builtins))

    def load_custom_tools(self, config_path: str | None = None) -> None:
        """
        Load custom tools from a YAML configuration file.

        Args:
            config_path: Path to tools_config.yaml.
                Defaults to project root.
        """
        path = Path(config_path) if config_path else PROJECT_ROOT / "tools_config.yaml"

        if not path.exists():
            logger.info("No custom tools config found at %s", path)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            tools = config.get("custom_tools", [])
            loaded = 0

            for tool_def in tools:
                try:
                    tool = CustomTool(
                        tool_name=tool_def["name"],
                        tool_description=tool_def["description"],
                        command_template=tool_def["command"],
                        timeout=tool_def.get("timeout", 30),
                        language=tool_def.get("language", ""),
                    )
                    self.register(tool)
                    loaded += 1
                except KeyError as e:
                    logger.warning(
                        "Invalid custom tool definition (missing %s): %s",
                        str(e), tool_def.get("name", "unknown"),
                    )

            logger.info("Loaded %d custom tools from %s", loaded, path)

        except yaml.YAMLError as e:
            logger.error("Failed to parse tools config: %s", str(e))
        except Exception as e:
            logger.error("Failed to load custom tools: %s", str(e))


# =============================================================================
# Global Registry Factory
# =============================================================================
def create_tool_registry(config_path: str | None = None) -> ToolRegistry:
    """
    Create and populate a tool registry with all available tools.

    Args:
        config_path: Optional path to custom tools YAML.

    Returns:
        Fully loaded ToolRegistry instance.
    """
    registry = ToolRegistry()
    registry.load_builtin_tools()
    registry.load_custom_tools(config_path)

    logger.info(
        "Tool registry ready: %d tools available",
        len(registry.list_tools()),
    )

    return registry
