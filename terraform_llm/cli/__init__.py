"""Command-line interface for terraform-bench."""

import typer

from terraform_llm.cli.benchmark import benchmark_command
from terraform_llm.cli.generate import generate_command
from terraform_llm.cli.list import list_command
from terraform_llm.cli.traces import traces_command
from terraform_llm.cli.leaderboard import leaderboard_command
from terraform_llm.cli.datasets import datasets_app

app = typer.Typer(help="Terraform Agent Benchmark - AI agent evaluation framework")

# Register main commands
app.command(name="benchmark")(benchmark_command)
app.command(name="generate")(generate_command)
app.command(name="list")(list_command)
app.command(name="traces")(traces_command)
app.command(name="leaderboard")(leaderboard_command)

# Register subcommand groups
app.add_typer(datasets_app, name="datasets")


def main():
    """Main CLI entry point."""
    app()


__all__ = ["app", "main"]
