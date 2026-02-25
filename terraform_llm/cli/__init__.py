"""Command-line interface for terraform-bench."""

import typer

from .benchmark import benchmark_command
from .generate import generate_command
from .list import list_command
from .datasets import datasets_app

app = typer.Typer(help="Terraform Agent Benchmark - AI agent evaluation framework")

# Register main commands
app.command(name="benchmark")(benchmark_command)
app.command(name="generate")(generate_command)
app.command(name="list")(list_command)

# Register subcommand groups
app.add_typer(datasets_app, name="datasets")


def main():
    """Main CLI entry point."""
    app()


__all__ = ["app", "main"]
