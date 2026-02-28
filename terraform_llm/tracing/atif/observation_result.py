"""Observation result schema for ATIF."""

from typing import Optional, List, Union
from pydantic import BaseModel, Field

from .content import ContentPart
from .subagent_trajectory_ref import SubagentTrajectoryRefSchema


class ObservationResultSchema(BaseModel):
    """Individual observation result from tool execution or action."""

    source_call_id: Optional[str] = Field(None, description="Tool call ID this result corresponds to")
    content: Optional[Union[str, List[ContentPart]]] = Field(None, description="Output from tool execution")
    subagent_trajectory_ref: Optional[List[SubagentTrajectoryRefSchema]] = Field(
        None, description="References to delegated subagent trajectories"
    )

    class Config:
        extra = "allow"
