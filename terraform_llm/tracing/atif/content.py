"""Multimodal content models for ATIF v1.6+."""

from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ImageSource(BaseModel):
    """Image source specification for multimodal content."""

    media_type: Literal["image/jpeg", "image/png", "image/gif", "image/webp"] = Field(
        ..., description="MIME type of the image"
    )
    path: str = Field(..., description="File path or URL to the image")


class ContentPart(BaseModel):
    """Content part for multimodal messages (text or image)."""

    type: Literal["text", "image"] = Field(..., description="Content type")
    text: Optional[str] = Field(None, description="Text content (required when type is 'text')")
    source: Optional[ImageSource] = Field(None, description="Image source (required when type is 'image')")

    @model_validator(mode='after')
    def validate_content(self) -> 'ContentPart':
        """Validate that text is provided for text type and source for image type."""
        if self.type == "text" and self.text is None:
            raise ValueError("text field is required when type is 'text'")
        if self.type == "image" and self.source is None:
            raise ValueError("source field is required when type is 'image'")
        if self.type == "text" and self.source is not None:
            raise ValueError("source field must be omitted when type is 'text'")
        if self.type == "image" and self.text is not None:
            raise ValueError("text field must be omitted when type is 'image'")
        return self
