"""CLI command for running benchmarks with tracing."""

from typing import Optional, List
from pathlib import Path
import typer

from terraform_llm.agent import ModelConfig, generate_hcl
from terraform_llm.datasets import load_dataset, DatasetLoader
from terraform_llm.runtime import DockerBenchmarkExecutor, BenchmarkExecutor


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

    # Load dataset
    try:
        if instance_id:
            # Load single instance
            loader = DatasetLoader(dataset)
            instance = loader.get_by_id(instance_id)
            if not instance:
                typer.echo(f"Error: Instance {instance_id} not found in dataset", err=True)
                raise typer.Exit(code=1)
            instances = [instance]
        else:
            # Load with filters
            dataset_obj = load_dataset(
                dataset,
                difficulty=difficulty,
                provider=provider,
                tags=tags,
                limit=limit,
            )
            instances = list(dataset_obj)

        if not instances:
            typer.echo("No instances found matching the filters", err=True)
            raise typer.Exit(code=1)

    except FileNotFoundError as e:
        typer.echo(f"Error: Dataset not found: {dataset}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error loading dataset: {e}", err=True)
        raise typer.Exit(code=1)

    # Initialize model configuration if needed
    model_config = None
    if model_provider and not skip_generation:
        try:
            # Map provider shorthand to full model name if needed
            if model_name:
                full_model = model_name
            elif model_provider == "anthropic":
                full_model = "anthropic/claude-3-5-sonnet-20241022"
            elif model_provider == "openai":
                full_model = "openai/gpt-4o"
            else:
                full_model = f"{model_provider}/default"

            model_config = ModelConfig(
                model=full_model,
                temperature=0.0,
            )
            if verbose:
                typer.echo(f"Initialized model: {model_config.model}")
        except Exception as e:
            typer.echo(f"Error initializing model: {e}", err=True)
            raise typer.Exit(code=1)
    elif not skip_generation:
        typer.echo("Error: --model is required (or use --skip-generation)", err=True)
        raise typer.Exit(code=1)

    # Initialize executor
    if use_docker:
        executor = DockerBenchmarkExecutor(
            output_dir=output_dir,
            terraform_image=terraform_image,
            localstack_image=localstack_image,
        )
        typer.echo("Using Docker + Localstack for execution")
    else:
        executor = BenchmarkExecutor(output_dir=output_dir)
        typer.echo("Using local Terraform execution (no Docker)")

    # Process instances
    results = []
    for idx, instance in enumerate(instances, 1):
        typer.echo(f"\n[{idx}/{len(instances)}] Processing: {instance.instance_id}")

        try:
            # Generate code if needed
            if skip_generation:
                # Load existing code from output directory
                instance_dir = Path(output_dir) / instance.instance_id
                if not instance_dir.exists():
                    typer.echo(f"  Error: No existing code found in {instance_dir}", err=True)
                    continue

                terraform_code = {}
                for tf_file in instance_dir.glob("*.tf"):
                    terraform_code[tf_file.name] = tf_file.read_text()

                if not terraform_code:
                    typer.echo(f"  Error: No .tf files found in {instance_dir}", err=True)
                    continue

                typer.echo(f"  Loaded {len(terraform_code)} file(s) from {instance_dir}")
            else:
                # Generate code
                typer.echo("  Generating Terraform code...")
                terraform_code = generate_hcl(
                    config=model_config,
                    problem_statement=instance.problem_statement,
                    provider=instance.provider,
                    region=instance.region,
                    hints=instance.hints,
                )
                typer.echo(f"  Generated {len(terraform_code)} file(s)")

            # Execute
            typer.echo("  Executing...")
            result = executor.execute_instance(
                instance_id=instance.instance_id,
                terraform_code=terraform_code,
                validation_script=instance.validation_script or "",
                region=instance.region,
                expected_resources=instance.expected_resources,
                problem_statement=instance.problem_statement,
                cleanup=cleanup,
            )

            # Print result
            status = "✓ PASSED" if result.get('passed') else "✗ FAILED"
            typer.echo(f"  {status}")

            if 'trace_path' in result and verbose:
                typer.echo(f"  Trace: {result['trace_path']}")

            results.append(result)

        except Exception as e:
            typer.echo(f"  Error: {e}", err=True)
            if verbose:
                import traceback
                traceback.print_exc()

    # Print summary
    if results:
        passed = sum(1 for r in results if r.get('passed'))
        typer.echo(f"\n{'='*60}")
        typer.echo(f"Summary: {passed}/{len(results)} passed ({passed/len(results)*100:.1f}%)")
        typer.echo(f"{'='*60}")
