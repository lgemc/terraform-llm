"""Loader for the IaC-Eval HuggingFace dataset (autoiac-project/iac-eval).

Maps IaC-Eval rows to BenchmarkInstance so it can be used anywhere our
native JSONL format is accepted.

Field mapping:
  IaC-Eval              -> BenchmarkInstance
  ─────────────────────────────────────────────
  Prompt                -> problem_statement
  Resource (CSV)        -> tags + expected_resources
  Difficulty (1-6 int)  -> difficulty (1-2=easy, 3-4=medium, 5-6=hard)
  Reference output      -> gold_solution["main.tf"]  (stripped of provider block)
  Intent (checklist)    -> hints
  Rego intent           -> metadata["rego_intent"]
  (generated)           -> instance_id "iac-eval-{idx:04d}"
"""

import re
from typing import Optional, List
from terraform_llm.datasets.schema import BenchmarkInstance, Difficulty, InstanceMetadata
from terraform_llm.datasets.dataset import Dataset


_DIFFICULTY_MAP = {1: "easy", 2: "easy", 3: "medium", 4: "medium", 5: "hard", 6: "hard"}

# Provider block patterns that reference real AWS credentials — strip these so
# the code is usable with LocalStack/Moto.
_PROVIDER_BLOCK_RE = re.compile(
    r'provider\s+"aws"\s*\{[^}]*profile[^}]*\}', re.DOTALL
)


def _parse_resources(resource_str: str) -> dict:
    """Count occurrences of each resource type from the CSV Resource field."""
    counts: dict = {}
    for r in resource_str.split(","):
        r = r.strip()
        if r:
            counts[r] = counts.get(r, 0) + 1
    return counts


def _parse_tags(resource_str: str) -> List[str]:
    return [r.strip() for r in resource_str.split(",") if r.strip()]


def _parse_hints(intent_str: str) -> List[str]:
    """Turn the Intent checklist into a list of one-liner hints."""
    hints = []
    for line in intent_str.splitlines():
        line = line.strip()
        if line:
            hints.append(line)
    return hints


def _strip_credentials(tf_code: str) -> str:
    """Remove provider blocks that contain hardcoded profiles or role ARNs."""
    cleaned = _PROVIDER_BLOCK_RE.sub('provider "aws" {\n  region = "us-east-1"\n}', tf_code)
    return cleaned.strip()


def _row_to_instance(row: dict, idx: int) -> BenchmarkInstance:
    difficulty_int = int(row.get("Difficulty", 3))
    difficulty_str = _DIFFICULTY_MAP.get(difficulty_int, "medium")
    resource_str = row.get("Resource", "")
    gold_tf = _strip_credentials(row.get("Reference output", ""))

    metadata = InstanceMetadata(
        estimated_cost="unknown",
        deployment_time_seconds=120,
        cleanup_required=True,
        created_at=None,
        author="iac-eval",
    )
    # Stash rego intent for downstream use (e.g. static validation)
    metadata.__dict__["rego_intent"] = row.get("Rego intent", "")

    return BenchmarkInstance(
        instance_id=f"iac-eval-{idx:04d}",
        problem_statement=row.get("Prompt", ""),
        difficulty=Difficulty(difficulty_str),
        tags=_parse_tags(resource_str),
        provider="aws",
        region="us-east-1",
        expected_resources=_parse_resources(resource_str),
        validation_script=None,
        metadata=metadata,
        required_outputs=[],
        gold_solution={"main.tf": gold_tf} if gold_tf else {},
        hints=_parse_hints(row.get("Intent", "")),
        setup_script=None,
    )


def load_iac_eval(
    split: str = "test",
    limit: Optional[int] = None,
    difficulty: Optional[str] = None,
) -> Dataset:
    """Load the IaC-Eval dataset from HuggingFace and return a Dataset.

    Args:
        split: HuggingFace split to load (only "test" exists).
        limit: Maximum number of instances to return.
        difficulty: Filter by difficulty ("easy", "medium", "hard").

    Returns:
        Dataset of BenchmarkInstance objects.

    Example:
        >>> from terraform_llm.datasets.iac_eval import load_iac_eval
        >>> ds = load_iac_eval(limit=50)
        >>> ds = load_iac_eval(difficulty="hard")
    """
    try:
        from datasets import load_dataset as hf_load
    except ImportError as e:
        raise ImportError("pip install datasets  # or: uv add datasets") from e

    hf_ds = hf_load("autoiac-project/iac-eval", split=split)

    instances = []
    for idx, row in enumerate(hf_ds):
        instance = _row_to_instance(row, idx)

        if difficulty and instance.difficulty.value != difficulty:
            continue

        instances.append(instance)

        if limit and len(instances) >= limit:
            break

    return Dataset(instances)
