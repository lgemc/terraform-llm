"""Subagent trajectory reference schema for ATIF."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class SubagentTrajectoryRefSchema(BaseModel):
    """Reference to a delegated subagent trajectory."""

    session_id: str = Field(..., description="Session ID of the subagent trajectory")
    trajectory_path: Optional[str] = Field(None, description="Path to subagent trajectory file")
    extra: Optional[Dict[str, Any]] = Field(None, description="Custom subagent metadata")

    class Config:
        extra = "allow"
