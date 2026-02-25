"""Dataset management subcommands."""

import typer
from .summary import summary_command
from .visualize import visualize_command, stats_command

datasets_app = typer.Typer(help="Dataset management commands")

# Register commands
datasets_app.command(name="summary")(summary_command)
datasets_app.command(name="visualize")(visualize_command)
datasets_app.command(name="stats")(stats_command)

__all__ = ["datasets_app"]
