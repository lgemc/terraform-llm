"""Observation schema for ATIF."""

from typing import List
from pydantic import BaseModel, Field

from .observation_result import ObservationResultSchema


class ObservationSchema(BaseModel):
    """Environment feedback/result container."""

    results: List[ObservationResultSchema] = Field(..., description="Array of observation results")
