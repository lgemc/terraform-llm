"""CLI command for running benchmarks with tracing."""

from typing import Optional, List
import typer

from ..agent.runner import BenchmarkRunner
from ..agent.terraform_agent import TerraformAgent
from ..model.client import create_client
from ..logging import ConsoleLogger, LogLevel


def run_command(
    dataset: str = typer.Argument(
        ...,
        help="Path to dataset file or folder (e.g., dataset/, examples/sample_dataset.jsonl)"
    ),
    instance_id: Optional[str] = typer.Option(
        None,
        "--instance-id", "-i",
        help="Run specific instance by ID"
    ),
    output_dir: str = typer.Option(
        "output",
        "--output-dir", "-o",
        help="Directory for terraform execution outputs"
    ),
    traces_dir: str = typer.Option(
        "traces",
        "--traces-dir", "-t",
        help="Directory for execution traces (creates timestamped subdirectories)"
    ),
    run_name: Optional[str] = typer.Option(
        None,
        "--run-name", "-n",
        help="Name prefix for this run (defaults to timestamp)"
    ),
    no_cleanup: bool = typer.Option(
        False,
        "--no-cleanup",
        help="Don't destroy infrastructure after validation"
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit", "-l",
        help="Maximum number of instances to run"
    ),
    difficulty: Optional[str] = typer.Option(
        None,
        "--difficulty", "-d",
        help="Filter by difficulty (easy, medium, hard)"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider", "-p",
        help="Filter by cloud provider (aws, azure, gcp)"
    ),
    tags: Optional[List[str]] = typer.Option(
        None,
        "--tag",
        help="Filter by tags (can be specified multiple times)"
    ),
    model_provider: Optional[str] = typer.Option(
        None,
        "--model",
        help="Model provider for code generation (anthropic or openai)"
    ),
    model_name: Optional[str] = typer.Option(
        None,
        "--model-name",
        help="Specific model to use (e.g., claude-3-5-sonnet-20241022, gpt-4)"
    ),
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        help="API key for model provider (defaults to environment variable)"
    ),
    max_iterations: int = typer.Option(
        3,
        "--max-iterations",
        help="Maximum fix attempts for code generation"
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Verbose output during code generation"
    ),
    skip_generation: bool = typer.Option(
        False,
        "--skip-generation",
        help="Skip code generation and reuse existing Terraform files from output directory"
    ),
    use_docker: bool = typer.Option(
        True,
        "--docker/--no-docker",
        help="Use Docker + LocalStack for isolated execution (recommended)"
    ),
    terraform_image: str = typer.Option(
        "hashicorp/terraform:latest",
        "--terraform-image",
        help="Docker image for Terraform"
    ),
    localstack_image: str = typer.Option(
        "localstack/localstack:latest",
        "--localstack-image",
        help="Docker image for LocalStack"
    ),
):
    """
    Run benchmarks from a dataset with execution tracing.

    By default, uses Docker + LocalStack for isolated AWS infrastructure testing.

    Examples:

        # Run with agent code generation (Docker + LocalStack)
        terraform-llm run examples/sample_dataset.jsonl --model anthropic

        # Run specific instance with agent
        terraform-llm run dataset/ --instance-id terraform-aws-lambda-vpc-001 --model anthropic

        # Run with specific model
        terraform-llm run dataset/ --model openai --model-name gpt-4

        # Run with filters
        terraform-llm run dataset/ --difficulty easy --provider aws --limit 5 --model anthropic

        # Run with custom Docker images
        terraform-llm run dataset/ --terraform-image hashicorp/terraform:1.6 \\
          --localstack-image localstack/localstack:3.0

        # Run without Docker (not recommended, requires terraform and AWS on host)
        terraform-llm run dataset/ --no-docker --model anthropic

        # Run without cleanup (for debugging)
        terraform-llm run dataset/ --instance-id test-001 --no-cleanup --model anthropic

        # Reuse existing generated code and only run validation
        terraform-llm run examples/sample_dataset.jsonl --skip-generation

    The traces are saved in mini-swe-agent compatible format at:
    traces/YYYY-MM-DD_HH_mm_ss/ (or traces/<run-name>_YYYY-MM-DD_HH_mm_ss/)
    """
    cleanup = not no_cleanup

    # Initialize logger
    log_level = LogLevel.DEBUG if verbose else LogLevel.INFO
    logger = ConsoleLogger(
        min_level=log_level,
        colored=True,
        show_timestamp=verbose,  # Only show timestamps in verbose mode
        show_data=True,
        compact=False
    )

    # Handle skip_generation flag
    if skip_generation:
        logger.info("config.skip_generation", "Skipping code generation - will reuse existing files", {
            "output_dir": output_dir
        })
        if model_provider:
            logger.warning("config.model_ignored", "Model provider will be ignored with --skip-generation", {
                "provider": model_provider
            })

    # Initialize agent if model provider specified
    agent = None
    if model_provider and not skip_generation:
        try:
            model_client = create_client(
                provider=model_provider,
                api_key=api_key,
                model=model_name
            )
            agent = TerraformAgent(
                model_client=model_client,
                max_iterations=max_iterations,
                verbose=verbose
            )
            logger.info("agent.initialized", f"Initialized {model_provider} agent", {
                "provider": model_provider,
                "model": model_name or "default"
            })
        except Exception as e:
            logger.error("agent.init_failed", f"Error initializing agent: {e}", {
                "provider": model_provider,
                "error": str(e)
            })
            raise typer.Exit(code=1)

    # Initialize runner
    runner = BenchmarkRunner(
        dataset_path=dataset,
        output_dir=output_dir,
        traces_dir=traces_dir,
        agent=agent,
        logger=logger,
        use_docker=use_docker,
        terraform_image=terraform_image,
        localstack_image=localstack_image,
        skip_generation=skip_generation
    )

    try:
        if instance_id:
            # Run single instance
            result = runner.run_instance(
                instance_id=instance_id,
                cleanup=cleanup,
                run_name=run_name
            )
        else:
            # Run all instances with filters
            summary = runner.run_all(
                cleanup=cleanup,
                run_name=run_name,
                limit=limit,
                difficulty=difficulty,
                provider=provider,
                tags=tags
            )

    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
