"""Generate command for creating Terraform code."""

from typing import Optional
from pathlib import Path
import typer
from rich import print as rprint
from rich.console import Console

from ..agent import ModelConfig, generate_hcl, EvalConfig, evaluate_instance
from ..datasets import BenchmarkInstance

console = Console()


def generate_command(
    prompt: str = typer.Argument(..., help="Infrastructure description"),
    output_dir: str = typer.Option(..., "-o", "--output-dir", help="Output directory"),
    model: str = typer.Option("anthropic/claude-3-5-sonnet-20241022", help="Model identifier"),
    temperature: float = typer.Option(0.0, help="Model temperature"),
    cloud_provider: str = typer.Option("aws", help="Cloud provider (aws/azure/gcp)"),
    region: str = typer.Option("us-east-1", help="Default region"),
    validate: bool = typer.Option(True, help="Run terraform validate on generated code"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output")
):
    """Generate Terraform code from a prompt."""
    rprint("[bold]Generating Terraform code...[/bold]")

    # Create model configuration
    model_config = ModelConfig(
        model=model,
        temperature=temperature,
    )

    # Generate code
    try:
        code = generate_hcl(
            config=model_config,
            problem_statement=prompt,
            provider=cloud_provider,
            region=region,
        )
    except Exception as e:
        console.print(f"\n[red]✗[/red] Failed to generate code: {e}")
        raise typer.Exit(code=1)

    # Save to output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for filename, content in code.items():
        file_path = output_path / filename
        file_path.write_text(content)

    console.print(f"\n[green]✓[/green] Generated {len(code)} file(s)")
    console.print(f"\n[bold]Code saved to:[/bold] {output_dir}/")

    # Optionally validate
    if validate:
        console.print("\n[bold]Validating generated code...[/bold]")

        # Create a temporary instance for validation
        instance = BenchmarkInstance(
            instance_id="generate-cmd",
            problem_statement=prompt,
            difficulty="easy",
            tags=[],
            provider=cloud_provider,
            region=region,
            expected_resources={},
        )

        eval_config = EvalConfig(run_apply=False)
        result = evaluate_instance(instance, code, eval_config)

        # Check validation results
        init_stage = next((s for s in result.stages if s.stage == "init"), None)
        validate_stage = next((s for s in result.stages if s.stage == "validate"), None)

        if init_stage and init_stage.score == 1.0:
            console.print(f"[green]✓[/green] terraform init: passed")
        else:
            console.print(f"[red]✗[/red] terraform init: failed")

        if validate_stage and validate_stage.score == 1.0:
            console.print(f"[green]✓[/green] terraform validate: passed")
        else:
            console.print(f"[red]✗[/red] terraform validate: failed")

    # Display generated code
    console.print("\n" + "=" * 60)
    console.print("[bold]main.tf[/bold]")
    console.print("=" * 60)
    console.print(code.get('main.tf', ''))
