"""Dataset management module for Terraform benchmarks."""

from terraform_llm.datasets.schema import (
    BenchmarkInstance,
    InstanceMetadata,
    Difficulty,
    validate_instance
)
from terraform_llm.datasets.loader import (
    DatasetLoader,
    save_dataset,
    create_instance,
    load_dataset
)
from terraform_llm.datasets.dataset import Dataset

__all__ = [
    'BenchmarkInstance',
    'InstanceMetadata',
    'Difficulty',
    'validate_instance',
    'DatasetLoader',
    'Dataset',
    'save_dataset',
    'create_instance',
    'load_dataset',
]
