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


def display_single_stage(stage: Dict[str, Any], stage_number: int) -> None:
    """Display a single stage with detailed formatting."""
    stage_name = stage.get("stage", "unknown")
    status = stage.get("status", "unknown")
    duration = stage.get("duration_seconds", 0)
    score = stage.get("score", 0.0)
    message = stage.get("message", "")

    # Status color
    status_color = {
        "passed": "green",
        "failed": "red",
        "skipped": "yellow",
    }.get(status, "white")

    # Create header
    header = f"""[bold cyan]Stage {stage_number}:[/bold cyan] {stage_name}
[bold cyan]Status:[/bold cyan] [{status_color}]{status}[/{status_color}]
[bold cyan]Score:[/bold cyan] {score:.2f}
[bold cyan]Duration:[/bold cyan] {duration:.2f}s
[bold cyan]Message:[/bold cyan] {message}"""

    console.print(Panel(header, title="Stage Details", border_style="cyan"))
    console.print()

    # Display output if present
    if "output" in stage and stage["output"]:
        render_output(stage["output"], "Output")
        console.print()

    # Display details if present (e.g., diagnostics for validation stage)
    details = stage.get("details", {})
    if details:
        # Special handling for diagnostics
        if "diagnostics" in details:
            console.print("[bold red]Diagnostics:[/bold red]")
            for diag in details["diagnostics"]:
                severity = diag.get("severity", "unknown")
                summary = diag.get("summary", "")
                detail = diag.get("detail", "")
                snippet = diag.get("snippet", {})

                severity_color = "red" if severity == "error" else "yellow"

                diag_text = f"[{severity_color}]{severity.upper()}[/{severity_color}]: {summary}\n{detail}"

                if snippet:
                    context = snippet.get("context", "")
                    code = snippet.get("code", "")
                    if context:
                        diag_text += f"\n\n[dim]Context: {context}[/dim]"
                    if code:
                        diag_text += f"\n[dim]{code}[/dim]"

                console.print(Panel(diag_text, border_style=severity_color))
            console.print()
        else:
            console.print(Panel(
                Syntax(json.dumps(details, indent=2), "json", theme="monokai"),
                title="Details",
                border_style="magenta"
            ))
            console.print()


def traces_command(
    trace_path: str = typer.Argument(
        ...,
        help="Path to trace directory, summary file, or specific trace file"
    ),
    show_messages: bool = typer.Option(
        False,
        "--messages", "-m",
        help="Show generated Terraform files from trace"
    ),
    show_steps: bool = typer.Option(
        False,
        "--steps", "-s",
        help="Show execution stages from trace"
    ),
    step: Optional[str] = typer.Option(
        None,
        "--step",
        help="Show a specific stage by name (e.g., 'validate', 'plan') or number (1-indexed)"
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

        # Show trace file
        uv run python -m terraform_llm.cli traces output/qwen2.5-coder-3b/terraform-aws-lambda-001/terraform-aws-lambda-001.traj.json

        # Show trace with raw JSON
        uv run python -m terraform_llm.cli traces output/.../terraform-aws-lambda-001.traj.json --json

        # Show trace with generated Terraform files
        uv run python -m terraform_llm.cli traces output/.../terraform-aws-lambda-001.traj.json --messages

        # Show trace with execution stages
        uv run python -m terraform_llm.cli traces output/.../terraform-aws-lambda-001.traj.json --steps

        # Show specific stage with detailed output
        uv run python -m terraform_llm.cli traces output/.../terraform-aws-lambda-001.traj.json --step validate
        uv run python -m terraform_llm.cli traces output/.../terraform-aws-lambda-001.traj.json --step 3
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
    info = trace.get("info", {})
    problem_statement = info.get("problem_statement", "")

    # Get score and timing info
    total_score = info.get("total_score", 0.0)
    total_time = info.get("total_time_seconds", 0.0)
    model = info.get("model", "unknown")
    region = info.get("region", "unknown")

    # Determine passed status from stages
    stages = trace.get("stages", [])
    all_passed = all(
        stage.get("status") in ["passed", "skipped"]
        for stage in stages
    )
    has_failure = any(stage.get("status") == "failed" for stage in stages)
    passed = all_passed and not has_failure

    # Create header panel
    status_color = "green" if passed else "red"
    status_text = "PASSED ✓" if passed else "FAILED ✗"

    header = f"""[bold cyan]Instance:[/bold cyan] {instance_id}
[bold cyan]Status:[/bold cyan] [{status_color}]{status_text}[/{status_color}]
[bold cyan]Score:[/bold cyan] {total_score:.2f}
[bold cyan]Duration:[/bold cyan] {total_time:.2f}s
[bold cyan]Model:[/bold cyan] {model}
[bold cyan]Region:[/bold cyan] {region}"""

    console.print(Panel(header, title="Trace Overview", border_style="cyan"))
    console.print()

    # If --step is specified, show only that stage
    if step is not None:
        # Try to parse as number first
        try:
            step_num = int(step)
            if step_num < 1 or step_num > len(stages):
                console.print(f"[red]Error: Stage {step_num} not found. Valid range: 1-{len(stages)}[/red]")
                raise typer.Exit(code=1)
            display_single_stage(stages[step_num - 1], step_num)
            return
        except ValueError:
            # Not a number, treat as stage name
            for idx, s in enumerate(stages, 1):
                if s.get("stage") == step:
                    display_single_stage(s, idx)
                    return

            # Stage name not found, show available stages
            available_stages = [s.get("stage", "unknown") for s in stages]
            console.print(f"[red]Error: Stage '{step}' not found.[/red]")
            console.print(f"[yellow]Available stages: {', '.join(available_stages)}[/yellow]")
            raise typer.Exit(code=1)

    # Display problem statement
    if problem_statement:
        console.print(Panel(problem_statement, title="Problem Statement", border_style="blue"))
        console.print()

    # Display generated files if requested (replaces messages)
    generated_files = trace.get("generated_files", {})
    if show_messages and generated_files:
        console.print("[bold cyan]Generated Files:[/bold cyan]")
        for filename, content in generated_files.items():
            console.print(Panel(
                Syntax(content, "hcl", theme="monokai"),
                title=f"File: {filename}",
                border_style="blue"
            ))
        console.print()

    # Display stages if requested (replaces steps)
    if show_steps and stages:
        console.print("[bold cyan]Execution Stages:[/bold cyan]")
        for i, stage in enumerate(stages, 1):
            display_single_stage(stage, i)
        console.print()

    # Display stages summary table
    if not show_steps and stages:
        table = Table(title="Stage Summary", box=box.ROUNDED)
        table.add_column("Stage", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Score", justify="right")
        table.add_column("Duration", justify="right")
        table.add_column("Message", style="dim")

        for stage in stages:
            stage_name = stage.get("stage", "unknown")
            status = stage.get("status", "unknown")
            score = stage.get("score", 0.0)
            duration = stage.get("duration_seconds", 0.0)
            message = stage.get("message", "")

            status_color = {
                "passed": "green",
                "failed": "red",
                "skipped": "yellow",
            }.get(status, "white")

            table.add_row(
                stage_name,
                f"[{status_color}]{status}[/{status_color}]",
                f"{score:.2f}",
                f"{duration:.2f}s",
                message
            )

        console.print(table)
        console.print()

    # Display summary counts
    console.print(f"[dim]Generated files: {len(generated_files)} | Stages: {len(stages)}[/dim]")
    if not show_messages and generated_files:
        console.print("[dim]Use --messages to view generated files[/dim]")
    if not show_steps and stages:
        console.print("[dim]Use --steps to view execution stages[/dim]")
