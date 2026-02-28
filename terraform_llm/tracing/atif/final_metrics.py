"""Final metrics schema for ATIF."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class FinalMetricsSchema(BaseModel):
    """Aggregate statistics for the entire trajectory."""

    total_prompt_tokens: Optional[int] = Field(None, description="Sum of all prompt tokens")
    total_completion_tokens: Optional[int] = Field(None, description="Sum of all completion tokens")
    total_cached_tokens: Optional[int] = Field(None, description="Sum of all cached tokens")
    total_cost_usd: Optional[float] = Field(None, description="Total monetary cost in USD")
    total_steps: Optional[int] = Field(None, description="Total number of steps")
    extra: Optional[Dict[str, Any]] = Field(None, description="Custom aggregate metrics")

    class Config:
        extra = "allow"
