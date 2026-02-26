# CLAUDE.md

## What this project does

Benchmark that measures how well LLMs generate Terraform. An LLM gets a problem statement, produces `.tf` files, then the pipeline runs `init → validate → plan → apply` and scores each stage (weighted: init 10%, validate 20%, plan 40%, apply 20%, validation script 10%).

## CLI

```bash
# Run benchmark (Docker + LocalStack by default)
uv run python -m terraform_llm.cli benchmark dataset/ -o output --model anthropic/claude-sonnet-4-5-20250929

# Run single instance
uv run python -m terraform_llm.cli benchmark dataset/ -o output --instance-id terraform-aws-s3-001

# Run without Docker (needs terraform on host)
uv run python -m terraform_llm.cli benchmark dataset/ -o output --no-docker

# Run with apply (default is plan-only)
uv run python -m terraform_llm.cli benchmark dataset/ -o output --run-apply

# Skip LLM generation, reuse existing .tf files
uv run python -m terraform_llm.cli benchmark dataset/ -o output --skip-generation

# Generate terraform from a prompt
uv run python -m terraform_llm.cli generate "Create an S3 bucket" -o output
```

## How the agent works

1. `agent/models.py` — Calls LLM via litellm to generate `.tf` files from a problem statement
2. `agent/environment.py` — `TerraformEnvironment` runs terraform commands. Accepts an optional `docker_env` (`LocalstackDockerEnvironment`) to route commands through Docker instead of local subprocess
3. `agent/evaluator.py` — `evaluate_instance()` runs the full pipeline (setup script → init → validate → plan → apply → validation → destroy), scores each stage, skips remaining stages on failure
4. `agent/agent.py` — `run_instance()` ties generation + evaluation together. `run_benchmark()` loops over a dataset
5. `agent/docker_environment.py` — Manages Docker network, LocalStack container, and runs terraform/validation/setup/cleanup scripts in containers

## Dataset structure

Each dataset lives in `dataset/<name>/` with a JSONL file. Each line is one instance:

```json
{
  "instance_id": "terraform-aws-s3-001",
  "problem_statement": "Create an S3 bucket with versioning",
  "difficulty": "easy",
  "tags": ["aws", "s3"],
  "provider": "aws",
  "region": "us-east-1",
  "expected_resources": {"aws_s3_bucket": 1},
  "validation_script": "dataset/simple_s3/validation.py",
  "metadata": {"estimated_cost": "$0.02/month", "deployment_time_seconds": 30},
  "gold_solution": {"main.tf": "..."},
  "hints": ["Use aws_s3_bucket_versioning as a separate resource"],
  "setup_script": null
}
```

Key fields: `expected_resources` drives plan scoring, `validation_script` runs after apply, `setup_script` creates pre-existing infrastructure before terraform runs.

## Key files

- `terraform_llm/agent/` — Core evaluation pipeline
- `terraform_llm/datasets/` — Schema, loader, Dataset class
- `terraform_llm/cli/` — CLI commands (benchmark, generate, list, traces)
- `dataset/` — Benchmark instances (JSONL + validation scripts + gold solutions)
