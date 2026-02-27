"""CLI command for indexing Terraform provider documentation."""

import logging
from pathlib import Path
import typer
from rich.console import Console

from terraform_llm.tools.search.indexer import DocumentIndexer

console = Console()
logger = logging.getLogger(__name__)


def index_docs_command(
    docs_path: str = typer.Argument(
        ...,
        help="Path to provider documentation directory (e.g., terraform-provider-aws/website/docs/r/)",
    ),
    output_index: str = typer.Argument(
        ...,
        help="Output directory for search index",
    ),
    provider: str = typer.Option(
        "aws",
        "--provider",
        "-p",
        help="Provider name (e.g., aws, google, azurerm)",
    ),
    file_pattern: str = typer.Option(
        "*.markdown",
        "--pattern",
        help="Glob pattern for markdown files",
    ),
    embedding_model: str = typer.Option(
        "sentence-transformers/all-MiniLM-L6-v2",
        "--embedding-model",
        "-e",
        help="Sentence transformer model for embeddings",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
):
    """
    Index Terraform provider documentation for hybrid search.

    This command parses provider documentation markdown files and builds
    a hybrid search index combining BM25 (keyword) and semantic (embedding)
    search for efficient retrieval.

    Example:
        uv run python -m terraform_llm.cli index-docs \\
            terraform-provider-aws/website/docs/r/ \\
            output/tf_index/ \\
            --provider aws
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    docs_dir = Path(docs_path)
    output_dir = Path(output_index)

    # Validate inputs
    if not docs_dir.exists():
        console.print(f"[red]Error: Documentation directory not found: {docs_dir}[/red]")
        raise typer.Exit(code=1)

    if not docs_dir.is_dir():
        console.print(f"[red]Error: Path is not a directory: {docs_dir}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Indexing Terraform Provider Documentation[/bold]")
    console.print(f"Provider: {provider}")
    console.print(f"Docs path: {docs_dir}")
    console.print(f"Output index: {output_dir}")
    console.print(f"Embedding model: {embedding_model}")
    console.print("")

    try:
        # Create indexer
        indexer = DocumentIndexer(embedding_model=embedding_model)

        # Index documents
        console.print("[bold]Step 1: Parsing documentation files...[/bold]")
        num_docs = indexer.index_directory(docs_dir, provider, file_pattern)

        if num_docs == 0:
            console.print(f"[red]Error: No documents found matching pattern '{file_pattern}' in {docs_dir}[/red]")
            raise typer.Exit(code=1)

        console.print(f"[green]✓ Parsed {num_docs} documents[/green]")
        console.print("")

        # Build indices
        console.print("[bold]Step 2: Building search indices...[/bold]")
        console.print("  - Building BM25 keyword index...")
        console.print("  - Generating semantic embeddings (this may take a few minutes)...")

        indexer.build_indices(output_dir)

        console.print(f"[green]✓ Index built successfully[/green]")
        console.print("")

        # Summary
        console.print("[bold green]Index created successfully![/bold green]")
        console.print(f"Location: {output_dir}")
        console.print(f"Documents: {num_docs}")
        console.print("")
        console.print("To use this index with the benchmark:")
        console.print(f"  uv run python -m terraform_llm.cli benchmark dataset/ \\")
        console.print(f"    --agent-type tool-enabled \\")
        console.print(f"    --docs-index-path {output_dir}")

    except Exception as e:
        console.print(f"[red]Error during indexing: {e}[/red]")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(code=1)
