"""Dataset schema definitions and validation."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class Difficulty(str, Enum):
    """Difficulty levels for benchmark instances."""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


@dataclass
class InstanceMetadata:
    """Metadata for a benchmark instance."""
    estimated_cost: str
    deployment_time_seconds: int
    cleanup_required: bool = True
    created_at: Optional[str] = None
    author: str = "terraform-bench"


@dataclass
class BenchmarkInstance:
    """Schema for a single benchmark instance."""
    instance_id: str
    problem_statement: str
    difficulty: Difficulty
    tags: List[str]
    provider: str
    region: str
    expected_resources: Dict[str, int]
    validation_script: str
    metadata: InstanceMetadata
    required_outputs: List[str] = field(default_factory=list)
    gold_solution: Dict[str, str] = field(default_factory=dict)
    hints: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BenchmarkInstance':
        """Create instance from dictionary."""
        metadata = InstanceMetadata(**data.get('metadata', {}))

        return cls(
            instance_id=data['instance_id'],
            problem_statement=data['problem_statement'],
            difficulty=Difficulty(data['difficulty']),
            tags=data['tags'],
            provider=data['provider'],
            region=data['region'],
            expected_resources=data['expected_resources'],
            validation_script=data['validation_script'],
            metadata=metadata,
            required_outputs=data.get('required_outputs', []),
            gold_solution=data.get('gold_solution', {}),
            hints=data.get('hints', [])
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert instance to dictionary."""
        return {
            'instance_id': self.instance_id,
            'problem_statement': self.problem_statement,
            'difficulty': self.difficulty.value,
            'tags': self.tags,
            'provider': self.provider,
            'region': self.region,
            'expected_resources': self.expected_resources,
            'required_outputs': self.required_outputs,
            'validation_script': self.validation_script,
            'gold_solution': self.gold_solution,
            'hints': self.hints,
            'metadata': {
                'estimated_cost': self.metadata.estimated_cost,
                'deployment_time_seconds': self.metadata.deployment_time_seconds,
                'cleanup_required': self.metadata.cleanup_required,
                'created_at': self.metadata.created_at,
                'author': self.metadata.author
            }
        }


def validate_instance(instance: Dict[str, Any]) -> List[str]:
    """
    Validate a benchmark instance against the schema.

    Args:
        instance: Dictionary representation of instance

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Required fields
    required_fields = [
        'instance_id', 'problem_statement', 'difficulty', 'tags',
        'provider', 'region', 'expected_resources', 'validation_script',
        'metadata'
    ]

    for field in required_fields:
        if field not in instance:
            errors.append(f"Missing required field: {field}")

    # Validate difficulty
    if 'difficulty' in instance:
        if instance['difficulty'] not in ['easy', 'medium', 'hard']:
            errors.append(f"Invalid difficulty: {instance['difficulty']}")

    # Validate instance_id format
    if 'instance_id' in instance:
        parts = instance['instance_id'].split('-')
        if len(parts) < 3 or parts[0] != 'terraform':
            errors.append(f"Invalid instance_id format: {instance['instance_id']}")

    # Validate tags is a list
    if 'tags' in instance and not isinstance(instance['tags'], list):
        errors.append("tags must be a list")

    # Validate expected_resources is a dict
    if 'expected_resources' in instance:
        if not isinstance(instance['expected_resources'], dict):
            errors.append("expected_resources must be a dictionary")
        else:
            for key, value in instance['expected_resources'].items():
                if not isinstance(value, int) or value < 0:
                    errors.append(f"expected_resources[{key}] must be a non-negative integer")

    # Validate metadata
    if 'metadata' in instance:
        meta = instance['metadata']
        if not isinstance(meta, dict):
            errors.append("metadata must be a dictionary")
        else:
            if 'estimated_cost' not in meta:
                errors.append("metadata.estimated_cost is required")
            if 'deployment_time_seconds' not in meta:
                errors.append("metadata.deployment_time_seconds is required")
            elif not isinstance(meta['deployment_time_seconds'], int):
                errors.append("metadata.deployment_time_seconds must be an integer")

    return errors
