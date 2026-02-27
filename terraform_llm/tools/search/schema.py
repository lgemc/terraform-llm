"""Schema for Terraform documentation chunks."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TerraformDoc:
    """
    Represents a parsed Terraform resource documentation.

    This schema captures the structured information from provider docs
    for efficient indexing and retrieval.
    """

    # Resource identity
    resource_id: str  # e.g., "aws_lambda_alias"
    provider: str  # e.g., "aws", "google", "azurerm"

    # Metadata
    subcategory: str  # e.g., "Lambda", "S3", "Compute"
    page_title: str  # e.g., "AWS: aws_lambda_alias"
    description: str  # Short description

    # Full documentation content
    full_text: str  # Complete markdown content

    # Structured sections
    overview: str = ""  # Introduction/overview section
    examples: list[dict[str, str]] = field(default_factory=list)  # [{"title": "...", "code": "..."}]

    # Arguments and attributes
    arguments_required: list[str] = field(default_factory=list)  # e.g., ["function_name", "name"]
    arguments_optional: list[str] = field(default_factory=list)  # e.g., ["description", "routing_config"]
    argument_descriptions: dict[str, str] = field(default_factory=dict)  # arg -> description

    attributes: list[str] = field(default_factory=list)  # Exported attributes
    attribute_descriptions: dict[str, str] = field(default_factory=dict)  # attr -> description

    # Source file info
    source_file: Optional[str] = None  # Path to original markdown file

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "resource_id": self.resource_id,
            "provider": self.provider,
            "subcategory": self.subcategory,
            "page_title": self.page_title,
            "description": self.description,
            "full_text": self.full_text,
            "overview": self.overview,
            "examples": self.examples,
            "arguments_required": self.arguments_required,
            "arguments_optional": self.arguments_optional,
            "argument_descriptions": self.argument_descriptions,
            "attributes": self.attributes,
            "attribute_descriptions": self.attribute_descriptions,
            "source_file": self.source_file,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TerraformDoc":
        """Create from dictionary."""
        return cls(**data)

    def get_searchable_chunks(self) -> list[dict[str, str]]:
        """
        Break document into searchable chunks for embedding.

        Returns:
            List of chunks with metadata: [{"text": "...", "type": "...", "title": "..."}]
        """
        chunks = []

        # Overview chunk
        if self.overview:
            chunks.append({
                "text": f"{self.resource_id}: {self.overview}",
                "type": "overview",
                "title": self.page_title,
            })

        # Example chunks
        for example in self.examples:
            chunks.append({
                "text": f"{example.get('title', 'Example')}\n{example.get('code', '')}",
                "type": "example",
                "title": example.get("title", "Example"),
            })

        # Argument chunks
        for arg, desc in self.argument_descriptions.items():
            chunks.append({
                "text": f"{self.resource_id}.{arg}: {desc}",
                "type": "argument",
                "title": arg,
            })

        # If no structured chunks, use full text
        if not chunks:
            chunks.append({
                "text": self.full_text,
                "type": "full_doc",
                "title": self.page_title,
            })

        return chunks
