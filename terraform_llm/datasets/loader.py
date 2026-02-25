"""Dataset loading and management."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterator, Union

from .schema import BenchmarkInstance, validate_instance
from .dataset import Dataset


class DatasetLoader:
    """Load and manage benchmark datasets in JSONL format."""

    def __init__(self, dataset_path: str):
        """
        Initialize dataset loader.

        Args:
            dataset_path: Path to JSONL dataset file
        """
        self.dataset_path = Path(dataset_path)
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    def load(self, validate: bool = True, return_dataset: bool = True) -> Union[List[BenchmarkInstance], Dataset]:
        """
        Load complete dataset into memory.

        Args:
            validate: Whether to validate instances against schema
            return_dataset: If True, return Dataset object; if False, return list

        Returns:
            Dataset object or list of BenchmarkInstance objects
        """
        instances = []

        for line_num, instance_dict in enumerate(self._read_jsonl(), start=1):
            if validate:
                errors = validate_instance(instance_dict)
                if errors:
                    raise ValueError(
                        f"Validation errors at line {line_num}:\n" +
                        "\n".join(f"  - {e}" for e in errors)
                    )

            try:
                instance = BenchmarkInstance.from_dict(instance_dict)
                instances.append(instance)
            except Exception as e:
                raise ValueError(f"Error parsing instance at line {line_num}: {e}")

        if return_dataset:
            return Dataset(instances)
        return instances

    def stream(self, validate: bool = True) -> Iterator[BenchmarkInstance]:
        """
        Stream instances one at a time (memory efficient).

        Args:
            validate: Whether to validate instances against schema

        Yields:
            BenchmarkInstance objects
        """
        for line_num, instance_dict in enumerate(self._read_jsonl(), start=1):
            if validate:
                errors = validate_instance(instance_dict)
                if errors:
                    raise ValueError(
                        f"Validation errors at line {line_num}:\n" +
                        "\n".join(f"  - {e}" for e in errors)
                    )

            try:
                instance = BenchmarkInstance.from_dict(instance_dict)
                yield instance
            except Exception as e:
                raise ValueError(f"Error parsing instance at line {line_num}: {e}")

    def filter(
        self,
        difficulty: Optional[str] = None,
        provider: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None,
        return_dataset: bool = True
    ) -> Union[List[BenchmarkInstance], Dataset]:
        """
        Load dataset with filters applied.

        Args:
            difficulty: Filter by difficulty level
            provider: Filter by cloud provider
            tags: Filter by tags (instance must have all specified tags)
            limit: Maximum number of instances to return
            return_dataset: If True, return Dataset object; if False, return list

        Returns:
            Dataset object or filtered list of BenchmarkInstance objects
        """
        instances = []
        count = 0

        for instance in self.stream(validate=True):
            # Apply filters
            if difficulty and instance.difficulty.value != difficulty:
                continue

            if provider and instance.provider != provider:
                continue

            if tags:
                if not all(tag in instance.tags for tag in tags):
                    continue

            instances.append(instance)
            count += 1

            if limit and count >= limit:
                break

        if return_dataset:
            return Dataset(instances)
        return instances

    def get_by_id(self, instance_id: str) -> Optional[BenchmarkInstance]:
        """
        Get a specific instance by ID.

        Args:
            instance_id: Instance identifier

        Returns:
            BenchmarkInstance or None if not found
        """
        for instance in self.stream(validate=False):
            if instance.instance_id == instance_id:
                return instance
        return None

    def _read_jsonl(self) -> Iterator[Dict[str, Any]]:
        """Read JSONL file line by line."""
        with open(self.dataset_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line:  # Skip empty lines
                    yield json.loads(line)


def save_dataset(instances: List[BenchmarkInstance], output_path: str) -> None:
    """
    Save instances to JSONL file.

    Args:
        instances: List of BenchmarkInstance objects
        output_path: Path to output JSONL file
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, 'w') as f:
        for instance in instances:
            json.dump(instance.to_dict(), f)
            f.write('\n')


def create_instance(
    instance_id: str,
    problem_statement: str,
    difficulty: str,
    tags: List[str],
    provider: str,
    region: str,
    expected_resources: Dict[str, int],
    validation_script: str,
    estimated_cost: str,
    deployment_time_seconds: int,
    **kwargs
) -> BenchmarkInstance:
    """
    Factory function to create a BenchmarkInstance.

    Args:
        instance_id: Unique identifier
        problem_statement: Natural language description
        difficulty: One of 'easy', 'medium', 'hard'
        tags: List of tags
        provider: Cloud provider
        region: Default region
        expected_resources: Resource type counts
        validation_script: Path to validation script
        estimated_cost: Cost estimate string
        deployment_time_seconds: Estimated deployment time
        **kwargs: Additional optional fields

    Returns:
        BenchmarkInstance object
    """
    from .schema import Difficulty, InstanceMetadata

    metadata = InstanceMetadata(
        estimated_cost=estimated_cost,
        deployment_time_seconds=deployment_time_seconds,
        cleanup_required=kwargs.get('cleanup_required', True),
        created_at=kwargs.get('created_at'),
        author=kwargs.get('author', 'terraform-bench')
    )

    return BenchmarkInstance(
        instance_id=instance_id,
        problem_statement=problem_statement,
        difficulty=Difficulty(difficulty),
        tags=tags,
        provider=provider,
        region=region,
        expected_resources=expected_resources,
        validation_script=validation_script,
        metadata=metadata,
        required_outputs=kwargs.get('required_outputs', []),
        gold_solution=kwargs.get('gold_solution', {}),
        hints=kwargs.get('hints', [])
    )


def load_dataset(
    path: str,
    split: Optional[str] = None,
    streaming: bool = False,
    validate: bool = True,
    **filter_kwargs
) -> Union[Dataset, Iterator[BenchmarkInstance]]:
    """
    Load a dataset from a JSONL file (HuggingFace-like API).

    Args:
        path: Path to JSONL dataset file
        split: Dataset split (e.g., 'train', 'test', 'train[:80%]')
        streaming: If True, return iterator instead of Dataset
        validate: Whether to validate instances against schema
        **filter_kwargs: Additional filters (difficulty, provider, tags, limit)

    Returns:
        Dataset object or Iterator if streaming=True

    Examples:
        >>> dataset = load_dataset('data/benchmark.jsonl')
        >>> dataset = load_dataset('data/benchmark.jsonl', difficulty='easy')
        >>> splits = load_dataset('data/benchmark.jsonl', split='train[:80%]')
    """
    loader = DatasetLoader(path)

    # Handle streaming mode
    if streaming:
        return loader.stream(validate=validate)

    # Load full dataset
    if filter_kwargs:
        # Apply filters
        dataset = loader.filter(
            difficulty=filter_kwargs.get('difficulty'),
            provider=filter_kwargs.get('provider'),
            tags=filter_kwargs.get('tags'),
            limit=filter_kwargs.get('limit'),
            return_dataset=True
        )
    else:
        dataset = loader.load(validate=validate, return_dataset=True)

    # Handle split notation
    if split:
        dataset = _apply_split(dataset, split)

    return dataset


def _apply_split(dataset: Dataset, split: str) -> Dataset:
    """
    Apply split notation to dataset.

    Args:
        dataset: Dataset to split
        split: Split notation (e.g., 'train', 'test', 'train[:80%]', 'test[80%:]')

    Returns:
        Dataset with split applied
    """
    if '[' not in split:
        # Named split without indexing - just return dataset
        return dataset

    # Parse split notation
    base_split, indices = split.split('[', 1)
    indices = indices.rstrip(']')

    total_len = len(dataset)

    # Handle percentage notation
    if '%' in indices:
        if ':' in indices:
            # Range with percentages
            parts = indices.split(':')
            start_pct = int(parts[0].rstrip('%')) if parts[0] else 0
            end_pct = int(parts[1].rstrip('%')) if parts[1] else 100

            start_idx = int(total_len * start_pct / 100)
            end_idx = int(total_len * end_pct / 100)
        else:
            # Single percentage
            pct = int(indices.rstrip('%'))
            start_idx = 0
            end_idx = int(total_len * pct / 100)
    else:
        # Handle absolute indices
        if ':' in indices:
            parts = indices.split(':')
            start_idx = int(parts[0]) if parts[0] else 0
            end_idx = int(parts[1]) if parts[1] else total_len
        else:
            # Single index
            idx = int(indices)
            return Dataset([dataset[idx]])

    return dataset[start_idx:end_idx]
