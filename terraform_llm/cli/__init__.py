"""Command-line interface for terraform-bench."""

import typer

from terraform_llm.cli.benchmark import benchmark_command
from terraform_llm.cli.generate import generate_command
from terraform_llm.cli.list import list_command
from terraform_llm.cli.traces import traces_app
from terraform_llm.cli.leaderboard import leaderboard_command
from terraform_llm.cli.datasets import datasets_app
from terraform_llm.cli.index_docs import index_docs_command
from terraform_llm.cli.rag import rag_command

app = typer.Typer(help="Terraform Agent Benchmark - AI agent evaluation framework")

# Register main commands
app.command(name="benchmark")(benchmark_command)
app.command(name="generate")(generate_command)
app.command(name="list")(list_command)
app.command(name="leaderboard")(leaderboard_command)
app.command(name="index-docs")(index_docs_command)
app.command(name="rag")(rag_command)

# Register subcommand groups
app.add_typer(datasets_app, name="datasets")
app.add_typer(traces_app, name="traces")


def main():
    """Main CLI entry point."""
    app()


__all__ = ["app", "main"]
