"""Step object schema for ATIF."""

from typing import Optional, Union, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime

from .content import ContentPart
from .metrics import MetricsSchema
from .observation import ObservationSchema
from .tool_call import ToolCallSchema


class StepObject(BaseModel):
    """Single interaction step in the trajectory."""

    step_id: int = Field(..., description="Ordinal index starting from 1", ge=1)
    timestamp: Optional[str] = Field(None, description="ISO 8601 timestamp")
    source: Literal["system", "user", "agent"] = Field(..., description="Step originator")
    model_name: Optional[str] = Field(None, description="LLM model for this step (agent only)")
    reasoning_effort: Optional[Union[str, float]] = Field(None, description="Reasoning effort measure (agent only)")
    message: Union[str, List[ContentPart]] = Field(..., description="Dialogue message or multimodal content")
    reasoning_content: Optional[str] = Field(None, description="Internal reasoning (agent only)")
    tool_calls: Optional[List[ToolCallSchema]] = Field(None, description="Tool invocations (agent only)")
    observation: Optional[ObservationSchema] = Field(None, description="Environment feedback")
    metrics: Optional[MetricsSchema] = Field(None, description="LLM metrics (agent only)")
    extra: Optional[Dict[str, Any]] = Field(None, description="Custom step metadata")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: Optional[str]) -> Optional[str]:
        """Validate ISO 8601 timestamp format."""
        if v is not None:
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
            except ValueError as e:
                raise ValueError(f"Invalid ISO 8601 timestamp: {v}") from e
        return v

    @field_validator('model_name', 'reasoning_effort', 'reasoning_content', 'tool_calls', 'metrics')
    @classmethod
    def validate_agent_only_fields(cls, v: Any, info) -> Any:
        """Validate that certain fields are only used with agent steps."""
        if v is not None and info.data.get('source') != 'agent':
            field_name = info.field_name
            raise ValueError(f"{field_name} is only applicable when source is 'agent'")
        return v

    class Config:
        extra = "allow"
