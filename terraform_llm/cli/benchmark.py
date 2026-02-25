"""Benchmark command for running evaluation."""

from typing import Optional
import typer
from rich import print as rprint
from rich.console import Console

from ..agent import ModelConfig, EvalConfig, run_benchmark
from ..datasets import load_dataset

console = Console()


def benchmark_command(
    dataset: str = typer.Argument(..., help="Path to JSONL dataset file"),
    output_dir: str = typer.Option(..., "-o", "--output-dir", help="Output directory"),
    model: str = typer.Option("anthropic/claude-3-5-sonnet-20241022", help="Model identifier (e.g., anthropic/claude-sonnet-4-5-20250929, openai/gpt-4o)"),
    temperature: float = typer.Option(0.0, help="Model temperature"),
    difficulty: Optional[str] = typer.Option(None, help="Filter by difficulty"),
    filter_provider: Optional[str] = typer.Option(None, help="Filter by cloud provider"),
    limit: Optional[int] = typer.Option(None, help="Limit number of instances"),
    run_apply: bool = typer.Option(False, help="Run terraform apply (creates real infrastructure)"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output")
):
    """Run benchmark evaluation."""
    rprint(f"[bold]Running benchmark on dataset:[/bold] {dataset}")

    # Load dataset with filters
    dataset_obj = load_dataset(
        dataset,
        difficulty=difficulty,
        provider=filter_provider,
        limit=limit,
    )

    # Create model configuration
    model_config = ModelConfig(
        model=model,
        temperature=temperature,
    )

    # Create evaluation configuration
    eval_config = EvalConfig(
        run_apply=run_apply,
        run_destroy=True,
        run_validation=run_apply,  # Only run validation if we're applying
    )

    # Run benchmark
    report = run_benchmark(
        dataset=dataset_obj,
        model_config=model_config,
        eval_config=eval_config,
    )

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold]BENCHMARK RESULTS[/bold]", justify="center")
    console.print("=" * 60)
    console.print(f"Model: {model_config.model}")
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

    console.print(f"\n[green]Results can be exported to:[/green] {output_dir}/benchmark_results.json")
