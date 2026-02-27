"""CLI command for testing hybrid search index."""

import typer
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from terraform_llm.tools.search import HybridSearch

console = Console()


def rag_command(
    query: str = typer.Argument(
        ...,
        help="Search query (e.g., 'aws lambda alias', 's3 bucket versioning')",
    ),
    index_path: str = typer.Argument(
        ...,
        help="Path to hybrid search index directory",
    ),
    top_k: int = typer.Option(
        5,
        "--top-k",
        "-k",
        help="Number of results to return",
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        "-p",
        help="Filter by provider (e.g., 'aws', 'google', 'azurerm')",
    ),
    show_full: bool = typer.Option(
        False,
        "--full",
        "-f",
        help="Show full document content (not just formatted summary)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show detailed search scores and metadata",
    ),
):
    """
    Test hybrid search index by querying for Terraform documentation.

    This command allows you to test the hybrid search index built with
    'index-docs' to see what documentation would be retrieved for a given query.

    Examples:
        # Search for Lambda alias documentation
        uv run python -m terraform_llm.cli rag "lambda alias traffic splitting" output/tf_index/

        # Search with provider filter
        uv run python -m terraform_llm.cli rag "s3 bucket" output/tf_index/ --provider aws

        # Get more results
        uv run python -m terraform_llm.cli rag "vpc configuration" output/tf_index/ --top-k 10
    """
    index_dir = Path(index_path)

    # Validate index path
    if not index_dir.exists():
        console.print(f"[red]Error: Index directory not found: {index_dir}[/red]")
        raise typer.Exit(code=1)

    if not (index_dir / "index_metadata.json").exists():
        console.print(f"[red]Error: Not a valid index directory (missing index_metadata.json): {index_dir}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Hybrid Search Test[/bold]")
    console.print(f"Query: [cyan]{query}[/cyan]")
    console.print(f"Index: {index_dir}")
    if provider:
        console.print(f"Provider filter: [yellow]{provider}[/yellow]")
    console.print("")

    try:
        # Load search index
        console.print("[dim]Loading hybrid search index...[/dim]")
        search = HybridSearch(index_dir)
        console.print(f"[green]✓ Loaded {search.metadata['num_documents']} documents[/green]")
        console.print("")

        # Perform search
        console.print(f"[bold]Searching for top {top_k} results...[/bold]")
        results = search.search(
            query=query,
            top_k=top_k,
            provider_filter=provider,
        )

        if not results:
            console.print("[yellow]No results found. Try a different query or remove provider filter.[/yellow]")
            raise typer.Exit(code=0)

        console.print(f"[green]Found {len(results)} result(s)[/green]")
        console.print("")

        # Display results
        for i, result in enumerate(results, 1):
            # Header
            header = f"[{i}/{len(results)}] {result['resource_id']}"
            if verbose:
                header += f" (score: {result['score']:.4f})"

            console.print(Panel(
                f"[bold]{result['title']}[/bold]\n"
                f"[dim]{result['description']}[/dim]\n\n"
                f"Provider: [cyan]{result['provider']}[/cyan] | "
                f"Category: [yellow]{result['subcategory']}[/yellow]",
                title=header,
                border_style="blue",
            ))

            if show_full:
                # Show full formatted result (as LLM would see it)
                formatted = search.format_result_for_llm(result)
                console.print(Panel(
                    Markdown(f"```hcl\n{formatted}\n```"),
                    title="Formatted Output (LLM View)",
                    border_style="green",
                ))
            else:
                # Show summary
                if result.get("overview"):
                    console.print(f"[bold]Overview:[/bold]")
                    console.print(result["overview"][:300] + "..." if len(result["overview"]) > 300 else result["overview"])
                    console.print("")

                if result.get("arguments_required"):
                    console.print(f"[bold]Required Arguments:[/bold] {', '.join(result['arguments_required'][:5])}")

                if result.get("arguments_optional"):
                    optional_preview = result['arguments_optional'][:5]
                    console.print(f"[bold]Optional Arguments:[/bold] {', '.join(optional_preview)}")
                    if len(result['arguments_optional']) > 5:
                        console.print(f"[dim]... and {len(result['arguments_optional']) - 5} more[/dim]")

                if result.get("examples"):
                    console.print(f"\n[bold]Examples:[/bold] {len(result['examples'])} available")

                if verbose:
                    console.print(f"\n[dim]Attributes: {', '.join(result.get('attributes', [])[:5])}[/dim]")

            console.print("")

        # Summary
        console.print("[bold green]Search complete![/bold green]")
        console.print(f"Tip: Use --full to see formatted output as the LLM agent sees it")
        console.print(f"Tip: Use --verbose to see search scores and more metadata")

    except Exception as e:
        console.print(f"[red]Error during search: {e}[/red]")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(code=1)
