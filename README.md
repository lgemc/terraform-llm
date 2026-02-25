# terraform-llm

A benchmark and training pipeline for building small, specialized LLMs that generate production-quality Terraform — matching the performance of models 10-100x their size.

## Why

Large frontier models (GPT-4, Claude, etc.) can generate decent Terraform, but they're expensive, slow, and overkill for infrastructure-as-code. The hypothesis: a small, fine-tuned model trained on high-quality Terraform data can match or exceed them on this specific task.

This project provides:

1. **A benchmark** to measure how well any LLM generates Terraform, with graded scoring across the full `init -> validate -> plan -> apply` pipeline
2. **A dataset framework** for curating Terraform generation tasks at varying difficulty levels
3. **A runner** that evaluates any model (via litellm) against the benchmark in a single command

The end goal is to train and release a small model (7B-13B parameters) that scores competitively against frontier models on Terraform generation.

## How it works

```
Problem statement ──> LLM ──> .tf files ──> Terraform pipeline ──> Graded score
                                              │
                                              ├── terraform init      (0.1 weight)
                                              ├── terraform validate  (0.2 weight)
                                              ├── terraform plan      (0.4 weight)
                                              ├── terraform apply     (0.2 weight)
                                              └── validation script   (0.1 weight)
```

Each stage produces a score between 0.0 and 1.0. The plan stage compares actual planned resources against expected resources with partial credit — if the benchmark expects 2 S3 buckets and the model produces 1, that's a 0.5 on that resource type, not a zero.

## Project structure

```
terraform_llm/
  datasets/          # Benchmark data layer
    schema.py        # BenchmarkInstance, difficulty levels, validation
    dataset.py       # HuggingFace-style Dataset class (filter, map, split)
    loader.py        # JSONL loading, streaming, save/export
  agent/             # Evaluation runner
    models.py        # LLM abstraction via litellm (any provider)
    environment.py   # Terraform subprocess execution in temp dirs
    evaluator.py     # Graded scoring pipeline + resource comparison
    agent.py         # run_instance, run_benchmark (~60 lines of core logic)
    results.py       # StageResult, InstanceResult, BenchmarkReport
```

## Quick start

```bash
pip install -e .
```

### Run the benchmark

```python
from terraform_llm.datasets import load_dataset
from terraform_llm.agent import ModelConfig, EvalConfig, run_benchmark

dataset = load_dataset("data/benchmark.jsonl")

# Evaluate any model — litellm supports OpenAI, Anthropic, Ollama, HuggingFace, etc.
model = ModelConfig(model="anthropic/claude-sonnet-4-5-20250929")
config = EvalConfig(run_apply=False)  # plan-only mode (no real infra created)

report = run_benchmark(dataset, model, config)
print(f"Mean score: {report.mean_score:.2f}")
print(f"Stage pass rates: {report.stage_pass_rates()}")
```

### Compare models

```python
models = [
    ModelConfig(model="anthropic/claude-sonnet-4-5-20250929"),
    ModelConfig(model="openai/gpt-4o"),
    ModelConfig(model="ollama/llama3:8b"),       # local small model
    ModelConfig(model="ollama/codellama:13b"),    # local code model
]

for model in models:
    report = run_benchmark(dataset, model, EvalConfig())
    print(f"{model.model}: {report.mean_score:.2f}")
```

### Benchmark instance format

Each instance in the JSONL dataset looks like:

```json
{
  "instance_id": "terraform-aws-s3-001",
  "problem_statement": "Create an S3 bucket with versioning enabled and server-side encryption using AES256",
  "difficulty": "easy",
  "tags": ["aws", "s3", "storage"],
  "provider": "aws",
  "region": "us-east-1",
  "expected_resources": {"aws_s3_bucket": 1, "aws_s3_bucket_versioning": 1, "aws_s3_bucket_server_side_encryption_configuration": 1},
  "validation_script": "scripts/validate_s3.sh",
  "metadata": {"estimated_cost": "$0.02/month", "deployment_time_seconds": 30},
  "gold_solution": {"main.tf": "resource \"aws_s3_bucket\" ..."},
  "hints": ["Use aws_s3_bucket_versioning as a separate resource"]
}
```

## Evaluation modes

| Mode | Flag | What happens |
|---|---|---|
| **Plan only** (default) | `run_apply=False` | Runs init/validate/plan. No real infrastructure. Free. |
| **Full apply** | `run_apply=True` | Deploys real infrastructure, runs validation, destroys after. Costs money. |

## Scoring

The benchmark uses graded scoring, not binary pass/fail:

- **init** (10%): Did providers resolve correctly?
- **validate** (20%): Is the HCL syntactically and semantically valid?
- **plan** (40%): Do the planned resources match what's expected? Partial credit for partial matches.
- **apply** (20%): Did the infrastructure deploy successfully?
- **validation script** (10%): Does the deployed infrastructure actually work as intended?

A model that gets to `plan` with correct resources but fails `apply` scores much higher than one that can't even pass `validate`.

## Roadmap

- [ ] Curate initial benchmark dataset (50-100 instances across easy/medium/hard)
- [ ] Baseline frontier models (Claude, GPT-4, Gemini)
- [ ] Baseline open models (Llama, CodeLlama, DeepSeek, Qwen)
- [ ] Fine-tune a small model on gold solutions
- [ ] Evaluate fine-tuned model against baselines
- [ ] Multi-turn agent mode (iterative fix based on terraform errors)

## Requirements

- Python >= 3.12
- Terraform CLI installed and on PATH
- API keys for whichever model provider you want to evaluate (set via environment variables)
