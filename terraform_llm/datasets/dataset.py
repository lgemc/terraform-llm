"""Dataset class with HuggingFace-like API."""

import random
from typing import List, Dict, Any, Optional, Union, Callable, Tuple
from collections.abc import Mapping

from .schema import BenchmarkInstance


class Dataset(Mapping):
    """
    A dataset class similar to HuggingFace datasets.

    Supports:
    - Indexing: dataset[0], dataset[0:10]
    - Column access: dataset['instance_id']
    - Methods: map, filter, select, shuffle, train_test_split
    """

    def __init__(self, data: List[BenchmarkInstance]):
        """
        Initialize dataset.

        Args:
            data: List of BenchmarkInstance objects
        """
        self._data = data
        self._columns = self._extract_columns()

    def _extract_columns(self) -> List[str]:
        """Extract column names from the first instance."""
        if not self._data:
            return []

        # Get all fields from BenchmarkInstance
        first_instance = self._data[0]
        return [
            'instance_id', 'problem_statement', 'difficulty', 'tags',
            'provider', 'region', 'expected_resources', 'validation_script',
            'metadata', 'required_outputs', 'gold_solution', 'hints'
        ]

    def __len__(self) -> int:
        """Return the number of instances in the dataset."""
        return len(self._data)

    def __getitem__(self, key: Union[int, slice, str]) -> Union[BenchmarkInstance, 'Dataset', List[Any]]:
        """
        Get item(s) from dataset.

        Args:
            key: Integer index, slice, or column name

        Returns:
            - If int: single BenchmarkInstance
            - If slice: new Dataset with selected instances
            - If str: list of values for that column
        """
        if isinstance(key, int):
            # Return single instance
            return self._data[key]
        elif isinstance(key, slice):
            # Return new Dataset with sliced data
            return Dataset(self._data[key])
        elif isinstance(key, str):
            # Return column values
            return self._get_column(key)
        else:
            raise TypeError(f"Invalid key type: {type(key)}")

    def __iter__(self):
        """Iterate over instances."""
        return iter(self._data)

    def _get_column(self, column_name: str) -> List[Any]:
        """Get all values for a specific column."""
        values = []
        for instance in self._data:
            if column_name == 'difficulty':
                values.append(instance.difficulty.value)
            else:
                values.append(getattr(instance, column_name))
        return values

    @property
    def column_names(self) -> List[str]:
        """Get list of column names."""
        return self._columns.copy()

    @property
    def num_rows(self) -> int:
        """Get number of rows (instances)."""
        return len(self._data)

    def map(
        self,
        function: Callable[[BenchmarkInstance], BenchmarkInstance],
        batched: bool = False
    ) -> 'Dataset':
        """
        Apply a function to all instances.

        Args:
            function: Function to apply to each instance
            batched: If True, function receives list of instances

        Returns:
            New Dataset with transformed instances
        """
        if batched:
            new_data = function(self._data)
        else:
            new_data = [function(instance) for instance in self._data]

        return Dataset(new_data)

    def filter(
        self,
        function: Callable[[BenchmarkInstance], bool],
        difficulty: Optional[str] = None,
        provider: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> 'Dataset':
        """
        Filter instances based on a function or criteria.

        Args:
            function: Function that returns True to keep instance
            difficulty: Filter by difficulty level
            provider: Filter by cloud provider
            tags: Filter by tags (instance must have all specified tags)

        Returns:
            New Dataset with filtered instances
        """
        filtered_data = []

        for instance in self._data:
            # Apply function filter
            if function and not function(instance):
                continue

            # Apply difficulty filter
            if difficulty and instance.difficulty.value != difficulty:
                continue

            # Apply provider filter
            if provider and instance.provider != provider:
                continue

            # Apply tags filter
            if tags and not all(tag in instance.tags for tag in tags):
                continue

            filtered_data.append(instance)

        return Dataset(filtered_data)

    def select(self, indices: List[int]) -> 'Dataset':
        """
        Select instances by indices.

        Args:
            indices: List of indices to select

        Returns:
            New Dataset with selected instances
        """
        selected_data = [self._data[i] for i in indices]
        return Dataset(selected_data)

    def shuffle(self, seed: Optional[int] = None) -> 'Dataset':
        """
        Shuffle the dataset.

        Args:
            seed: Random seed for reproducibility

        Returns:
            New shuffled Dataset
        """
        shuffled_data = self._data.copy()
        if seed is not None:
            random.seed(seed)
        random.shuffle(shuffled_data)
        return Dataset(shuffled_data)

    def train_test_split(
        self,
        test_size: Optional[float] = None,
        train_size: Optional[float] = None,
        shuffle: bool = True,
        seed: Optional[int] = None
    ) -> Dict[str, 'Dataset']:
        """
        Split dataset into train and test sets.

        Args:
            test_size: Proportion of dataset for test (0.0 to 1.0)
            train_size: Proportion of dataset for train (0.0 to 1.0)
            shuffle: Whether to shuffle before splitting
            seed: Random seed for reproducibility

        Returns:
            Dictionary with 'train' and 'test' datasets
        """
        if test_size is None and train_size is None:
            test_size = 0.2
        elif test_size is None:
            test_size = 1.0 - train_size
        elif train_size is None:
            train_size = 1.0 - test_size

        if not 0 < test_size < 1 or not 0 < train_size < 1:
            raise ValueError("test_size and train_size must be between 0 and 1")

        if abs(test_size + train_size - 1.0) > 1e-6:
            raise ValueError("test_size + train_size must equal 1.0")

        data = self._data.copy()
        if shuffle:
            if seed is not None:
                random.seed(seed)
            random.shuffle(data)

        test_count = int(len(data) * test_size)
        test_data = data[:test_count]
        train_data = data[test_count:]

        return {
            'train': Dataset(train_data),
            'test': Dataset(test_data)
        }

    def sort(self, column: str, reverse: bool = False) -> 'Dataset':
        """
        Sort dataset by a column.

        Args:
            column: Column name to sort by
            reverse: If True, sort in descending order

        Returns:
            New sorted Dataset
        """
        sorted_data = sorted(
            self._data,
            key=lambda x: getattr(x, column) if column != 'difficulty' else x.difficulty.value,
            reverse=reverse
        )
        return Dataset(sorted_data)

    def to_list(self) -> List[BenchmarkInstance]:
        """Convert dataset to list of instances."""
        return self._data.copy()

    def to_dict(self) -> Dict[str, List[Any]]:
        """
        Convert dataset to dictionary of columns.

        Returns:
            Dictionary mapping column names to lists of values
        """
        result = {}
        for column in self._columns:
            result[column] = self._get_column(column)
        return result

    def add_item(self, item: BenchmarkInstance) -> 'Dataset':
        """
        Add a single instance to the dataset.

        Args:
            item: BenchmarkInstance to add

        Returns:
            New Dataset with added instance
        """
        new_data = self._data.copy()
        new_data.append(item)
        return Dataset(new_data)

    def remove_columns(self, columns: List[str]) -> 'Dataset':
        """
        Remove columns from dataset (returns same instances).
        Note: This returns the same dataset as BenchmarkInstance is immutable.

        Args:
            columns: List of column names to remove

        Returns:
            Same Dataset (BenchmarkInstance doesn't support column removal)
        """
        # Since BenchmarkInstance is a dataclass, we can't remove columns
        # This method is here for API compatibility but returns same dataset
        return self

    def rename_column(self, original_name: str, new_name: str) -> 'Dataset':
        """
        Rename a column (not supported for BenchmarkInstance).

        Args:
            original_name: Original column name
            new_name: New column name

        Returns:
            Same Dataset (column renaming not supported)
        """
        # Since BenchmarkInstance is a dataclass, we can't rename columns
        # This method is here for API compatibility but returns same dataset
        return self

    def unique(self, column: str) -> List[Any]:
        """
        Get unique values in a column.

        Args:
            column: Column name

        Returns:
            List of unique values
        """
        values = self._get_column(column)
        return list(set(values))

    def info(self) -> str:
        """
        Get dataset information.

        Returns:
            String with dataset info
        """
        info_lines = [
            f"Dataset({{",
            f"    num_rows: {self.num_rows}",
            f"    columns: {self.column_names}",
            f"}})"
        ]
        return "\n".join(info_lines)

    def __repr__(self) -> str:
        """String representation of dataset."""
        return self.info()
