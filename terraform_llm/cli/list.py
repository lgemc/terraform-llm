"""List command for showing dataset instances."""

from typing import Optional
import typer
from rich.console import Console

from terraform_llm.datasets import DatasetLoader

console = Console()


def list_command(
    dataset: str = typer.Argument(..., help="Path to JSONL dataset file"),
    difficulty: Optional[str] = typer.Option(None, help="Filter by difficulty"),
    provider: Optional[str] = typer.Option(None, help="Filter by provider"),
    limit: Optional[int] = typer.Option(None, help="Limit results")
):
    """List instances in a dataset."""
    loader = DatasetLoader(dataset)

    instances = loader.filter(
        difficulty=difficulty,
        provider=provider,
        limit=limit,
        return_dataset=False
    )

    console.print(f"[bold]Found {len(instances)} instances:[/bold]\n")

    for i, instance in enumerate(instances, 1):
        console.print(f"[cyan]{i}. {instance.instance_id}[/cyan]")
        console.print(f"   Difficulty: [yellow]{instance.difficulty.value}[/yellow]")
        console.print(f"   Provider: {instance.provider}")
        console.print(f"   Problem: {instance.problem_statement[:80]}...")
        console.print()
