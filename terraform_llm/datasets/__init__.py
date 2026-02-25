"""Dataset management module for Terraform benchmarks."""

from .schema import (
    BenchmarkInstance,
    InstanceMetadata,
    Difficulty,
    validate_instance
)
from .loader import (
    DatasetLoader,
    save_dataset,
    create_instance,
    load_dataset
)
from .dataset import Dataset

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
