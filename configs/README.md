# Configuration Files

This directory contains YAML configuration files for running benchmark experiments with terraform-agent.

## Structure

```
configs/
├── config.yaml                              # Default configuration
├── experiment/
│   ├── qwen-3.5-4b-multiturn.yaml          # Qwen 3.5 4B experiment
│   └── gpt-oss-120b-multiturn.yaml         # GPT-OSS 120B experiment
└── README.md                                # This file
```

## Usage

### Option 1: Use a config file

```bash
# Set your API endpoint (if using local inference)
export OPENAI_API_BASE="http://192.168.0.9:8000/v1"

# Run with config file (automatically looks in configs/)
uv run python -m terraform_llm.cli benchmark --config-file experiment/qwen-3.5-4b-multiturn

# Or with full path
uv run python -m terraform_llm.cli benchmark --config-file configs/experiment/qwen-3.5-4b-multiturn.yaml
```

### Option 2: Config file + CLI overrides

CLI arguments override config file values:

```bash
# Use config but override parallel workers and output directory
uv run python -m terraform_llm.cli benchmark \
    --config-file experiment/qwen-3.5-4b-multiturn \
    --parallel 10 \
    --output-dir output/custom-experiment
```

### Option 3: Traditional CLI (no config file)

```bash
uv run python -m terraform_llm.cli benchmark dataset/ \
    --model openai/Qwen/Qwen3.5-4B \
    --docs-index-path output/tf_index/ \
    --output-dir output/qwen-3.5:4b-test \
    -j 5 \
    --backend moto \
    --multiturn
```

## Configuration Structure

### Dataset Configuration
```yaml
dataset: dataset/                    # Path to dataset
instance_id: null                    # Run specific instance (null = all)
difficulty: null                     # Filter: easy, medium, hard
provider: null                       # Filter: aws, azure, gcp
tags: null                          # Filter by tags
limit: null                         # Limit number of instances
```

### Model Configuration
```yaml
model:
  model: openai/Qwen/Qwen3.5-4B
  temperature: 0.0
  max_tokens: 16384
  agent_type: simple                # simple or tool-enabled
  max_tool_iterations: 5
  docs_index_path: output/tf_index/ # For tool-enabled agent
  reasoning_effort: null            # low, medium, high (for reasoning models)
  multiturn: true                   # Enable multiturn refinement
  max_multiturn_iterations: 3       # Max refinement iterations
```

### Evaluation Configuration
```yaml
eval:
  run_apply: true
  run_destroy: true
  run_validation: true
  init_timeout: 120
  plan_timeout: 300
  apply_timeout: 600
  use_docker: true
  backend: moto                     # localstack or moto
  terraform_image: hashicorp/terraform:latest
  localstack_image: localstack/localstack:latest
  moto_image: motoserver/moto:latest
```

### Execution Configuration
```yaml
execution:
  parallel: 5                       # Number of parallel workers
  skip_generation: false            # Skip LLM, reuse existing .tf files
  verbose: false
```

### Output Configuration
```yaml
output_dir: output/qwen-3.5:4b-multiturn-3
```

## Creating Your Own Configs

1. Copy an existing config from `experiment/`
2. Modify the parameters for your experiment
3. Save it in `experiment/` with a descriptive name
4. Run with `--config-file experiment/your-config-name`

## What Gets Saved

All trajectory files (`.traj.json`) and `benchmark_results.json` will include:

- **model_config**: All model parameters used
- **eval_config**: All evaluation parameters used
- **execution_config**: Parallel workers, skip_generation, verbose
- **config_file**: Path to config file (if used)

This ensures full reproducibility of experiments.

## Environment Variables

Some configs may require environment variables to be set:

```bash
# For local inference servers
export OPENAI_API_BASE="http://192.168.0.9:8000/v1"

# For cloud APIs (if needed)
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
```

Check the comments in each config file for required environment variables.
