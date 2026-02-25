"""Generate command for creating Terraform code."""

from typing import Optional
import typer
from rich import print as rprint
from rich.console import Console

from ..agent import TerraformAgent
from ..model import create_client

console = Console()


def generate_command(
    prompt: str = typer.Argument(..., help="Infrastructure description"),
    output_dir: str = typer.Option(..., "-o", "--output-dir", help="Output directory"),
    provider: str = typer.Option("anthropic", help="Model provider"),
    model: Optional[str] = typer.Option(None, help="Model identifier"),
    cloud_provider: str = typer.Option("aws", help="Cloud provider (aws/azure/gcp)"),
    region: str = typer.Option("us-east-1", help="Default region"),
    max_iterations: int = typer.Option(3, help="Max fix iterations"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Verbose output")
):
    """Generate Terraform code from a prompt."""
    rprint("[bold]Generating Terraform code...[/bold]")

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

    # Generate code
    result = agent.generate_and_validate(
        problem_statement=prompt,
        provider=cloud_provider,
        region=region,
        work_dir=output_dir
    )

    if result['valid']:
        console.print(f"\n[green]✓[/green] Generated valid Terraform code in {result['iterations']} iteration(s)")
        console.print(f"\n[bold]Code saved to:[/bold] {output_dir}/")
        console.print("\n" + "=" * 60)
        console.print("[bold]main.tf[/bold]")
        console.print("=" * 60)
        console.print(result['code'].get('main.tf', ''))
    else:
        console.print(f"\n[red]✗[/red] Failed to generate valid code after {result['iterations']} attempts")
        console.print(f"[red]Error:[/red] {result.get('error', 'Unknown error')}")
        raise typer.Exit(code=1)
