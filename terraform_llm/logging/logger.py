"""Logging abstraction for terraform-agent."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from enum import Enum
from datetime import datetime
import json
import sys


class LogLevel(str, Enum):
    """Log severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Logger(ABC):
    """Abstract base class for logging."""

    @abstractmethod
    def log(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an event with optional data.

        Args:
            level: Log severity level
            event: Event name/identifier
            message: Human-readable message
            data: Optional metadata dictionary
        """
        pass

    def debug(self, event: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message."""
        self.log(LogLevel.DEBUG, event, message, data)

    def info(self, event: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Log info message."""
        self.log(LogLevel.INFO, event, message, data)

    def warning(self, event: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message."""
        self.log(LogLevel.WARNING, event, message, data)

    def error(self, event: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Log error message."""
        self.log(LogLevel.ERROR, event, message, data)

    def critical(self, event: str, message: str = "", data: Optional[Dict[str, Any]] = None) -> None:
        """Log critical message."""
        self.log(LogLevel.CRITICAL, event, message, data)


class ConsoleLogger(Logger):
    """Console logger with colored output and structured formatting."""

    # ANSI color codes
    COLORS = {
        LogLevel.DEBUG: "\033[36m",      # Cyan
        LogLevel.INFO: "\033[32m",       # Green
        LogLevel.WARNING: "\033[33m",    # Yellow
        LogLevel.ERROR: "\033[31m",      # Red
        LogLevel.CRITICAL: "\033[35m",   # Magenta
    }
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Icons for event types
    ICONS = {
        "run.started": "🚀",
        "run.completed": "✅",
        "dataset.loading": "📂",
        "dataset.loaded": "📊",
        "instance.started": "🔨",
        "instance.completed": "✓",
        "generation.started": "🤖",
        "generation.attempt": "🔄",
        "generation.succeeded": "✨",
        "generation.failed": "❌",
        "execution.started": "⚙️",
        "execution.success": "✅",
        "execution.failed": "⚠️",
        "execution.exhausted": "❌",
        "terraform.init": "📦",
        "terraform.validate": "✓",
        "terraform.plan": "📋",
        "terraform.apply": "🚀",
        "validation.completed": "🔍",
        "cleanup.completed": "🧹",
        "cleanup.requested": "🧹",
        "instance.error": "❌",
    }

    def __init__(
        self,
        min_level: LogLevel = LogLevel.INFO,
        colored: bool = True,
        show_timestamp: bool = False,
        show_data: bool = True,
        compact: bool = False
    ):
        """
        Initialize console logger.

        Args:
            min_level: Minimum log level to display
            colored: Whether to use colored output
            show_timestamp: Whether to show timestamps
            show_data: Whether to show data field
            compact: Whether to use compact mode (less visual)
        """
        self.min_level = min_level
        self.colored = colored and sys.stdout.isatty()
        self.show_timestamp = show_timestamp
        self.show_data = show_data
        self.compact = compact

        # Level ordering for filtering
        self.level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }

    def log(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an event to console."""
        # Filter by level
        if self.level_order[level] < self.level_order[self.min_level]:
            return

        # Special formatting for major events
        if event in ["instance.started", "instance.completed", "run.started", "run.completed"]:
            self._log_major_event(level, event, message, data)
        elif event.startswith("terraform.") or event.startswith("generation.") or event.startswith("execution."):
            self._log_step_event(level, event, message, data)
        else:
            self._log_standard(level, event, message, data)

    def _log_standard(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Standard log format."""
        parts = []

        # Timestamp
        if self.show_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            if self.colored:
                parts.append(f"{self.DIM}{timestamp}{self.RESET}")
            else:
                parts.append(timestamp)

        # Icon
        icon = self.ICONS.get(event, "•")
        parts.append(icon)

        # Message
        if self.colored:
            color = self.COLORS.get(level, "")
            parts.append(f"{color}{message or event}{self.RESET}")
        else:
            parts.append(message or event)

        # Data (compact)
        if data and self.show_data and not self.compact:
            key_data = self._extract_key_data(data)
            if key_data:
                if self.colored:
                    parts.append(f"{self.DIM}({key_data}){self.RESET}")
                else:
                    parts.append(f"({key_data})")

        print("  " + " ".join(parts))

    def _log_major_event(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Format for major events with visual separation."""
        if event == "instance.started":
            print()
            print("─" * 70)
            instance_id = data.get("instance_id", "unknown") if data else "unknown"
            difficulty = data.get("difficulty", "").upper() if data else ""
            if self.colored:
                print(f"🔨 {self.BOLD}{instance_id}{self.RESET} {self.DIM}[{difficulty}]{self.RESET}")
            else:
                print(f"🔨 {instance_id} [{difficulty}]")
            print("─" * 70)
        elif event == "instance.completed":
            passed = data.get("passed", False) if data else False
            if passed:
                if self.colored:
                    print(f"\n{self.COLORS[LogLevel.INFO]}✅ PASSED{self.RESET}")
                else:
                    print("\n✅ PASSED")
            else:
                if self.colored:
                    print(f"\n{self.COLORS[LogLevel.ERROR]}❌ FAILED{self.RESET}")
                else:
                    print("\n❌ FAILED")
        elif event == "run.started":
            print()
            print("=" * 70)
            if self.colored:
                print(f"{self.BOLD}🚀 Terraform Agent Benchmark Run{self.RESET}")
            else:
                print("🚀 Terraform Agent Benchmark Run")
            print("=" * 70)
            if message:
                print(f"📁 {message}")
        elif event == "run.completed":
            print()
            print("=" * 70)
            if self.colored:
                print(f"{self.BOLD}✅ Run Completed{self.RESET}")
            else:
                print("✅ Run Completed")
            if message:
                print(f"   {message}")
            print("=" * 70)
            print()

    def _log_step_event(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Format for step events with indentation."""
        icon = self.ICONS.get(event, "  ▸")

        if self.colored:
            color = self.COLORS.get(level, "")
            status = f"{color}{message}{self.RESET}" if message else event
        else:
            status = message or event

        parts = [icon, status]

        # Add key info
        if data and not self.compact:
            if event.startswith("terraform."):
                success = data.get("success")
                if success is not None:
                    if success:
                        parts.append("✓" if not self.colored else f"{self.COLORS[LogLevel.INFO]}✓{self.RESET}")
                    else:
                        parts.append("✗" if not self.colored else f"{self.COLORS[LogLevel.ERROR]}✗{self.RESET}")
            elif event == "generation.succeeded":
                files = data.get("files", [])
                if files:
                    parts.append(f"({len(files)} files)")

        print("  " + " ".join(parts))

    def _extract_key_data(self, data: Dict[str, Any]) -> str:
        """Extract most important data for display."""
        # Priority keys to show
        priority = ["count", "total", "passed", "failed", "iterations"]

        key_items = []
        for key in priority:
            if key in data:
                key_items.append(f"{key}={data[key]}")

        return ", ".join(key_items) if key_items else ""

    def _format_data(self, data: Dict[str, Any]) -> str:
        """Format data dictionary for display."""
        # Keep it compact
        items = []
        for key, value in data.items():
            # Truncate long values
            if isinstance(value, str) and len(value) > 50:
                value = value[:47] + "..."
            elif isinstance(value, (list, dict)):
                value = json.dumps(value)
                if len(value) > 50:
                    value = value[:47] + "..."
            items.append(f"{key}={value}")

        return f"[{', '.join(items)}]"


class NullLogger(Logger):
    """Logger that does nothing (for testing or disabling logging)."""

    def log(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Do nothing."""
        pass


class FileLogger(Logger):
    """Logger that writes JSON lines to a file."""

    def __init__(self, file_path: str, min_level: LogLevel = LogLevel.INFO):
        """
        Initialize file logger.

        Args:
            file_path: Path to log file
            min_level: Minimum log level to write
        """
        self.file_path = file_path
        self.min_level = min_level

        # Level ordering for filtering
        self.level_order = {
            LogLevel.DEBUG: 0,
            LogLevel.INFO: 1,
            LogLevel.WARNING: 2,
            LogLevel.ERROR: 3,
            LogLevel.CRITICAL: 4,
        }

    def log(
        self,
        level: LogLevel,
        event: str,
        message: str = "",
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log an event to file as JSON."""
        # Filter by level
        if self.level_order[level] < self.level_order[self.min_level]:
            return

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "event": event,
            "message": message,
        }

        if data:
            log_entry["data"] = data

        # Append to file
        with open(self.file_path, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
