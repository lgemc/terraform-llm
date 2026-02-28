"""Core benchmark runner that ties model, environment, and evaluator together."""

import logging
from typing import Optional

from terraform_llm.datasets.schema import BenchmarkInstance
from terraform_llm.datasets.dataset import Dataset
from terraform_llm.agent.models import ModelConfig, generate_hcl
from terraform_llm.agent.tool_agent import generate_hcl_with_tools
from terraform_llm.agent.evaluator import EvalConfig, evaluate_instance
from terraform_llm.agent.results import InstanceResult, BenchmarkReport

logger = logging.getLogger(__name__)


def run_instance(
    instance: BenchmarkInstance,
    model_config: ModelConfig,
    eval_config: Optional[EvalConfig] = None,
    work_dir: Optional[str] = None,
    docker_env=None,
) -> InstanceResult:
    """
    Run a single benchmark instance: generate HCL, then evaluate.

    Args:
        instance: Benchmark instance to evaluate
        model_config: LLM configuration
        eval_config: Evaluation pipeline configuration (defaults to plan-only)
        work_dir: Optional directory for terraform files (persists output if provided)
        docker_env: Optional pre-created docker environment (for parallel execution)

    Returns:
        InstanceResult with all stage scores
    """
    if eval_config is None:
        eval_config = EvalConfig()

    logger.info(f"Running instance {instance.instance_id} with model {model_config.model}")

    # Step 1: Generate HCL from LLM
    agent_type_display = f"{model_config.model} ({model_config.agent_type})"
    print(f"  Generating Terraform code with {agent_type_display}...")
    tool_call_trace = []
    prompt = None
    try:
        if model_config.agent_type == "tool-enabled":
            generated_files, tool_call_trace, prompt = generate_hcl_with_tools(
                model=model_config.model,
                problem_statement=instance.problem_statement,
                provider=instance.provider,
                region=instance.region,
                hints=instance.hints,
                temperature=model_config.temperature,
                max_tokens=model_config.max_tokens,
                max_iterations=model_config.max_tool_iterations,
                docs_index_path=model_config.docs_index_path,
                reasoning_effort=model_config.reasoning_effort,
            )
        else:
            # Default: simple agent
            generated_files, prompt = generate_hcl(
                config=model_config,
                problem_statement=instance.problem_statement,
                provider=instance.provider,
                region=instance.region,
                hints=instance.hints,
            )
        print(f"  Generated {len(generated_files)} file(s): {', '.join(generated_files.keys())}")
    except Exception as e:
        print(f"  Generation failed: {e}")
        logger.error(f"LLM generation failed for {instance.instance_id}: {e}")
        return InstanceResult(
            instance_id=instance.instance_id,
            model=model_config.model,
            error=f"Generation failed: {e}",
        )

    # Step 2: Evaluate generated HCL
    print("  Evaluating generated code...")
    result = evaluate_instance(instance, generated_files, eval_config, work_dir=work_dir, docker_env=docker_env)
    result.model = model_config.model
    result.tool_calls = tool_call_trace  # Attach tool call trace
    result.prompt = prompt  # Attach the prompt
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
