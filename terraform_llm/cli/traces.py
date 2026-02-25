"""CLI command for reading and displaying traces."""

import json
import re
from pathlib import Path
from typing import Optional, Dict, Any
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich import box


console = Console()


def strip_ansi_codes(text: str) -> str:
    """Strip ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


def render_output(output: str, title: str = "Output") -> None:
    """Render output with ANSI codes or as JSON if applicable."""
    if not output:
        console.print(f"[dim]{title}: (empty)[/dim]")
        return

    # Try to parse as JSON first
    try:
        json_data = json.loads(output)
        console.print(Panel(
            Syntax(json.dumps(json_data, indent=2), "json", theme="monokai"),
            title=title,
            border_style="cyan"
        ))
        return
    except (json.JSONDecodeError, ValueError):
        pass

    # Render with ANSI codes using Rich's Text
    text = Text.from_ansi(output)
    console.print(Panel(text, title=title, border_style="cyan"))


def display_single_step(step: Dict[str, Any], step_number: int) -> None:
    """Display a single step with detailed formatting."""
    step_name = step.get("step", "unknown")
    status = step.get("status", "unknown")
    duration = step.get("duration", 0)
    timestamp = step.get("timestamp", "")

    # Status color
    status_color = {
        "success": "green",
        "passed": "green",
        "failed": "red",
        "error": "red",
    }.get(status, "yellow")

    # Create header
    header = f"""[bold cyan]Step {step_number}:[/bold cyan] {step_name}
[bold cyan]Status:[/bold cyan] [{status_color}]{status}[/{status_color}]
[bold cyan]Duration:[/bold cyan] {duration:.2f}s
[bold cyan]Timestamp:[/bold cyan] {timestamp}"""

    if "command" in step:
        header += f"\n[bold cyan]Command:[/bold cyan] {step['command']}"

    console.print(Panel(header, title="Step Details", border_style="cyan"))
    console.print()

    # Display output if present
    if "output" in step and step["output"]:
        render_output(step["output"], "Output")
        console.print()

    # Display stderr if present
    if "stderr" in step and step["stderr"]:
        render_output(step["stderr"], "Stderr")
        console.print()

    # Display error if present
    if "error" in step:
        console.print(Panel(
            f"[red]{step['error']}[/red]",
            title="Error",
            border_style="red"
        ))
        console.print()

    # Display additional fields
    excluded_keys = {"step", "status", "duration", "timestamp", "command", "output", "stderr", "error"}
    other_fields = {k: v for k, v in step.items() if k not in excluded_keys}

    if other_fields:
        console.print(Panel(
            Syntax(json.dumps(other_fields, indent=2), "json", theme="monokai"),
            title="Additional Fields",
            border_style="magenta"
        ))


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
    step: Optional[str] = typer.Option(
        None,
        "--step",
        help="Show a specific step by name (e.g., 'terraform_validate') or number (1-indexed)"
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

        # Show specific step with detailed output
        terraform-llm traces traces/2026-02-24_19_41_13/terraform-aws-lambda-vpc-001.json --step terraform_validate
        terraform-llm traces traces/2026-02-24_19_41_13/terraform-aws-lambda-vpc-001.json --step 4
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
                display_trace(path, show_messages, show_steps, step, json_output)

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
                  show_steps: bool = False, step: Optional[str] = None,
                  json_output: bool = False):
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

    # If --step is specified, show only that step
    steps = trace.get("steps", [])
    if step is not None:
        # Try to parse as number first
        try:
            step_num = int(step)
            if step_num < 1 or step_num > len(steps):
                console.print(f"[red]Error: Step {step_num} not found. Valid range: 1-{len(steps)}[/red]")
                raise typer.Exit(code=1)
            display_single_step(steps[step_num - 1], step_num)
            return
        except ValueError:
            # Not a number, treat as step name
            for idx, s in enumerate(steps, 1):
                if s.get("step") == step:
                    display_single_step(s, idx)
                    return

            # Step name not found, show available steps
            available_steps = [s.get("step", "unknown") for s in steps]
            console.print(f"[red]Error: Step '{step}' not found.[/red]")
            console.print(f"[yellow]Available steps: {', '.join(available_steps)}[/yellow]")
            raise typer.Exit(code=1)

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
