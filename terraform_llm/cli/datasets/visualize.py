"""Visualize command for displaying dataset instances in detail."""

from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich import box

from ...datasets import DatasetLoader

console = Console()


def visualize_command(
    dataset: str = typer.Argument(..., help="Path to JSONL dataset file"),
    instance_id: Optional[str] = typer.Option(None, "--id", help="Specific instance ID to visualize"),
    index: Optional[int] = typer.Option(None, "--index", help="Instance index (0-based) to visualize"),
    show_solution: bool = typer.Option(True, "--solution/--no-solution", help="Show gold solution"),
):
    """Visualize a dataset instance in detail."""
    loader = DatasetLoader(dataset)
    instances = loader.filter(return_dataset=False)

    if not instances:
        console.print("[red]No instances found in dataset[/red]")
        return

    # Select instance
    if instance_id:
        instance = next((i for i in instances if i.instance_id == instance_id), None)
        if not instance:
            console.print(f"[red]Instance ID '{instance_id}' not found[/red]")
            return
    elif index is not None:
        if index < 0 or index >= len(instances):
            console.print(f"[red]Index {index} out of range (0-{len(instances)-1})[/red]")
            return
        instance = instances[index]
    else:
        # Default to first instance
        instance = instances[0]

    console.print()

    # Header
    console.print(Panel(
        f"[bold cyan]{instance.instance_id}[/bold cyan]",
        title="[bold]Instance ID[/bold]",
        border_style="cyan"
    ))

    # Metadata table
    meta_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    meta_table.add_column("Field", style="bold yellow")
    meta_table.add_column("Value")

    meta_table.add_row("Difficulty", f"[{_get_difficulty_color(instance.difficulty.value)}]{instance.difficulty.value.upper()}[/]")
    meta_table.add_row("Provider", f"[blue]{instance.provider}[/blue]")
    meta_table.add_row("Region", instance.region)
    meta_table.add_row("Tags", ", ".join([f"[green]{tag}[/green]" for tag in instance.tags]))
    meta_table.add_row("Estimated Cost", instance.metadata.estimated_cost)
    meta_table.add_row("Deployment Time", f"{instance.metadata.deployment_time_seconds}s")

    console.print(meta_table)
    console.print()

    # Problem statement
    console.print(Panel(
        instance.problem_statement,
        title="[bold]Problem Statement[/bold]",
        border_style="yellow"
    ))
    console.print()

    # Expected resources
    resource_table = Table(title="[bold]Expected Resources[/bold]", box=box.ROUNDED)
    resource_table.add_column("Resource Type", style="cyan")
    resource_table.add_column("Count", justify="right", style="magenta")

    for resource_type, count in instance.expected_resources.items():
        resource_table.add_row(resource_type, str(count))

    console.print(resource_table)
    console.print()

    # Required outputs
    if instance.required_outputs:
        console.print("[bold]Required Outputs:[/bold]")
        for output in instance.required_outputs:
            console.print(f"  • [cyan]{output}[/cyan]")
        console.print()

    # Hints
    if instance.hints:
        console.print(Panel(
            "\n".join([f"[dim]{i+1}.[/dim] {hint}" for i, hint in enumerate(instance.hints)]),
            title="[bold]Hints[/bold]",
            border_style="green"
        ))
        console.print()

    # Gold solution
    if show_solution and instance.gold_solution:
        for filename, content in instance.gold_solution.items():
            syntax = Syntax(
                content,
                "hcl",
                theme="monokai",
                line_numbers=True,
                word_wrap=True
            )
            console.print(Panel(
                syntax,
                title=f"[bold]Gold Solution: {filename}[/bold]",
                border_style="blue"
            ))
            console.print()

    # Footer metadata
    console.print(f"[dim]Created: {instance.metadata.created_at or 'N/A'} | "
                  f"Author: {instance.metadata.author} | "
                  f"Validation: {instance.validation_script}[/dim]")
    console.print()


def _get_difficulty_color(difficulty: str) -> str:
    """Get color for difficulty level."""
    colors = {
        "easy": "green",
        "medium": "yellow",
        "hard": "red"
    }
    return colors.get(difficulty.lower(), "white")


def stats_command(
    dataset: str = typer.Argument(..., help="Path to JSONL dataset file"),
):
    """Show statistics about a dataset."""
    loader = DatasetLoader(dataset)
    instances = loader.filter(return_dataset=False)

    if not instances:
        console.print("[red]No instances found in dataset[/red]")
        return

    console.print()
    console.print(Panel(
        f"[bold cyan]{dataset}[/bold cyan]",
        title="[bold]Dataset Statistics[/bold]",
        border_style="cyan"
    ))
    console.print()

    # Count by difficulty
    difficulty_counts = {}
    provider_counts = {}
    tag_counts = {}

    for instance in instances:
        # Difficulty
        diff = instance.difficulty.value
        difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1

        # Provider
        provider_counts[instance.provider] = provider_counts.get(instance.provider, 0) + 1

        # Tags
        for tag in instance.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Overall stats
    console.print(f"[bold]Total Instances:[/bold] {len(instances)}")
    console.print()

    # Difficulty breakdown
    diff_table = Table(title="[bold]Difficulty Distribution[/bold]", box=box.ROUNDED)
    diff_table.add_column("Difficulty", style="bold")
    diff_table.add_column("Count", justify="right", style="cyan")
    diff_table.add_column("Percentage", justify="right", style="magenta")

    for difficulty in ["easy", "medium", "hard"]:
        count = difficulty_counts.get(difficulty, 0)
        percentage = (count / len(instances)) * 100
        color = _get_difficulty_color(difficulty)
        diff_table.add_row(
            f"[{color}]{difficulty.upper()}[/{color}]",
            str(count),
            f"{percentage:.1f}%"
        )

    console.print(diff_table)
    console.print()

    # Provider breakdown
    prov_table = Table(title="[bold]Provider Distribution[/bold]", box=box.ROUNDED)
    prov_table.add_column("Provider", style="bold blue")
    prov_table.add_column("Count", justify="right", style="cyan")

    for provider, count in sorted(provider_counts.items()):
        prov_table.add_row(provider, str(count))

    console.print(prov_table)
    console.print()

    # Top tags
    if tag_counts:
        tag_table = Table(title="[bold]Top Tags[/bold]", box=box.ROUNDED)
        tag_table.add_column("Tag", style="bold green")
        tag_table.add_column("Count", justify="right", style="cyan")

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        for tag, count in sorted_tags:
            tag_table.add_row(tag, str(count))

        console.print(tag_table)
        console.print()
