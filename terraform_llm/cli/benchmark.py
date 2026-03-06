"""Benchmark command for running evaluation."""

import json
import time
from typing import Optional, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import typer
from rich import print as rprint
from rich.console import Console
from omegaconf import OmegaConf

from terraform_llm.agent import ModelConfig, EvalConfig, run_instance, generate_hcl
from terraform_llm.agent.evaluator import evaluate_instance
from terraform_llm.agent.results import BenchmarkReport
from terraform_llm.datasets import load_dataset, DatasetLoader
from terraform_llm.tracing.atif_tracer import ATIFTracer

console = Console()
console_lock = threading.Lock()


def process_instance(
    inst,
    idx: int,
    total: int,
    model_config: ModelConfig,
    eval_config: EvalConfig,
    output_base: Path,
    skip_generation: bool,
    verbose: bool,
    docker_env=None,
):
    """Process a single benchmark instance (used for parallel execution)."""
    instance_dir = output_base / inst.instance_id
    instance_dir.mkdir(parents=True, exist_ok=True)
    instance_start = time.time()

    with console_lock:
        console.print(f"\n[{idx}/{total}] Processing: {inst.instance_id}")

    try:
        if skip_generation:
            # Load existing code from instance directory
            if not instance_dir.exists():
                with console_lock:
                    console.print(f"  [red]Error: No existing code found in {instance_dir}[/red]")
                return None

            terraform_code = {}
            for tf_file in instance_dir.glob("*.tf"):
                terraform_code[tf_file.name] = tf_file.read_text()

            if not terraform_code:
                with console_lock:
                    console.print(f"  [red]Error: No .tf files found in {instance_dir}[/red]")
                return None

            with console_lock:
                console.print(f"  Loaded {len(terraform_code)} file(s) from {instance_dir}")

            # Evaluate with persistent work_dir
            instance_result = evaluate_instance(
                inst, terraform_code, eval_config, work_dir=str(instance_dir), docker_env=docker_env,
            )
            instance_result.model = model_config.model
            instance_result.compute_total_score()
        else:
            # Full pipeline: generate + evaluate, using instance_dir as work_dir
            instance_result = run_instance(
                inst, model_config, eval_config, work_dir=str(instance_dir), docker_env=docker_env,
            )

        # Save ATIF trajectory (use from result if available, otherwise build it)
        if instance_result.trajectory:
            atif_traj = instance_result.trajectory
            # Add extra metadata to trajectory
            atif_traj.extra = atif_traj.extra or {}
            atif_traj.extra.update({
                "total_time_seconds": time.time() - instance_start,
                "model_config": model_config.to_dict(),
                "eval_config": eval_config.to_dict(),
            })
        else:
            # Fallback: build trajectory from result (for skip_generation mode)
            tracer = ATIFTracer(agent_version="1.0.0")
            atif_traj = tracer.from_terraform_trajectory(
                instance_id=inst.instance_id,
                problem_statement=inst.problem_statement,
                model=instance_result.model,
                agent_type=model_config.agent_type,
                generated_files=instance_result.generated_files,
                stages=[s.to_dict() for s in instance_result.stages],
                tool_calls=instance_result.tool_calls,
                prompt=instance_result.prompt,
            )

            # Add extra metadata to trajectory
            atif_traj.extra = atif_traj.extra or {}
            atif_traj.extra.update({
                "region": inst.region,
                "expected_resources": inst.expected_resources,
                "total_score": instance_result.total_score,
                "total_time_seconds": time.time() - instance_start,
                "model_config": model_config.to_dict(),
                "eval_config": eval_config.to_dict(),
            })
            if instance_result.error:
                atif_traj.extra["error"] = instance_result.error

        # Save ATIF trajectory
        traj_path = instance_dir / f"{inst.instance_id}.traj.json"
        with open(traj_path, "w") as f:
            json.dump(atif_traj.to_json_dict(exclude_none=True), f, indent=2)

        # Print per-instance result (thread-safe)
        with console_lock:
            score_str = f"{instance_result.total_score:.2f}"
            if instance_result.total_score >= 0.8:
                console.print(f"  [green]Score: {score_str}[/green]")
            else:
                console.print(f"  [yellow]Score: {score_str}[/yellow]")

            for stage in instance_result.stages:
                status_color = "green" if stage.status.value == "passed" else "red"
                if stage.status.value == "skipped":
                    status_color = "dim"
                console.print(f"    {stage.stage}: [{status_color}]{stage.status.value}[/{status_color}] ({stage.score:.2f})")

            if instance_result.error:
                console.print(f"  [red]Error: {instance_result.error}[/red]")

            console.print(f"  Trace: {traj_path}")

        return instance_result

    except Exception as e:
        with console_lock:
            console.print(f"  [red]Error: {e}[/red]")
            if verbose:
                import traceback
                traceback.print_exc()
        return None


def benchmark_command(
    dataset: Optional[str] = typer.Argument(
        None,
        help="Path to dataset file or directory (loads all .jsonl files recursively from directories)",
    ),
    config_file: Optional[str] = typer.Option(
        None,
        "--config-file",
        "-c",
        help="Path to YAML config file (relative to configs/ directory or absolute path)",
    ),
    output_dir: Optional[str] = typer.Option(None, "-o", "--output-dir", help="Output directory"),
    model: Optional[str] = typer.Option(
        None,
        help="Model identifier (e.g., anthropic/claude-sonnet-4-5-20250929, openai/gpt-4o)",
    ),
    temperature: Optional[float] = typer.Option(None, help="Model temperature"),
    max_tokens: Optional[int] = typer.Option(None, help="Maximum tokens for model generation"),
    agent_type: Optional[str] = typer.Option(
        None,
        "--agent-type",
        help="Agent type: 'simple' (direct generation) or 'tool-enabled' (with doc search)",
    ),
    max_tool_iterations: Optional[int] = typer.Option(
        None,
        "--max-tool-iterations",
        help="Maximum iterations for tool-enabled agent",
    ),
    docs_index_path: Optional[str] = typer.Option(
        None,
        "--docs-index-path",
        help="Path to hybrid search index for tool-enabled agent (build with 'index-docs' command)",
    ),
    reasoning_effort: Optional[str] = typer.Option(
        None,
        "--reasoning-effort",
        help="Reasoning effort for reasoning models (low, medium, high) - enables extended thinking",
    ),
    multiturn: Optional[bool] = typer.Option(
        None,
        "--multiturn",
        help="Enable multiturn refinement: agent receives validation feedback and iterates",
    ),
    max_multiturn_iterations: Optional[int] = typer.Option(
        None,
        "--max-multiturn-iterations",
        help="Maximum multiturn refinement iterations (default: 3)",
    ),
    difficulty: Optional[str] = typer.Option(None, help="Filter by difficulty"),
    filter_provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Filter by cloud provider"),
    limit: Optional[int] = typer.Option(None, help="Limit number of instances"),
    instance_id: Optional[str] = typer.Option(
        None, "--instance-id", "-i", help="Run specific instance by ID",
    ),
    tags: Optional[List[str]] = typer.Option(
        None, "--tag", help="Filter by tags (can be specified multiple times)",
    ),
    run_apply: Optional[bool] = typer.Option(None, help="Run terraform apply (creates infrastructure)"),
    use_docker: Optional[bool] = typer.Option(
        None,
        "--docker/--no-docker",
        help="Use Docker + AWS emulator for isolated execution (recommended)",
    ),
    backend: Optional[str] = typer.Option(
        None,
        "--backend",
        help="AWS emulator backend: 'localstack' (paid for RDS) or 'moto' (fully open source)",
    ),
    terraform_image: Optional[str] = typer.Option(
        None,
        "--terraform-image",
        help="Docker image for Terraform",
    ),
    localstack_image: Optional[str] = typer.Option(
        None,
        "--localstack-image",
        help="Docker image for LocalStack",
    ),
    moto_image: Optional[str] = typer.Option(
        None,
        "--moto-image",
        help="Docker image for Moto",
    ),
    skip_generation: Optional[bool] = typer.Option(
        None,
        "--skip-generation",
        help="Skip code generation and reuse existing Terraform files from output directory",
    ),
    verbose: Optional[bool] = typer.Option(None, "-v", "--verbose", help="Verbose output"),
    parallel: Optional[int] = typer.Option(
        None,
        "--parallel",
        "-j",
        help="Number of parallel workers for benchmark execution (default: 3)",
    ),
):
    """Run benchmark evaluation with optional Docker + AWS emulator execution."""

    # Load configuration from YAML file if provided
    if config_file:
        config_path = Path(config_file)
        if not config_path.is_absolute():
            # Try relative to configs/ directory
            config_path = Path("configs") / config_file
            if not config_path.exists():
                # Try with .yaml extension
                config_path = Path("configs") / f"{config_file}.yaml"

        if not config_path.exists():
            console.print(f"[red]Error: Config file not found: {config_file}[/red]")
            raise typer.Exit(code=1)

        console.print(f"[bold]Loading config from:[/bold] {config_path}")
        cfg = OmegaConf.load(config_path)
    else:
        # Load default config
        default_config_path = Path("configs/config.yaml")
        if default_config_path.exists():
            cfg = OmegaConf.load(default_config_path)
        else:
            # Use empty config if no default exists
            cfg = OmegaConf.create({})

    # Override config with CLI arguments (if provided)
    cli_overrides = {}
    if dataset is not None:
        cli_overrides["dataset"] = dataset
    if output_dir is not None:
        cli_overrides["output_dir"] = output_dir
    if model is not None:
        cli_overrides.setdefault("model", {})["model"] = model
    if temperature is not None:
        cli_overrides.setdefault("model", {})["temperature"] = temperature
    if max_tokens is not None:
        cli_overrides.setdefault("model", {})["max_tokens"] = max_tokens
    if agent_type is not None:
        cli_overrides.setdefault("model", {})["agent_type"] = agent_type
    if max_tool_iterations is not None:
        cli_overrides.setdefault("model", {})["max_tool_iterations"] = max_tool_iterations
    if docs_index_path is not None:
        cli_overrides.setdefault("model", {})["docs_index_path"] = docs_index_path
    if reasoning_effort is not None:
        cli_overrides.setdefault("model", {})["reasoning_effort"] = reasoning_effort
    if multiturn is not None:
        cli_overrides.setdefault("model", {})["multiturn"] = multiturn
    if max_multiturn_iterations is not None:
        cli_overrides.setdefault("model", {})["max_multiturn_iterations"] = max_multiturn_iterations
    if difficulty is not None:
        cli_overrides["difficulty"] = difficulty
    if filter_provider is not None:
        cli_overrides["provider"] = filter_provider
    if limit is not None:
        cli_overrides["limit"] = limit
    if instance_id is not None:
        cli_overrides["instance_id"] = instance_id
    if tags is not None:
        cli_overrides["tags"] = tags
    if run_apply is not None:
        cli_overrides.setdefault("eval", {})["run_apply"] = run_apply
    if use_docker is not None:
        cli_overrides.setdefault("eval", {})["use_docker"] = use_docker
    if backend is not None:
        cli_overrides.setdefault("eval", {})["backend"] = backend
    if terraform_image is not None:
        cli_overrides.setdefault("eval", {})["terraform_image"] = terraform_image
    if localstack_image is not None:
        cli_overrides.setdefault("eval", {})["localstack_image"] = localstack_image
    if moto_image is not None:
        cli_overrides.setdefault("eval", {})["moto_image"] = moto_image
    if skip_generation is not None:
        cli_overrides.setdefault("execution", {})["skip_generation"] = skip_generation
    if verbose is not None:
        cli_overrides.setdefault("execution", {})["verbose"] = verbose
    if parallel is not None:
        cli_overrides.setdefault("execution", {})["parallel"] = parallel

    # Merge CLI overrides into config
    cfg = OmegaConf.merge(cfg, OmegaConf.create(cli_overrides))

    # Extract values from config with defaults
    dataset = cfg.get("dataset", "dataset/")
    output_dir = cfg.get("output_dir", "output")
    difficulty = cfg.get("difficulty", None)
    filter_provider = cfg.get("provider", None)
    limit = cfg.get("limit", None)
    instance_id = cfg.get("instance_id", None)
    tags = cfg.get("tags", None)

    # Model config
    model_cfg = cfg.get("model", {})
    model = model_cfg.get("model", "anthropic/claude-3-5-sonnet-20241022")
    temperature = model_cfg.get("temperature", 0.0)
    max_tokens = model_cfg.get("max_tokens", 16384)
    agent_type = model_cfg.get("agent_type", "simple")
    max_tool_iterations = model_cfg.get("max_tool_iterations", 5)
    docs_index_path = model_cfg.get("docs_index_path", None)
    reasoning_effort = model_cfg.get("reasoning_effort", None)
    multiturn = model_cfg.get("multiturn", False)
    max_multiturn_iterations = model_cfg.get("max_multiturn_iterations", 3)

    # Eval config
    eval_cfg = cfg.get("eval", {})
    run_apply = eval_cfg.get("run_apply", True)
    use_docker = eval_cfg.get("use_docker", True)
    backend = eval_cfg.get("backend", "localstack")
    terraform_image = eval_cfg.get("terraform_image", "hashicorp/terraform:latest")
    localstack_image = eval_cfg.get("localstack_image", "localstack/localstack:latest")
    moto_image = eval_cfg.get("moto_image", "motoserver/moto:latest")

    # Execution config
    exec_cfg = cfg.get("execution", {})
    skip_generation = exec_cfg.get("skip_generation", False)
    verbose = exec_cfg.get("verbose", False)
    parallel = exec_cfg.get("parallel", 3)

    # Print configuration summary
    console.print("\n" + "=" * 80)
    console.print("[bold cyan]BENCHMARK CONFIGURATION[/bold cyan]", justify="center")
    console.print("=" * 80)

    if config_file:
        console.print(f"[bold]Config file:[/bold] {config_path}")

    console.print("\n[bold yellow]Dataset Configuration:[/bold yellow]")
    console.print(f"  Dataset path: {dataset}")
    console.print(f"  Output directory: {output_dir}")
    if instance_id:
        console.print(f"  Instance ID: {instance_id}")
    if difficulty:
        console.print(f"  Difficulty filter: {difficulty}")
    if filter_provider:
        console.print(f"  Provider filter: {filter_provider}")
    if tags:
        console.print(f"  Tags filter: {tags}")
    if limit:
        console.print(f"  Limit: {limit} instances")

    console.print("\n[bold yellow]Model Configuration:[/bold yellow]")
    console.print(f"  Model: {model}")
    console.print(f"  Temperature: {temperature}")
    console.print(f"  Max tokens: {max_tokens}")
    console.print(f"  Agent type: {agent_type}")
    if agent_type == "tool-enabled":
        console.print(f"  Max tool iterations: {max_tool_iterations}")
        console.print(f"  Docs index path: {docs_index_path}")
    if reasoning_effort:
        console.print(f"  Reasoning effort: {reasoning_effort}")
    console.print(f"  Multiturn: {multiturn}")
    if multiturn:
        console.print(f"  Max multiturn iterations: {max_multiturn_iterations}")

    console.print("\n[bold yellow]Evaluation Configuration:[/bold yellow]")
    console.print(f"  Run apply: {run_apply}")
    console.print(f"  Use Docker: {use_docker}")
    if use_docker:
        console.print(f"  Backend: {backend}")
        console.print(f"  Terraform image: {terraform_image}")
        if backend == "localstack":
            console.print(f"  LocalStack image: {localstack_image}")
        elif backend == "moto":
            console.print(f"  Moto image: {moto_image}")

    console.print("\n[bold yellow]Execution Configuration:[/bold yellow]")
    console.print(f"  Parallel workers: {parallel}")
    console.print(f"  Skip generation: {skip_generation}")
    console.print(f"  Verbose: {verbose}")

    console.print("=" * 80 + "\n")

    # Load dataset
    try:
        if instance_id:
            loader = DatasetLoader(dataset)
            instance = loader.get_by_id(instance_id)
            if not instance:
                console.print(f"[red]Error: Instance {instance_id} not found in dataset[/red]")
                raise typer.Exit(code=1)
            instances = [instance]
        else:
            dataset_obj = load_dataset(
                dataset,
                difficulty=difficulty,
                provider=filter_provider,
                tags=tags,
                limit=limit,
            )
            instances = list(dataset_obj)

        if not instances:
            console.print("[red]No instances found matching the filters[/red]")
            raise typer.Exit(code=1)

        console.print(f"[bold green]Loaded {len(instances)} instance(s) for processing[/bold green]\n")

    except FileNotFoundError:
        console.print(f"[red]Error: Dataset not found: {dataset}[/red]")
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error loading dataset: {e}[/red]")
        raise typer.Exit(code=1)

    # Create model configuration
    model_config = ModelConfig(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        agent_type=agent_type,
        max_tool_iterations=max_tool_iterations,
        docs_index_path=docs_index_path,
        reasoning_effort=reasoning_effort,
        multiturn=multiturn,
        max_multiturn_iterations=max_multiturn_iterations,
    )

    # Validate backend choice
    if backend not in ["localstack", "moto"]:
        console.print(f"[red]Error: Invalid backend '{backend}'. Must be 'localstack' or 'moto'[/red]")
        raise typer.Exit(code=1)

    # Create evaluation configuration
    eval_config = EvalConfig(
        run_apply=run_apply,
        run_destroy=True,
        run_validation=run_apply,
        use_docker=use_docker,
        backend=backend,
        terraform_image=terraform_image,
        localstack_image=localstack_image,
        moto_image=moto_image,
    )

    # Process instances
    report = BenchmarkReport(model=model_config.model)
    output_base = Path(output_dir)

    # Create shared docker environment for all instances
    shared_docker_env = None
    if use_docker:
        env_label = "shared" if parallel > 1 else "Docker"
        console.print(f"[bold]Creating {env_label} {backend.capitalize()} environment...[/bold]")

        if backend == "localstack":
            from terraform_llm.agent.docker_environment import LocalstackDockerEnvironment
            shared_docker_env = LocalstackDockerEnvironment(
                work_dir=str(output_base),
                image=terraform_image,
                localstack_image=localstack_image,
            )
        elif backend == "moto":
            from terraform_llm.agent.moto_environment import MotoDockerEnvironment
            shared_docker_env = MotoDockerEnvironment(
                work_dir=str(output_base),
                image=terraform_image,
                moto_image=moto_image,
            )

        console.print(f"[green]{backend.capitalize()} environment ready[/green]")

    # Choose parallel or sequential execution
    try:
        if parallel > 1:
            rprint(f"[bold]Using {parallel} parallel workers[/bold]")

            # Process instances in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                # Submit all instances for processing
                futures = {}
                for idx, inst in enumerate(instances, 1):
                    future = executor.submit(
                        process_instance,
                        inst,
                        idx,
                        len(instances),
                        model_config,
                        eval_config,
                        output_base,
                        skip_generation,
                        verbose,
                        shared_docker_env,
                    )
                    futures[future] = inst

                # Collect results as they complete
                for future in as_completed(futures):
                    instance_result = future.result()
                    if instance_result:
                        report.results.append(instance_result)
        else:
            # Sequential execution (original behavior)
            for idx, inst in enumerate(instances, 1):
                instance_result = process_instance(
                    inst,
                    idx,
                    len(instances),
                    model_config,
                    eval_config,
                    output_base,
                    skip_generation,
                    verbose,
                    shared_docker_env,
                )
                if instance_result:
                    report.results.append(instance_result)
    finally:
        # Clean up docker environment
        if shared_docker_env is not None:
            console.print("\n[bold]Cleaning up Docker environment...[/bold]")
            shared_docker_env.cleanup()
            console.print("[green]Cleanup complete[/green]")

    # Print summary
    console.print("\n" + "=" * 60)
    console.print("[bold]BENCHMARK RESULTS[/bold]", justify="center")
    console.print("=" * 60)
    console.print(f"Model: {model_config.model}")
    console.print(f"Execution: {'Docker + ' + backend.capitalize() if use_docker else 'Local'}")
    console.print(f"Total instances: {len(report.results)}")
    console.print(f"Mean score: {report.mean_score:.2f}")

    # Calculate pass rate (score >= 0.8)
    passed = sum(1 for r in report.results if r.total_score >= 0.8)
    pass_rate = passed / len(report.results) if report.results else 0.0
    console.print(f"[green]Passed (score >= 0.8):[/green] {passed}/{len(report.results)} ({pass_rate:.1%})")

    # Stage pass rates
    console.print("\n[bold]Stage pass rates:[/bold]")
    stage_rates = report.stage_pass_rates()
    for stage, rate in stage_rates.items():
        console.print(f"  {stage}: {rate:.1%}")

    # Save aggregate results with metadata
    results_data = report.to_dict()
    results_data["model_config"] = model_config.to_dict()
    results_data["eval_config"] = eval_config.to_dict()
    results_data["execution_config"] = {
        "parallel": parallel,
        "skip_generation": skip_generation,
        "verbose": verbose,
    }
    if config_file:
        results_data["config_file"] = str(config_path)
    results_data["output_dir"] = str(output_base)

    results_path = output_base / "benchmark_results.json"
    with open(results_path, "w") as f:
        json.dump(results_data, f, indent=2)
    console.print(f"\n[green]Results saved to:[/green] {results_path}")
