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
from rich.markdown import Markdown
from rich import box
from litellm import completion


console = Console()
traces_app = typer.Typer(help="Trace management and analysis commands")


def is_atif_trajectory(trace: Dict[str, Any]) -> bool:
    """Check if trajectory is ATIF format."""
    return "schema_version" in trace and trace["schema_version"].startswith("ATIF")


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


@traces_app.command(name="show")
def show_command(
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
    full: bool = typer.Option(
        False,
        "--full", "-f",
        help="Show full content without truncation"
    ),
):
    """
    Read and display execution traces from benchmark runs.

    Examples:

        # Show trace file
        uv run python -m terraform_llm.cli traces show output/qwen2.5-coder-3b/terraform-aws-lambda-001/terraform-aws-lambda-001.traj.json

        # Show trace with raw JSON
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --json

        # Show trace with generated Terraform files
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --messages

        # Show trace with execution stages
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --steps

        # Show full trace without truncation
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --steps --full

        # Show specific stage with detailed output
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --step validate
        uv run python -m terraform_llm.cli traces show output/.../terraform-aws-lambda-001.traj.json --step 3
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
                display_trace(path, show_messages, show_steps, step, json_output, full)

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


def _display_atif_stage(step: Dict[str, Any], full: bool = False) -> None:
    """Display a single ATIF system step (terraform stage) with detailed formatting."""
    extra = step.get("extra", {})
    stage_name = extra.get("stage", "unknown")
    status = extra.get("status", "unknown")
    duration = extra.get("duration_seconds", 0.0)
    score = extra.get("score", 0.0)
    # Try extra.message first (newer format), fall back to parsing from step.message
    message = extra.get("message", "")
    if not message:
        # Parse from step.message format "Terraform {stage}: {message}"
        step_msg = step.get("message", "")
        if ":" in step_msg:
            message = step_msg.split(":", 1)[1].strip()

    # Status color
    status_color = {
        "passed": "green",
        "failed": "red",
        "skipped": "yellow",
    }.get(status, "white")

    # Create header
    header = f"""[bold cyan]Stage:[/bold cyan] {stage_name}
[bold cyan]Status:[/bold cyan] [{status_color}]{status}[/{status_color}]
[bold cyan]Score:[/bold cyan] {score:.2f}
[bold cyan]Duration:[/bold cyan] {duration:.2f}s
[bold cyan]Message:[/bold cyan] {message}"""

    console.print(Panel(header, title="Stage Details", border_style="cyan"))
    console.print()

    # Display observation output if present
    observation = step.get("observation", {})
    if observation and observation.get("results"):
        for result in observation["results"]:
            content = result.get("content", "")
            # Skip if content is just "Status: {status}" (fallback message)
            if content and not content.startswith("Status: "):
                render_output(content if full else content[:1000], "Output")
                console.print()

    # Display details if present (e.g., diagnostics, planned resources)
    # Try extra.details first (newer format), fall back to observation content
    details = extra.get("details", {})
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


def display_atif_trace(trace: Dict[str, Any], show_messages: bool = False,
                       show_steps: bool = False, step_filter: Optional[str] = None,
                       full: bool = False):
    """Display ATIF format trace."""
    # Extract basic info
    session_id = trace.get("session_id", "unknown")
    schema_version = trace.get("schema_version", "unknown")
    agent_info = trace.get("agent", {})
    model = agent_info.get("model_name", "unknown")
    agent_name = agent_info.get("name", "unknown")
    agent_version = agent_info.get("version", "unknown")

    # Extract extra metadata (terraform-agent specific)
    extra = trace.get("extra", {})
    instance_id = extra.get("instance_id", session_id)
    problem_statement = extra.get("problem_statement", "")
    total_score = extra.get("total_score", 0.0)
    total_time = extra.get("total_time_seconds", 0.0)
    region = extra.get("region", "unknown")
    generated_files = extra.get("generated_files", {})

    # Get metrics
    final_metrics = trace.get("final_metrics", {})
    total_steps = final_metrics.get("total_steps", len(trace.get("steps", [])))

    # Determine passed status from system steps
    steps = trace.get("steps", [])
    system_steps = [s for s in steps if s.get("source") == "system"]
    all_passed = all(
        s.get("extra", {}).get("status") in ["passed", "skipped"]
        for s in system_steps
        if "status" in s.get("extra", {})
    )
    has_failure = any(
        s.get("extra", {}).get("status") == "failed"
        for s in system_steps
        if "status" in s.get("extra", {})
    )
    passed = all_passed and not has_failure

    # Create header panel
    status_color = "green" if passed else "red"
    status_text = "PASSED ✓" if passed else "FAILED ✗"

    header = f"""[bold cyan]Instance:[/bold cyan] {instance_id}
[bold cyan]Status:[/bold cyan] [{status_color}]{status_text}[/{status_color}]
[bold cyan]Score:[/bold cyan] {total_score:.2f}
[bold cyan]Duration:[/bold cyan] {total_time:.2f}s
[bold cyan]Model:[/bold cyan] {model}
[bold cyan]Agent:[/bold cyan] {agent_name} v{agent_version}
[bold cyan]Schema:[/bold cyan] {schema_version}
[bold cyan]Region:[/bold cyan] {region}"""

    console.print(Panel(header, title="ATIF Trajectory Overview", border_style="cyan"))
    console.print()

    # If --step is specified, show only that stage
    if step_filter is not None:
        # Find system steps (these are the terraform stages)
        system_steps = [s for s in steps if s.get("source") == "system"]

        # Try to parse as number first
        try:
            step_num = int(step_filter)
            if step_num < 1 or step_num > len(system_steps):
                console.print(f"[red]Error: Stage {step_num} not found. Valid range: 1-{len(system_steps)}[/red]")
                raise typer.Exit(code=1)
            target_step = system_steps[step_num - 1]
        except ValueError:
            # Not a number, treat as stage name
            target_step = None
            for s in system_steps:
                if s.get("extra", {}).get("stage") == step_filter:
                    target_step = s
                    break

            if target_step is None:
                # Stage name not found, show available stages
                available_stages = [s.get("extra", {}).get("stage", "unknown") for s in system_steps]
                console.print(f"[red]Error: Stage '{step_filter}' not found.[/red]")
                console.print(f"[yellow]Available stages: {', '.join(available_stages)}[/yellow]")
                raise typer.Exit(code=1)

        # Display the specific step
        _display_atif_stage(target_step, full)
        return

    # Display problem statement
    if problem_statement:
        console.print(Panel(problem_statement, title="Problem Statement", border_style="blue"))
        console.print()

    # Display generated files if requested
    if show_messages and generated_files:
        console.print("[bold cyan]Generated Files:[/bold cyan]")
        for filename, content in generated_files.items():
            console.print(Panel(
                Syntax(content, "hcl", theme="monokai"),
                title=f"File: {filename}",
                border_style="blue"
            ))
        console.print()

    # Display steps if requested
    if show_steps:
        console.print("[bold cyan]Trajectory Steps:[/bold cyan]")
        for i, step in enumerate(steps, 1):
            step_id = step.get("step_id", i)
            source = step.get("source", "unknown")
            message = step.get("message", "")
            timestamp = step.get("timestamp", "")
            tool_calls = step.get("tool_calls", [])
            observation = step.get("observation", {})
            metrics = step.get("metrics", {})

            # Format message display
            if isinstance(message, str):
                msg_display = message if full else (message[:200] + "..." if len(message) > 200 else message)
            else:
                msg_display = "[multimodal content]"

            step_header = f"""[bold cyan]Step {step_id}:[/bold cyan] [{source}]
[bold cyan]Timestamp:[/bold cyan] {timestamp}
[bold cyan]Message:[/bold cyan] {msg_display}"""

            if tool_calls:
                step_header += f"\n[bold cyan]Tool Calls:[/bold cyan] {len(tool_calls)}"
                for tc in tool_calls:
                    step_header += f"\n  • {tc.get('function_name', 'unknown')}"

            if metrics:
                prompt_tokens = metrics.get("prompt_tokens", 0)
                completion_tokens = metrics.get("completion_tokens", 0)
                cost = metrics.get("cost_usd", 0.0)
                step_header += f"\n[bold cyan]Metrics:[/bold cyan] {prompt_tokens} prompt / {completion_tokens} completion tokens (${cost:.4f})"

            console.print(Panel(step_header, border_style="green" if source == "agent" else "yellow"))

            # Show observation if present
            if observation and observation.get("results"):
                for result in observation["results"]:
                    content = result.get("content", "")
                    if content:
                        render_output(content if full else content[:500], "Observation")

            console.print()

    # Display steps summary table
    if not show_steps and steps:
        table = Table(title="Steps Summary", box=box.ROUNDED)
        table.add_column("Step", style="cyan", justify="right")
        table.add_column("Source", justify="center")
        table.add_column("Type", style="dim")
        table.add_column("Details", style="dim")

        for step in steps:
            step_id = str(step.get("step_id", "?"))
            source = step.get("source", "unknown")
            message = step.get("message", "")

            # Determine type
            if source == "user":
                step_type = "User Query"
            elif source == "agent":
                if step.get("tool_calls"):
                    step_type = f"{len(step['tool_calls'])} Tool Calls"
                else:
                    step_type = "Response"
            else:
                step_type = step.get("extra", {}).get("stage", "System")

            # Determine details
            if isinstance(message, str):
                details = message if full else (message[:60] + "..." if len(message) > 60 else message)
            else:
                details = "[multimodal]"

            source_color = {
                "user": "blue",
                "agent": "green",
                "system": "yellow",
            }.get(source, "white")

            table.add_row(
                step_id,
                f"[{source_color}]{source}[/{source_color}]",
                step_type,
                details
            )

        console.print(table)
        console.print()

    # Display final metrics
    if final_metrics:
        metrics_table = Table(title="Final Metrics", box=box.ROUNDED)
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", justify="right")

        if final_metrics.get("total_prompt_tokens"):
            metrics_table.add_row("Total Prompt Tokens", str(final_metrics["total_prompt_tokens"]))
        if final_metrics.get("total_completion_tokens"):
            metrics_table.add_row("Total Completion Tokens", str(final_metrics["total_completion_tokens"]))
        if final_metrics.get("total_cached_tokens"):
            metrics_table.add_row("Total Cached Tokens", str(final_metrics["total_cached_tokens"]))
        if final_metrics.get("total_cost_usd"):
            metrics_table.add_row("Total Cost (USD)", f"${final_metrics['total_cost_usd']:.4f}")
        metrics_table.add_row("Total Steps", str(total_steps))

        console.print(metrics_table)
        console.print()

    # Display hints
    console.print(f"[dim]Steps: {total_steps} | Generated files: {len(generated_files)}[/dim]")
    if not show_messages and generated_files:
        console.print("[dim]Use --messages to view generated files[/dim]")
    if not show_steps and steps:
        console.print("[dim]Use --steps to view all steps in detail[/dim]")


def display_trace(trace_path: Path, show_messages: bool = False,
                  show_steps: bool = False, step: Optional[str] = None,
                  json_output: bool = False, full: bool = False):
    """Display individual trace file."""
    with open(trace_path) as f:
        trace = json.load(f)

    if json_output:
        console.print_json(data=trace)
        return

    # Check if ATIF format
    if is_atif_trajectory(trace):
        display_atif_trace(trace, show_messages, show_steps, step, full)
        return

    # Legacy format display
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


@traces_app.command(name="diagnose")
def diagnose_command(
    trace_path: str = typer.Argument(
        ...,
        help="Path to trace file (.traj.json)"
    ),
    model: str = typer.Option(
        "anthropic/claude-sonnet-4-5-20250929",
        "--model", "-m",
        help="LLM model to use for diagnosis"
    ),
):
    """
    Diagnose why a model failed on a specific trace.

    This command analyzes failed stages in a trace file and uses an LLM
    to provide insights into why the model failed and what could be improved.

    Examples:

        # Diagnose with default model (Claude)
        uv run python -m terraform_llm.cli traces diagnose output/gpt-oss:120b/terraform-aws-apigw-lambda-001/terraform-aws-apigw-lambda-001.traj.json

        # Diagnose with specific model
        uv run python -m terraform_llm.cli traces diagnose output/.../trace.traj.json --model gpt-4
    """
    path = Path(trace_path)

    if not path.exists():
        console.print(f"[red]Error: Trace file not found: {trace_path}[/red]")
        raise typer.Exit(code=1)

    try:
        with open(path) as f:
            trace = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON in {path.name}: {e}[/red]")
        raise typer.Exit(code=1)

    # Extract failed stages
    stages = trace.get("stages", [])
    failed_stages = [s for s in stages if s.get("status") == "failed"]

    if not failed_stages:
        console.print("[green]✓ No failed stages found in this trace.[/green]")
        console.print("[dim]This trace appears to have passed all stages.[/dim]")
        raise typer.Exit(code=0)

    # Display failed stages summary
    console.print(f"[red]Found {len(failed_stages)} failed stage(s)[/red]\n")

    # Prepare diagnosis prompt
    instance_id = trace.get("instance_id", "unknown")
    problem_statement = trace.get("info", {}).get("problem_statement", "N/A")
    generated_files = trace.get("generated_files", {})
    model_used = trace.get("info", {}).get("model", "unknown")

    # Build context for LLM
    diagnosis_prompt = f"""You are a Terraform expert analyzing why an AI model failed to generate correct Terraform code.

Instance ID: {instance_id}
Model Used: {model_used}

Problem Statement:
{problem_statement}

Generated Terraform Files:
"""

    for filename, content in generated_files.items():
        diagnosis_prompt += f"\n--- {filename} ---\n{content}\n"

    diagnosis_prompt += "\nFailed Stages:\n"

    for idx, stage in enumerate(failed_stages, 1):
        stage_name = stage.get("stage", "unknown")
        message = stage.get("message", "")
        output = strip_ansi_codes(stage.get("output", ""))
        details = stage.get("details", {})

        diagnosis_prompt += f"\n{idx}. Stage: {stage_name}\n"
        diagnosis_prompt += f"   Message: {message}\n"

        if output:
            diagnosis_prompt += f"   Output:\n{output}\n"

        if details:
            diagnosis_prompt += f"   Details:\n{json.dumps(details, indent=2)}\n"

    diagnosis_prompt += """

Please analyze the failures and provide:
1. Root cause(s) of each failure
2. What the model did wrong in its Terraform code
3. How to fix the issues
4. General recommendations to avoid similar issues

Be concise but thorough. Focus on actionable insights."""

    # Call LLM for diagnosis
    console.print("[cyan]Analyzing failures with LLM...[/cyan]\n")

    try:
        response = completion(
            model=model,
            messages=[
                {"role": "user", "content": diagnosis_prompt}
            ],
            temperature=0.0,
        )

        diagnosis = response.choices[0].message.content

        # Display diagnosis with markdown rendering
        console.print(Panel(
            Markdown(diagnosis),
            title=f"[bold cyan]Diagnosis (by {model})[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))

    except Exception as e:
        console.print(f"[red]Error calling LLM: {e}[/red]")
        raise typer.Exit(code=1)


@traces_app.command(name="validate")
def validate_command(
    trace_path: str = typer.Argument(
        ...,
        help="Path to trajectory file to validate"
    ),
):
    """
    Validate an ATIF trajectory file against the schema.

    Examples:

        # Validate ATIF trajectory
        uv run python -m terraform_llm.cli traces validate output/.../trace.traj.json
    """
    path = Path(trace_path)

    if not path.exists():
        console.print(f"[red]Error: File not found: {trace_path}[/red]")
        raise typer.Exit(code=1)

    try:
        with open(path) as f:
            trace = json.load(f)

        if not is_atif_trajectory(trace):
            console.print(f"[yellow]Warning: Not an ATIF trajectory (legacy format)[/yellow]")
            console.print(f"[dim]Schema version: {trace.get('trajectory_format', 'unknown')}[/dim]")
            raise typer.Exit(code=0)

        # Validate using Pydantic model
        from terraform_llm.tracing.atif import Trajectory

        try:
            trajectory = Trajectory(**trace)
            console.print(f"[green]✓ Valid ATIF trajectory ({trajectory.schema_version})[/green]")
            console.print(f"[dim]Session ID: {trajectory.session_id}[/dim]")
            console.print(f"[dim]Steps: {len(trajectory.steps)}[/dim]")
            console.print(f"[dim]Agent: {trajectory.agent.name} v{trajectory.agent.version}[/dim]")

            if trajectory.has_multimodal_content():
                console.print(f"[cyan]Contains multimodal content (images)[/cyan]")

        except Exception as e:
            console.print(f"[red]✗ Invalid ATIF trajectory[/red]")
            console.print(f"[red]Validation error: {e}[/red]")
            raise typer.Exit(code=1)

    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON: {e}[/red]")
        raise typer.Exit(code=1)


@traces_app.command(name="compare")
def compare_command(
    trace1: str = typer.Argument(..., help="First trajectory file"),
    trace2: str = typer.Argument(..., help="Second trajectory file"),
):
    """
    Compare two trajectories side by side.

    Examples:

        # Compare two model runs
        uv run python -m terraform_llm.cli traces compare output/model1/trace.traj.json output/model2/trace.traj.json
    """
    path1 = Path(trace1)
    path2 = Path(trace2)

    if not path1.exists():
        console.print(f"[red]Error: File not found: {trace1}[/red]")
        raise typer.Exit(code=1)
    if not path2.exists():
        console.print(f"[red]Error: File not found: {trace2}[/red]")
        raise typer.Exit(code=1)

    try:
        with open(path1) as f:
            traj1 = json.load(f)
        with open(path2) as f:
            traj2 = json.load(f)

        # Create comparison table
        table = Table(title="Trajectory Comparison", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column(path1.name, justify="right", style="blue")
        table.add_column(path2.name, justify="right", style="green")

        # Check format
        is_atif1 = is_atif_trajectory(traj1)
        is_atif2 = is_atif_trajectory(traj2)

        table.add_row("Format", "ATIF" if is_atif1 else "Legacy", "ATIF" if is_atif2 else "Legacy")

        # Extract metrics
        if is_atif1 and is_atif2:
            # ATIF comparison
            extra1 = traj1.get("extra", {})
            extra2 = traj2.get("extra", {})
            metrics1 = traj1.get("final_metrics", {})
            metrics2 = traj2.get("final_metrics", {})

            table.add_row("Score", f"{extra1.get('total_score', 0.0):.2f}", f"{extra2.get('total_score', 0.0):.2f}")
            table.add_row("Duration", f"{extra1.get('total_time_seconds', 0.0):.2f}s", f"{extra2.get('total_time_seconds', 0.0):.2f}s")
            table.add_row("Steps", str(metrics1.get("total_steps", 0)), str(metrics2.get("total_steps", 0)))
            table.add_row("Model", traj1.get("agent", {}).get("model_name", "unknown"), traj2.get("agent", {}).get("model_name", "unknown"))

            if metrics1.get("total_cost_usd") or metrics2.get("total_cost_usd"):
                table.add_row(
                    "Cost",
                    f"${metrics1.get('total_cost_usd', 0.0):.4f}",
                    f"${metrics2.get('total_cost_usd', 0.0):.4f}"
                )

        else:
            # Legacy comparison
            info1 = traj1.get("info", {})
            info2 = traj2.get("info", {})

            table.add_row("Score", f"{info1.get('total_score', 0.0):.2f}", f"{info2.get('total_score', 0.0):.2f}")
            table.add_row("Duration", f"{info1.get('total_time_seconds', 0.0):.2f}s", f"{info2.get('total_time_seconds', 0.0):.2f}s")
            table.add_row("Model", info1.get("model", "unknown"), info2.get("model", "unknown"))

        console.print(table)

    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON: {e}[/red]")
        raise typer.Exit(code=1)


@traces_app.command(name="export")
def export_command(
    trace_path: str = typer.Argument(..., help="Path to trajectory file"),
    output_path: str = typer.Argument(..., help="Output path for exported file"),
    format: str = typer.Option("markdown", "--format", "-f", help="Export format (markdown, text, html)"),
):
    """
    Export trajectory to different formats.

    Examples:

        # Export to markdown
        uv run python -m terraform_llm.cli traces export trace.traj.json trace.md --format markdown
    """
    path = Path(trace_path)
    out_path = Path(output_path)

    if not path.exists():
        console.print(f"[red]Error: File not found: {trace_path}[/red]")
        raise typer.Exit(code=1)

    try:
        with open(path) as f:
            trace = json.load(f)

        if format == "markdown":
            content = _export_markdown(trace)
        elif format == "text":
            content = _export_text(trace)
        else:
            console.print(f"[red]Unsupported format: {format}[/red]")
            raise typer.Exit(code=1)

        with open(out_path, "w") as f:
            f.write(content)

        console.print(f"[green]✓ Exported to {out_path}[/green]")

    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON: {e}[/red]")
        raise typer.Exit(code=1)


def _export_markdown(trace: Dict[str, Any]) -> str:
    """Export trajectory to markdown format."""
    lines = []

    if is_atif_trajectory(trace):
        # ATIF export
        extra = trace.get("extra", {})
        agent = trace.get("agent", {})
        metrics = trace.get("final_metrics", {})

        lines.append(f"# Trajectory: {extra.get('instance_id', trace.get('session_id'))}\n")
        lines.append(f"**Agent:** {agent.get('name')} v{agent.get('version')}\n")
        lines.append(f"**Model:** {agent.get('model_name')}\n")
        lines.append(f"**Score:** {extra.get('total_score', 0.0):.2f}\n")
        lines.append(f"**Duration:** {extra.get('total_time_seconds', 0.0):.2f}s\n")
        lines.append("\n## Problem Statement\n")
        lines.append(f"{extra.get('problem_statement', 'N/A')}\n")

        lines.append("\n## Steps\n")
        for step in trace.get("steps", []):
            step_id = step.get("step_id")
            source = step.get("source")
            message = step.get("message", "")

            lines.append(f"\n### Step {step_id}: {source}\n")
            if isinstance(message, str):
                lines.append(f"{message}\n")

        lines.append("\n## Generated Files\n")
        for filename, content in extra.get("generated_files", {}).items():
            lines.append(f"\n### {filename}\n")
            lines.append(f"```hcl\n{content}\n```\n")

    else:
        # Legacy export
        info = trace.get("info", {})
        lines.append(f"# Trajectory: {trace.get('instance_id')}\n")
        lines.append(f"**Model:** {info.get('model')}\n")
        lines.append(f"**Score:** {info.get('total_score', 0.0):.2f}\n")

    return "".join(lines)


def _export_text(trace: Dict[str, Any]) -> str:
    """Export trajectory to plain text format."""
    return json.dumps(trace, indent=2)


@traces_app.command(name="failures")
def failures_command(
    results_path: str = typer.Argument(
        ...,
        help="Path to benchmark results directory or benchmark_results.json"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Show full output from failed stages"
    ),
):
    """
    Show all failures from a benchmark run.

    Examples:

        # Show failures from a benchmark run
        uv run python -m terraform_llm.cli traces failures output/openai-gpt-5.2/

        # Show failures with full output
        uv run python -m terraform_llm.cli traces failures output/openai-gpt-5.2/ --verbose
    """
    path = Path(results_path)

    if not path.exists():
        console.print(f"[red]Error: Path not found: {results_path}[/red]")
        raise typer.Exit(code=1)

    # Determine if it's a directory or file
    if path.is_dir():
        results_file = path / "benchmark_results.json"
        if not results_file.exists():
            console.print(f"[red]Error: No benchmark_results.json found in {path}[/red]")
            raise typer.Exit(code=1)
    else:
        results_file = path

    try:
        with open(results_file) as f:
            results = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON in {results_file}: {e}[/red]")
        raise typer.Exit(code=1)

    # Extract all instances with failures
    all_results = results.get("results", [])
    failed_instances = []

    for instance in all_results:
        instance_id = instance.get("instance_id", "unknown")
        stages = instance.get("stages", [])
        failed_stages = [s for s in stages if s.get("status") == "failed"]

        if failed_stages:
            failed_instances.append({
                "instance_id": instance_id,
                "total_score": instance.get("total_score", 0.0),
                "failed_stages": failed_stages,
                "all_stages": stages,
            })

    if not failed_instances:
        console.print("[green]✓ No failures found! All instances passed.[/green]")
        raise typer.Exit(code=0)

    # Display summary
    console.print(f"\n[red]Found {len(failed_instances)} instance(s) with failures[/red]")
    console.print(f"[dim]Total instances: {len(all_results)}[/dim]\n")

    # Create summary table
    summary_table = Table(title="Failed Instances Summary", box=box.ROUNDED)
    summary_table.add_column("Instance ID", style="cyan")
    summary_table.add_column("Score", justify="right")
    summary_table.add_column("Failed Stage", style="red")
    summary_table.add_column("Message", style="dim")

    for failed in failed_instances:
        instance_id = failed["instance_id"]
        score = failed["total_score"]

        # Find first failed stage
        first_failure = failed["failed_stages"][0]
        stage_name = first_failure.get("stage", "unknown")
        message = first_failure.get("message", "")

        # Truncate message if too long
        if len(message) > 60 and not verbose:
            message = message[:57] + "..."

        summary_table.add_row(
            instance_id,
            f"{score:.2f}",
            stage_name,
            message
        )

    console.print(summary_table)
    console.print()

    # Display detailed failures
    if verbose:
        console.print("[bold cyan]Detailed Failure Information:[/bold cyan]\n")

        for failed in failed_instances:
            instance_id = failed["instance_id"]
            score = failed["total_score"]

            # Create panel for each instance
            header = f"[bold cyan]Instance:[/bold cyan] {instance_id}\n"
            header += f"[bold cyan]Score:[/bold cyan] {score:.2f}\n"
            header += f"[bold cyan]Failed Stages:[/bold cyan] {len(failed['failed_stages'])}"

            console.print(Panel(header, title="Failed Instance", border_style="red"))
            console.print()

            # Display each failed stage
            for stage in failed["failed_stages"]:
                stage_name = stage.get("stage", "unknown")
                status = stage.get("status", "unknown")
                message = stage.get("message", "")
                output = stage.get("output", "")
                duration = stage.get("duration_seconds", 0.0)

                stage_header = f"""[bold cyan]Stage:[/bold cyan] {stage_name}
[bold cyan]Status:[/bold cyan] [red]{status}[/red]
[bold cyan]Duration:[/bold cyan] {duration:.2f}s
[bold cyan]Message:[/bold cyan] {message}"""

                console.print(Panel(stage_header, border_style="red"))
                console.print()

                # Display output
                if output:
                    render_output(output, "Failed Stage Output")
                    console.print()

            console.print()
    else:
        console.print("[dim]Use --verbose to see full output from failed stages[/dim]")


# Backward compatibility: keep traces_command as alias to show_command
def traces_command(*args, **kwargs):
    """Deprecated: use 'traces show' instead."""
    return show_command(*args, **kwargs)
