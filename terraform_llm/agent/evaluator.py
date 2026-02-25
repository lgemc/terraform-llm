"""Graded evaluation of Terraform pipeline stages."""

import logging
from typing import Dict, Tuple
from dataclasses import dataclass

from terraform_llm.datasets.schema import BenchmarkInstance
from terraform_llm.agent.results import StageResult, StageStatus, InstanceResult
from terraform_llm.agent.environment import TerraformEnvironment

logger = logging.getLogger(__name__)


@dataclass
class EvalConfig:
    """Configuration for the evaluation pipeline."""
    run_apply: bool = False
    run_destroy: bool = True
    run_validation: bool = False
    init_timeout: int = 120
    plan_timeout: int = 300
    apply_timeout: int = 600


def evaluate_instance(
    instance: BenchmarkInstance,
    generated_files: dict[str, str],
    config: EvalConfig,
) -> InstanceResult:
    """
    Run the full evaluation pipeline for a single instance.

    Stages run sequentially; if a stage fails, subsequent stages are SKIPPED.

    Args:
        instance: The benchmark instance with expected_resources, etc.
        generated_files: Dict of filename -> HCL content from the LLM
        config: Evaluation configuration

    Returns:
        InstanceResult with all stage results and total score
    """
    result = InstanceResult(
        instance_id=instance.instance_id,
        generated_files=generated_files,
    )

    with TerraformEnvironment() as env:
        env.setup(generated_files)

        # Stage 1: init
        init_result = env.terraform_init(timeout=config.init_timeout)
        result.stages.append(init_result)
        if init_result.status != StageStatus.PASSED:
            _skip_remaining(result, ["validate", "plan", "apply", "validation_script"])
            return result

        # Stage 2: validate
        validate_result = env.terraform_validate()
        result.stages.append(validate_result)
        if validate_result.status != StageStatus.PASSED:
            _skip_remaining(result, ["plan", "apply", "validation_script"])
            return result

        # Stage 3: plan
        plan_result = env.terraform_plan(timeout=config.plan_timeout)
        result.stages.append(plan_result)

        if plan_result.status == StageStatus.PASSED:
            # Score plan against expected resources
            planned = plan_result.details.get("planned_resources", {})
            score, message = score_plan(planned, instance.expected_resources)
            plan_result.score = score
            plan_result.message = message
            if score < 1.0:
                plan_result.status = StageStatus.PASSED  # still passed, just partial score
        else:
            _skip_remaining(result, ["apply", "validation_script"])
            return result

        # Stage 4: apply (optional)
        if config.run_apply:
            apply_result = env.terraform_apply(timeout=config.apply_timeout)
            result.stages.append(apply_result)

            if apply_result.status != StageStatus.PASSED:
                _skip_remaining(result, ["validation_script"])
                # Still try to destroy
                if config.run_destroy:
                    env.terraform_destroy()
                return result

            # Stage 5: validation script (optional)
            if config.run_validation and instance.validation_script:
                validation_result = env.run_validation_script(instance.validation_script)
                result.stages.append(validation_result)

            # Stage 6: destroy
            if config.run_destroy:
                destroy_result = env.terraform_destroy()
                logger.info(f"Destroy: {destroy_result.status.value}")

    return result


def score_plan(
    planned_resources: dict[str, int],
    expected_resources: Dict[str, int],
) -> Tuple[float, str]:
    """
    Score a terraform plan against expected resources.

    Per-type scoring: min(planned, expected) / max(planned, expected)
    Small penalty for unexpected resource types (capped at 0.3).
    Final score averaged across expected types.

    Args:
        planned_resources: Resource type counts from terraform plan
        expected_resources: Resource type counts from the benchmark instance

    Returns:
        Tuple of (score between 0.0 and 1.0, human-readable message)
    """
    if not expected_resources:
        if not planned_resources:
            return 1.0, "No expected resources to check"
        return 0.5, "No expectations defined"

    type_scores = []
    messages = []

    for rtype, expected in expected_resources.items():
        if expected == 0:
            continue
        planned = planned_resources.get(rtype, 0)
        type_score = min(planned, expected) / max(planned, expected)
        type_scores.append(type_score)
        if planned != expected:
            messages.append(f"{rtype}: expected {expected}, got {planned}")

    # Penalty for unexpected resource types
    unexpected = set(planned_resources.keys()) - set(expected_resources.keys())
    penalty = min(0.1 * len(unexpected), 0.3)

    score = (sum(type_scores) / len(type_scores) if type_scores else 0.0) - penalty
    score = max(0.0, score)

    if not messages and not unexpected:
        msg = "All resources match expected counts"
    else:
        if unexpected:
            messages.append(f"Unexpected types: {', '.join(sorted(unexpected))}")
        msg = "; ".join(messages)

    return score, msg


def _skip_remaining(result: InstanceResult, stages: list[str]) -> None:
    """Add SKIPPED results for remaining stages."""
    for stage in stages:
        result.stages.append(StageResult(
            stage=stage,
            status=StageStatus.SKIPPED,
            score=0.0,
            message="Skipped due to previous stage failure",
        ))
