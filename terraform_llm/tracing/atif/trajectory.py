"""Root trajectory schema for ATIF."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, field_validator

from .agent import AgentSchema
from .final_metrics import FinalMetricsSchema
from .step import StepObject


class Trajectory(BaseModel):
    """ATIF v1.6 compliant trajectory."""

    schema_version: str = Field(default="ATIF-v1.6", description="ATIF version")
    session_id: str = Field(..., description="Unique identifier for the agent run")
    agent: AgentSchema = Field(..., description="Agent configuration")
    steps: List[StepObject] = Field(..., description="Complete interaction history")
    notes: Optional[str] = Field(None, description="Custom notes or explanations")
    final_metrics: Optional[FinalMetricsSchema] = Field(None, description="Aggregate trajectory metrics")
    continued_trajectory_ref: Optional[str] = Field(None, description="Reference to continuation trajectory")
    extra: Optional[Dict[str, Any]] = Field(None, description="Custom root-level metadata")

    @field_validator('steps')
    @classmethod
    def validate_step_ids(cls, v: List[StepObject]) -> List[StepObject]:
        """Validate that step IDs are sequential starting from 1."""
        for idx, step in enumerate(v, start=1):
            if step.step_id != idx:
                raise ValueError(f"Step IDs must be sequential starting from 1. Expected {idx}, got {step.step_id}")
        return v

    @field_validator('steps')
    @classmethod
    def validate_tool_call_references(cls, v: List[StepObject]) -> List[StepObject]:
        """Validate that observation source_call_ids reference existing tool_call_ids."""
        # Collect all tool_call_ids from all steps
        all_tool_call_ids = set()
        for step in v:
            if step.tool_calls:
                for tool_call in step.tool_calls:
                    all_tool_call_ids.add(tool_call.tool_call_id)

        # Validate observations reference existing tool calls
        for step in v:
            if step.observation:
                for result in step.observation.results:
                    if result.source_call_id is not None and result.source_call_id not in all_tool_call_ids:
                        raise ValueError(
                            f"Observation source_call_id '{result.source_call_id}' does not reference "
                            f"any existing tool_call_id"
                        )
        return v

    def has_multimodal_content(self) -> bool:
        """Check if trajectory contains multimodal content (images)."""
        from .content import ContentPart

        for step in self.steps:
            if isinstance(step.message, list):
                for part in step.message:
                    if isinstance(part, ContentPart) and part.type == "image":
                        return True

            if step.observation:
                for result in step.observation.results:
                    if isinstance(result.content, list):
                        for part in result.content:
                            if isinstance(part, ContentPart) and part.type == "image":
                                return True

        return False

    def to_json_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        data = self.model_dump(exclude_none=exclude_none)
        return data

    class Config:
        extra = "allow"
