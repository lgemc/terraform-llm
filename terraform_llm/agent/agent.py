"""Core benchmark runner that ties model, environment, and evaluator together."""

import logging
from typing import Optional

from terraform_llm.datasets.schema import BenchmarkInstance
from terraform_llm.datasets.dataset import Dataset
from terraform_llm.agent.models import ModelConfig, generate_hcl
from terraform_llm.agent.tool_agent import generate_hcl_with_tools
from terraform_llm.agent.evaluator import EvalConfig, evaluate_instance
from terraform_llm.agent.results import InstanceResult, BenchmarkReport
from terraform_llm.tracing.atif_tracer import ATIFTracer

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

    With multiturn enabled, the agent can iteratively refine based on validation feedback.

    Args:
        instance: Benchmark instance to evaluate
        model_config: LLM configuration
        eval_config: Evaluation pipeline configuration (defaults to plan-only)
        work_dir: Optional directory for terraform files (persists output if provided)
        docker_env: Optional pre-created docker environment (for parallel execution)

    Returns:
        InstanceResult with all stage scores and ATIF trajectory
    """
    if eval_config is None:
        eval_config = EvalConfig()

    logger.info(f"Running instance {instance.instance_id} with model {model_config.model}")

    # Initialize ATIF tracer to capture multi-turn trajectory
    tracer = ATIFTracer(agent_version="1.0.0")
    tracer.set_model(model_config.model, model_config.agent_type)
    tracer.session_id = instance.instance_id  # Use instance_id instead of random UUID

    # Step 1: Add initial user message
    tracer.add_user_message(instance.problem_statement)

    # Step 1: Generate HCL from LLM
    agent_type_display = f"{model_config.model} ({model_config.agent_type})"
    if model_config.multiturn:
        agent_type_display += " [multiturn]"
    print(f"  Generating Terraform code with {agent_type_display}...")

    tool_call_trace = []
    prompt = None
    messages = None
    best_result = None
    best_score = -1.0

    # Multiturn loop (defaults to 1 iteration if multiturn is disabled)
    max_iterations = model_config.max_multiturn_iterations if model_config.multiturn else 1

    for iteration in range(max_iterations):
        if model_config.multiturn and iteration > 0:
            print(f"  Refinement iteration {iteration + 1}/{max_iterations}...")

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
                # Simple agent
                validation_feedback = None
                if iteration > 0 and best_result:
                    # Build feedback from previous evaluation
                    validation_feedback = _build_validation_feedback(best_result)

                generated_files, prompt, messages = generate_hcl(
                    config=model_config,
                    problem_statement=instance.problem_statement,
                    provider=instance.provider,
                    region=instance.region,
                    hints=instance.hints,
                    validation_feedback=validation_feedback,
                    messages=messages,
                )

            if iteration == 0:
                print(f"  Generated {len(generated_files)} file(s): {', '.join(generated_files.keys())}")

            # Add agent generation step to trajectory
            files_summary = "\n\n".join([
                f"### {filename}\n```hcl\n{content[:500]}{'...' if len(content) > 500 else ''}\n```"
                for filename, content in generated_files.items()
            ])
            iteration_suffix = f" (iteration {iteration + 1}/{max_iterations})" if model_config.multiturn and max_iterations > 1 else ""
            tracer.add_agent_step(
                message=f"Generated {len(generated_files)} Terraform file(s){iteration_suffix}:\n\n{files_summary}",
                reasoning_content=prompt if prompt else None,
            )

        except Exception as e:
            print(f"  Generation failed: {e}")
            logger.error(f"LLM generation failed for {instance.instance_id}: {e}")

            # Return best result so far if available
            if best_result:
                best_result.trajectory = tracer.to_trajectory(
                    extra={
                        "instance_id": instance.instance_id,
                        "problem_statement": instance.problem_statement,
                        "generated_files": best_result.generated_files,
                        "region": instance.region,
                        "expected_resources": instance.expected_resources,
                        "total_score": best_result.total_score,
                        "error": None,
                    }
                )
                return best_result

            result = InstanceResult(
                instance_id=instance.instance_id,
                model=model_config.model,
                error=f"Generation failed: {e}",
            )
            result.trajectory = tracer.to_trajectory(
                extra={
                    "instance_id": instance.instance_id,
                    "problem_statement": instance.problem_statement,
                    "generated_files": {},
                    "region": instance.region,
                    "expected_resources": instance.expected_resources,
                    "total_score": 0.0,
                    "error": str(e),
                }
            )
            return result

        # Step 2: Evaluate generated HCL
        if iteration == 0:
            print("  Evaluating generated code...")

        result = evaluate_instance(instance, generated_files, eval_config, work_dir=work_dir, docker_env=docker_env)
        result.model = model_config.model
        result.tool_calls = tool_call_trace
        result.prompt = prompt
        result.compute_total_score()

        # Add evaluation stages to trajectory as system steps
        for stage in result.stages:
            tracer.add_system_step(
                message=f"Terraform {stage.stage}: {stage.message}",
                observation=stage.raw_output if stage.raw_output else None,
                extra={
                    "stage": stage.stage,
                    "status": stage.status.value,
                    "score": stage.score,
                    "duration_seconds": stage.duration_seconds,
                    "details": stage.details if stage.details else None,
                    "message": stage.message,
                    "iteration": iteration + 1,
                },
            )

        # Track best result
        if result.total_score > best_score:
            best_score = result.total_score
            best_result = result

        # Early exit if perfect score or multiturn disabled
        if not model_config.multiturn or result.total_score >= 1.0:
            logger.info(f"Instance {instance.instance_id} score: {result.total_score:.2f}")
            result.trajectory = tracer.to_trajectory(
                extra={
                    "instance_id": instance.instance_id,
                    "problem_statement": instance.problem_statement,
                    "generated_files": result.generated_files,
                    "region": instance.region,
                    "expected_resources": instance.expected_resources,
                    "total_score": result.total_score,
                    "best_score": best_score,
                    "iterations": iteration + 1,
                }
            )
            return result

        # Add refinement feedback as user message for next iteration
        feedback = _build_validation_feedback(result)
        tracer.add_user_message(f"The previous Terraform configuration had issues. Please fix them:\n\n{feedback}")

        # Continue to next iteration with feedback
        print(f"    Score: {result.total_score:.2f} - attempting refinement...")

    # Return best result after all iterations
    logger.info(f"Instance {instance.instance_id} final score: {best_result.total_score:.2f} (best of {max_iterations} iterations)")
    best_result.trajectory = tracer.to_trajectory(
        extra={
            "instance_id": instance.instance_id,
            "problem_statement": instance.problem_statement,
            "generated_files": best_result.generated_files,
            "region": instance.region,
            "expected_resources": instance.expected_resources,
            "total_score": best_result.total_score,
            "best_score": best_score,
            "iterations": max_iterations,
        }
    )
    return best_result


def _build_validation_feedback(result: InstanceResult) -> str:
    """Build feedback message from evaluation result."""
    feedback_parts = []

    # Include generated files so LLM can see what it wrote
    if result.generated_files:
        feedback_parts.append("## Generated Files\n")
        for filename, content in result.generated_files.items():
            feedback_parts.append(f"### {filename}\n```hcl\n{content}\n```\n")

    # Include error messages from failed stages
    feedback_parts.append("## Errors\n")
    has_errors = False
    for stage in result.stages:
        if stage.status.value == "failed":
            # Include full output (up to 3000 chars) to capture complete diagnostics
            feedback_parts.append(f"**{stage.stage} failed:**\n```\n{stage.raw_output[:3000]}\n```\n")
            has_errors = True

    if not has_errors:
        feedback_parts.append("Previous attempt had issues. Please review and improve the configuration.")

    return "\n".join(feedback_parts)


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
