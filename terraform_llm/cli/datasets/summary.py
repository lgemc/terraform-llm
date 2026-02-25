"""Summary command for showing dataset statistics."""

from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from ...datasets import load_dataset

console = Console()


def summary_command(
    dataset_path: str = typer.Argument(..., help="Path to dataset folder or JSONL file")
):
    """Show summary statistics for datasets in a folder."""
    path = Path(dataset_path)

    if not path.exists():
        console.print(f"[red]Error:[/red] Path not found: {dataset_path}")
        raise typer.Exit(code=1)

    # Collect all JSONL files (recursively in subdirectories)
    if path.is_file():
        jsonl_files = [path]
    else:
        jsonl_files = list(path.rglob("*.jsonl"))

    if not jsonl_files:
        console.print(f"[yellow]No JSONL files found in:[/yellow] {dataset_path}")
        raise typer.Exit(code=0)

    # Create summary table
    table = Table(title=f"Dataset Summary: {dataset_path}")
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Instances", justify="right", style="green")
    table.add_column("Difficulty", justify="left")
    table.add_column("Providers", justify="left")
    table.add_column("Tags", justify="left")

    total_instances = 0

    for jsonl_file in sorted(jsonl_files):
        try:
            dataset = load_dataset(str(jsonl_file), validate=True)
            instances = list(dataset)

            # Collect statistics
            num_instances = len(instances)
            total_instances += num_instances

            difficulties = {}
            providers = set()
            all_tags = set()

            for instance in instances:
                diff = instance.difficulty.value
                difficulties[diff] = difficulties.get(diff, 0) + 1
                providers.add(instance.provider)
                all_tags.update(instance.tags)

            # Format statistics
            diff_str = ", ".join(f"{k}:{v}" for k, v in sorted(difficulties.items()))
            providers_str = ", ".join(sorted(providers))
            tags_str = ", ".join(sorted(all_tags)[:5])
            if len(all_tags) > 5:
                tags_str += f", +{len(all_tags) - 5} more"

            # Show relative path from the base path for context
            rel_path = jsonl_file.relative_to(path) if path.is_dir() else jsonl_file.name

            table.add_row(
                str(rel_path),
                str(num_instances),
                diff_str,
                providers_str,
                tags_str
            )

        except Exception as e:
            console.print(f"[red]Error loading {jsonl_file.name}:[/red] {str(e)}")
            continue

    console.print(table)
    console.print(f"\n[bold]Total instances:[/bold] {total_instances}")
