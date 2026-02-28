"""Agent configuration schema for ATIF."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class ToolDefinition(BaseModel):
    """Tool/function definition following OpenAI function calling schema."""

    type: str = Field(default="function", description="Type of tool")
    function: Dict[str, Any] = Field(..., description="Function definition with name, description, and parameters")


class AgentSchema(BaseModel):
    """Agent configuration identifying the system used for the trajectory."""

    name: str = Field(..., description="Agent system name (e.g., 'terraform-agent')")
    version: str = Field(..., description="Agent system version (e.g., '1.0.0')")
    model_name: Optional[str] = Field(None, description="Default LLM model for this trajectory")
    tool_definitions: Optional[List[ToolDefinition]] = Field(None, description="Array of available tool definitions")
    extra: Optional[Dict[str, Any]] = Field(None, description="Custom agent configuration")

    class Config:
        extra = "allow"
