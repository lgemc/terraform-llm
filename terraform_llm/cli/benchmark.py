"""Benchmark command for running evaluation."""

from typing import Optional
import typer
from rich import print as rprint
from rich.console import Console

from ..agent import TerraformAgent, BenchmarkRunner
from ..model import create_client

console = Console()


def benchmark_command(
    dataset: str = typer.Argument(..., help="Path to JSONL dataset file"),
    output_dir: str = typer.Option(..., "-o", "--output-dir", help="Output directory"),
    provider: str = typer.Option("anthropic", help="Model provider (anthropic/openai)"),
    model: Optional[str] = typer.Option(None, help="Model identifier"),
    max_iterations: int = typer.Option(3, help="Max fix iterations"),
    difficulty: Optional[str] = typer.Option(None, help="Filter by difficulty"),
    filter_provider: Optional[str] = typer.Option(None, help="Filter by cloud provider"),
    limit: Optional[int] = typer.Option(None, help="Limit number of instances"),
    cleanup: bool = typer.Option(True, help="Destroy infrastructure after test"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output")
):
    """Run benchmark evaluation."""
    rprint(f"[bold]Running benchmark on dataset:[/bold] {dataset}")

    # Create model client
    model_client = create_client(
        provider=provider,
        model=model
    )

    # Create agent
    agent = TerraformAgent(
        model_client=model_client,
        max_iterations=max_iterations,
        verbose=verbose
    )

    # Run benchmark
    runner = BenchmarkRunner(
        agent=agent,
        dataset_path=dataset,
        output_dir=output_dir,
        cleanup=cleanup
    )

    results = runner.run_benchmark(
        difficulty=difficulty,
        provider=filter_provider,
        limit=limit
    )

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold]BENCHMARK RESULTS[/bold]", justify="center")
    console.print("=" * 60)
    console.print(f"Total instances: {results['total_instances']}")
    console.print(f"[green]Passed:[/green] {results['passed']}")
    console.print(f"[red]Failed:[/red] {results['failed']}")
    console.print(f"Pass rate: {results['pass_rate']:.2%}")
    console.print("\n[bold]Failure breakdown:[/bold]")
    console.print(f"  Generation: {results['failure_breakdown']['generation']}")
    console.print(f"  Terraform: {results['failure_breakdown']['terraform']}")
    console.print(f"  Validation: {results['failure_breakdown']['validation']}")
    console.print(f"\n[green]Results saved to:[/green] {output_dir}/benchmark_results.json")
