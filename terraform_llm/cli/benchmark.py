"""Benchmark command for running evaluation."""

import json
import time
from typing import Optional, List
from pathlib import Path
import typer
from rich import print as rprint
from rich.console import Console

from terraform_llm.agent import ModelConfig, EvalConfig, run_instance, generate_hcl
from terraform_llm.datasets import load_dataset, DatasetLoader

console = Console()


def benchmark_command(
    dataset: str = typer.Argument(
        ...,
        help="Path to dataset file or directory (loads all .jsonl files recursively from directories)",
    ),
    output_dir: str = typer.Option("output", "-o", "--output-dir", help="Output directory"),
    model: str = typer.Option(
        "anthropic/claude-3-5-sonnet-20241022",
        help="Model identifier (e.g., anthropic/claude-sonnet-4-5-20250929, openai/gpt-4o)",
    ),
    temperature: float = typer.Option(0.0, help="Model temperature"),
    max_tokens: int = typer.Option(16384, help="Maximum tokens for model generation"),
    agent_type: str = typer.Option(
        "simple",
        "--agent-type",
        help="Agent type: 'simple' (direct generation) or 'tool-enabled' (with doc search)",
    ),
    max_tool_iterations: int = typer.Option(
        5,
        "--max-tool-iterations",
        help="Maximum iterations for tool-enabled agent",
    ),
    docs_index_path: Optional[str] = typer.Option(
        None,
        "--docs-index-path",
        help="Path to hybrid search index for tool-enabled agent (build with 'index-docs' command)",
    ),
    reasoning_effort: Optional[str] = typer.Option(
        None,
        "--reasoning-effort",
        help="Reasoning effort for reasoning models (low, medium, high) - enables extended thinking",
    ),
    difficulty: Optional[str] = typer.Option(None, help="Filter by difficulty"),
    filter_provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter by cloud provider"),
    limit: Optional[int] = typer.Option(None, help="Limit number of instances"),
    instance_id: Optional[str] = typer.Option(
        None, "--instance-id", "-i", help="Run specific instance by ID",
    ),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", help="Filter by tags (can be specified multiple times)",
    ),
    run_apply: bool = typer.Option(False, help="Run terraform apply (creates infrastructure)"),
    use_docker: bool = typer.Option(
        True,
        "--docker/--no-docker",
        help="Use Docker + LocalStack for isolated execution (recommended)",
    ),
    terraform_image: str = typer.Option(
        "hashicorp/terraform:latest",
        "--terraform-image",
        help="Docker image for Terraform",
    ),
    localstack_image: str = typer.Option(
        "localstack/localstack:latest",
        "--localstack-image",
        help="Docker image for LocalStack",
    ),
    skip_generation: bool = typer.Option(
        False,
        "--skip-generation",
        help="Skip code generation and reuse existing Terraform files from output directory",
    ),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output"),
):
    """Run benchmark evaluation with optional Docker + LocalStack execution."""
    rprint(f"[bold]Running benchmark on dataset:[/bold] {dataset}")

    if use_docker:
        rprint("[bold]Execution mode:[/bold] Docker + LocalStack")
    else:
        rprint("[bold]Execution mode:[/bold] Local Terraform")

    # Load dataset
    try:
        if instance_id:
            loader = DatasetLoader(dataset)
            instance = loader.get_by_id(instance_id)
            if not instance:
                console.print(f"[red]Error: Instance {instance_id} not found in dataset[/red]")
                raise typer.Exit(code=1)
            instances = [instance]
        else:
            dataset_obj = load_dataset(
                dataset,
                difficulty=difficulty,
                provider=filter_provider,
                tags=tags,
                limit=limit,
            )
            instances = list(dataset_obj)

        if not instances:
            console.print("[red]No instances found matching the filters[/red]")
            raise typer.Exit(code=1)

    except FileNotFoundError:
        console.print(f"[red]Error: Dataset not found: {dataset}[/red]")
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error loading dataset: {e}[/red]")
        raise typer.Exit(code=1)

    # Create model configuration
    model_config = ModelConfig(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        agent_type=agent_type,
        max_tool_iterations=max_tool_iterations,
        docs_index_path=docs_index_path,
        reasoning_effort=reasoning_effort,
    )

    # Create evaluation configuration
    eval_config = EvalConfig(
        run_apply=run_apply,
        run_destroy=True,
        run_validation=run_apply,
        use_docker=use_docker,
        terraform_image=terraform_image,
        localstack_image=localstack_image,
    )

    # Process instances
    from terraform_llm.agent.results import BenchmarkReport
    from terraform_llm.agent.evaluator import evaluate_instance
    report = BenchmarkReport(model=model_config.model)
    output_base = Path(output_dir)

    for idx, inst in enumerate(instances, 1):
        console.print(f"\n[{idx}/{len(instances)}] Processing: {inst.instance_id}")
        instance_dir = output_base / inst.instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        instance_start = time.time()

        try:
            if skip_generation:
                # Load existing code from instance directory
                if not instance_dir.exists():
                    console.print(f"  [red]Error: No existing code found in {instance_dir}[/red]")
                    continue

                terraform_code = {}
                for tf_file in instance_dir.glob("*.tf"):
                    terraform_code[tf_file.name] = tf_file.read_text()

                if not terraform_code:
                    console.print(f"  [red]Error: No .tf files found in {instance_dir}[/red]")
                    continue

                console.print(f"  Loaded {len(terraform_code)} file(s) from {instance_dir}")

                # Evaluate with persistent work_dir
                instance_result = evaluate_instance(
                    inst, terraform_code, eval_config, work_dir=str(instance_dir),
                )
                instance_result.model = model_config.model
                instance_result.compute_total_score()
            else:
                # Full pipeline: generate + evaluate, using instance_dir as work_dir
                instance_result = run_instance(
                    inst, model_config, eval_config, work_dir=str(instance_dir),
                )

            report.results.append(instance_result)

            # Save trajectory file
            traj = {
                "trajectory_format": "terraform-agent-1.0",
                "instance_id": inst.instance_id,
                "info": {
                    "problem_statement": inst.problem_statement,
                    "region": inst.region,
                    "expected_resources": inst.expected_resources,
                    "model": instance_result.model,
                    "agent_type": model_config.agent_type,
                    "total_score": instance_result.total_score,
                    "total_time_seconds": time.time() - instance_start,
                },
                "model_config": model_config.to_dict(),
                "generated_files": instance_result.generated_files,
                "stages": [s.to_dict() for s in instance_result.stages],
            }
            if instance_result.prompt:
                traj["prompt"] = instance_result.prompt
            if instance_result.tool_calls:
                traj["tool_calls"] = instance_result.tool_calls
            if instance_result.error:
                traj["info"]["error"] = instance_result.error

            traj_path = instance_dir / f"{inst.instance_id}.traj.json"
            with open(traj_path, "w") as f:
                json.dump(traj, f, indent=2)

            # Print per-instance result
            score_str = f"{instance_result.total_score:.2f}"
            if instance_result.total_score >= 0.8:
                console.print(f"  [green]Score: {score_str}[/green]")
            else:
                console.print(f"  [yellow]Score: {score_str}[/yellow]")

            for stage in instance_result.stages:
                status_color = "green" if stage.status.value == "passed" else "red"
                if stage.status.value == "skipped":
                    status_color = "dim"
                console.print(f"    {stage.stage}: [{status_color}]{stage.status.value}[/{status_color}] ({stage.score:.2f})")

            if instance_result.error:
                console.print(f"  [red]Error: {instance_result.error}[/red]")

            console.print(f"  Trace: {traj_path}")

        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            if verbose:
                import traceback
                traceback.print_exc()

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold]BENCHMARK RESULTS[/bold]", justify="center")
    console.print("=" * 60)
    console.print(f"Model: {model_config.model}")
    console.print(f"Execution: {'Docker + LocalStack' if use_docker else 'Local'}")
    console.print(f"Total instances: {len(report.results)}")
    console.print(f"Mean score: {report.mean_score:.2f}")

    # Calculate pass rate (score >= 0.8)
    passed = sum(1 for r in report.results if r.total_score >= 0.8)
    pass_rate = passed / len(report.results) if report.results else 0.0
    console.print(f"[green]Passed (score >= 0.8):[/green] {passed}/{len(report.results)} ({pass_rate:.1%})")

    # Stage pass rates
    console.print("\n[bold]Stage pass rates:[/bold]")
    stage_rates = report.stage_pass_rates()
    for stage, rate in stage_rates.items():
        console.print(f"  {stage}: {rate:.1%}")

    # Save aggregate results with metadata
    results_data = report.to_dict()
    results_data["model_config"] = model_config.to_dict()
    results_data["output_dir"] = str(output_base)

    results_path = output_base / "benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump(results_data, f, indent=2)
    console.print(f"\n[green]Results saved to:[/green] {results_path}")
