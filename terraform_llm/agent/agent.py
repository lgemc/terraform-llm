"""Core benchmark runner that ties model, environment, and evaluator together."""

import logging
from typing import Optional

from ..datasets.schema import BenchmarkInstance
from ..datasets.dataset import Dataset
from .models import ModelConfig, generate_hcl
from .evaluator import EvalConfig, evaluate_instance
from .results import InstanceResult, BenchmarkReport

logger = logging.getLogger(__name__)


def run_instance(
    instance: BenchmarkInstance,
    model_config: ModelConfig,
    eval_config: Optional[EvalConfig] = None,
) -> InstanceResult:
    """
    Run a single benchmark instance: generate HCL, then evaluate.

    Args:
        instance: Benchmark instance to evaluate
        model_config: LLM configuration
        eval_config: Evaluation pipeline configuration (defaults to plan-only)

    Returns:
        InstanceResult with all stage scores
    """
    if eval_config is None:
        eval_config = EvalConfig()

    logger.info(f"Running instance {instance.instance_id} with model {model_config.model}")

    # Step 1: Generate HCL from LLM
    try:
        generated_files = generate_hcl(
            config=model_config,
            problem_statement=instance.problem_statement,
            provider=instance.provider,
            region=instance.region,
            hints=instance.hints,
        )
    except Exception as e:
        logger.error(f"LLM generation failed for {instance.instance_id}: {e}")
        return InstanceResult(
            instance_id=instance.instance_id,
            model=model_config.model,
            error=f"Generation failed: {e}",
        )

    # Step 2: Evaluate generated HCL
    result = evaluate_instance(instance, generated_files, eval_config)
    result.model = model_config.model
    result.compute_total_score()

    logger.info(f"Instance {instance.instance_id} score: {result.total_score:.2f}")
    return result


def run_benchmark(
    dataset: Dataset,
    model_config: ModelConfig,
    eval_config: Optional[EvalConfig] = None,
    max_instances: Optional[int] = None,
) -> BenchmarkReport:
    """
    Run the benchmark across a dataset of instances.

    Args:
        dataset: Dataset of BenchmarkInstance objects
        model_config: LLM configuration
        eval_config: Evaluation configuration
        max_instances: Maximum number of instances to evaluate

    Returns:
        BenchmarkReport with aggregated results
    """
    report = BenchmarkReport(model=model_config.model)
    instances = list(dataset)
    if max_instances:
        instances = instances[:max_instances]

    for i, instance in enumerate(instances):
        logger.info(f"[{i + 1}/{len(instances)}] {instance.instance_id}")
        result = run_instance(instance, model_config, eval_config)
        report.results.append(result)

    logger.info(f"Benchmark complete. Mean score: {report.mean_score:.2f}")
    return report
