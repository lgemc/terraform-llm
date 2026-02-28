"""LLM metrics schema for ATIF."""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class MetricsSchema(BaseModel):
    """LLM operational and confidence data for a single step."""

    prompt_tokens: Optional[int] = Field(None, description="Total input tokens (cached + non-cached)")
    completion_tokens: Optional[int] = Field(None, description="Total tokens generated")
    cached_tokens: Optional[int] = Field(None, description="Subset of prompt_tokens served from cache")
    cost_usd: Optional[float] = Field(None, description="Monetary cost for this step in USD")
    prompt_token_ids: Optional[List[int]] = Field(None, description="Token IDs for prompt")
    completion_token_ids: Optional[List[int]] = Field(None, description="Token IDs for completion")
    logprobs: Optional[List[float]] = Field(None, description="Log probabilities for completion tokens")
    extra: Optional[Dict[str, Any]] = Field(None, description="Provider-specific metrics")

    class Config:
        extra = "allow"
