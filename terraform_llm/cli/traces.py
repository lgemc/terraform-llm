"""CLI command for reading and displaying traces."""

import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich import box


console = Console()


def traces_command(
    trace_path: str = typer.Argument(
        ...,
        help="Path to trace directory, summary file, or specific trace file"
    ),
    show_messages: bool = typer.Option(
        False,
        "--messages", "-m",
        help="Show full message history from trace"
    ),
    show_steps: bool = typer.Option(
        False,
        "--steps", "-s",
        help="Show execution steps from trace"
    ),
    json_output: bool = typer.Option(
        False,
        "--json", "-j",
        help="Output raw JSON instead of formatted display"
    ),
):
    """
    Read and display execution traces from benchmark runs.

    Examples:

        # Show summary from a trace directory
        terraform-llm traces traces/2026-02-24_19_41_13/

        # Show specific trace file
        terraform-llm traces traces/2026-02-24_19_41_13/terraform-aws-lambda-vpc-001.json

        # Show summary with raw JSON
        terraform-llm traces traces/2026-02-24_19_41_13/summary.json --json

        # Show trace with full messages
        terraform-llm traces traces/2026-02-24_19_41_13/terraform-aws-lambda-vpc-001.json --messages

        # Show trace with execution steps
        terraform-llm traces traces/2026-02-24_19_41_13/terraform-aws-lambda-vpc-001.json --steps
    """
    path = Path(trace_path)

    if not path.exists():
        console.print(f"[red]Error: Path not found: {trace_path}[/red]")
        raise typer.Exit(code=1)

    try:
        if path.is_dir():
            # Display summary from directory
            summary_file = path / "summary.json"
            if summary_file.exists():
                display_summary(summary_file, json_output)
            else:
                console.print(f"[yellow]No summary.json found in {trace_path}[/yellow]")
                # List available trace files
                trace_files = list(path.glob("*.json"))
                if trace_files:
                    console.print("\n[cyan]Available trace files:[/cyan]")
                    for trace_file in trace_files:
                        console.print(f"  • {trace_file.name}")
                raise typer.Exit(code=1)
        else:
            # Display specific file
            if path.name == "summary.json" or "summary" in path.stem:
                display_summary(path, json_output)
            else:
                display_trace(path, show_messages, show_steps, json_output)

    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON in {path.name}: {e}[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


def display_summary(summary_path: Path, json_output: bool = False):
    """Display summary from summary.json file."""
    with open(summary_path) as f:
        summary = json.load(f)

    if json_output:
        console.print_json(data=summary)
        return

    # Display summary statistics
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    pass_rate = summary.get("pass_rate", 0.0)

    # Create summary table
    table = Table(title="Benchmark Run Summary", box=box.ROUNDED)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta", justify="right")

    table.add_row("Total", str(total))
    table.add_row("Passed", f"[green]{passed}[/green]")
    table.add_row("Failed", f"[red]{failed}[/red]")
    table.add_row("Pass Rate", f"{pass_rate:.1%}")

    console.print(table)
    console.print()

    # Display individual results
    results = summary.get("results", [])
    if results:
        results_table = Table(title="Individual Results", box=box.ROUNDED)
        results_table.add_column("Instance ID", style="cyan")
        results_table.add_column("Status", justify="center")
        results_table.add_column("Error/Info", style="dim")

        for result in results:
            instance_id = result.get("instance_id", "unknown")
            passed = result.get("passed", False)
            status = "[green]✓ PASSED[/green]" if passed else "[red]✗ FAILED[/red]"
            error = result.get("error", "")

            results_table.add_row(instance_id, status, error)

        console.print(results_table)


def display_trace(trace_path: Path, show_messages: bool = False,
                  show_steps: bool = False, json_output: bool = False):
    """Display individual trace file."""
    with open(trace_path) as f:
        trace = json.load(f)

    if json_output:
        console.print_json(data=trace)
        return

    # Display basic info
    instance_id = trace.get("instance_id", "unknown")
    problem_statement = trace.get("problem_statement", "")
    start_time = trace.get("start_time", "")
    end_time = trace.get("end_time", "")

    info = trace.get("info", {})
    exit_status = info.get("exit_status", "unknown")
    passed = info.get("passed", False)

    # Create header panel
    status_color = "green" if passed else "red"
    status_text = "PASSED ✓" if passed else "FAILED ✗"

    header = f"""[bold cyan]Instance:[/bold cyan] {instance_id}
[bold cyan]Status:[/bold cyan] [{status_color}]{status_text}[/{status_color}]
[bold cyan]Exit Status:[/bold cyan] {exit_status}
[bold cyan]Start Time:[/bold cyan] {start_time}
[bold cyan]End Time:[/bold cyan] {end_time}"""

    console.print(Panel(header, title="Trace Overview", border_style="cyan"))
    console.print()

    # Display problem statement
    if problem_statement:
        console.print(Panel(problem_statement, title="Problem Statement", border_style="blue"))
        console.print()

    # Display messages if requested
    messages = trace.get("messages", [])
    if show_messages and messages:
        console.print("[bold cyan]Message History:[/bold cyan]")
        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            extra = msg.get("extra", {})

            role_color = {
                "system": "yellow",
                "user": "blue",
                "assistant": "green",
                "error": "red"
            }.get(role, "white")

            msg_text = f"[{role_color}]{role.upper()}[/{role_color}] ({timestamp})"
            if extra:
                msg_text += f"\n[dim]{extra}[/dim]"
            msg_text += f"\n{content}"

            console.print(Panel(msg_text, border_style=role_color))
        console.print()

    # Display steps if requested
    steps = trace.get("steps", [])
    if show_steps and steps:
        console.print("[bold cyan]Execution Steps:[/bold cyan]")
        for i, step in enumerate(steps, 1):
            step_text = json.dumps(step, indent=2)
            console.print(Panel(
                Syntax(step_text, "json", theme="monokai"),
                title=f"Step {i}",
                border_style="magenta"
            ))
        console.print()

    # Display summary counts
    console.print(f"[dim]Messages: {len(messages)} | Steps: {len(steps)}[/dim]")
    if not show_messages and messages:
        console.print("[dim]Use --messages to view full message history[/dim]")
    if not show_steps and steps:
        console.print("[dim]Use --steps to view execution steps[/dim]")
