"""Tool call schema for ATIF."""

from typing import Dict, Any
from pydantic import BaseModel, Field


class ToolCallSchema(BaseModel):
    """Structured tool/function invocation."""

    tool_call_id: str = Field(..., description="Unique identifier for this tool call")
    function_name: str = Field(..., description="Name of the function or tool")
    arguments: Dict[str, Any] = Field(..., description="Arguments passed to the function")
