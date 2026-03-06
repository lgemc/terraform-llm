# Terraform LLM Benchmark Dashboard

Interactive web dashboard for visualizing terraform-agent benchmark results.

## Features

- **Multi-model Comparison** - Compare results from multiple benchmark runs side-by-side
- **Instance Details** - View generated Terraform code, execution stages, and error diagnostics
- **Iteration Timeline** - For multiturn runs, see how the agent improved across iterations
- **Configuration Display** - View all model, eval, and execution parameters used for each run
- **Interactive Filtering** - Group instances by category, filter by status, sort by score
- **ATIF Support** - Automatically converts ATIF trajectory format to dashboard format

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Open http://localhost:5173 in your browser.

## Usage

### Auto-load from output directory

The dashboard automatically scans `../output/` for:
- `benchmark_results.json` files
- `.traj.json` trajectory files

If found, results are loaded automatically on startup.

### Manual file upload

If no output directory is found, you can:
1. Upload a `benchmark_results.json` file
2. Upload multiple `.traj.json` files
3. Select a directory containing results

### Viewing Results

- **Sidebar**: Browse instances grouped by category
- **Config Panel**: Click to expand and view run configuration
- **Instance Detail**: Click an instance to view:
  - Problem statement
  - Generated Terraform code
  - Execution stages (init, validate, plan, apply)
  - Error diagnostics with line numbers
  - For multiturn: iteration-by-iteration progress

### Multiturn Runs

For runs with `--multiturn` enabled, the dashboard shows:
- Total iterations attempted
- Best score achieved across all iterations
- Score progression (+/- changes between iterations)
- Refinement feedback given to the agent
- Stage-by-stage comparison across iterations

## Configuration Display

The new ConfigPanel shows:

**Model Configuration:**
- Model name and type
- Temperature, max tokens
- Agent type (simple vs tool-enabled)
- Multiturn settings
- Reasoning effort (if applicable)

**Evaluation Configuration:**
- Docker/local execution mode
- Backend (LocalStack vs Moto)
- Docker images used
- Timeouts for each stage

**Execution Configuration:**
- Number of parallel workers
- Skip generation flag
- Output directory

## Development

```bash
# Run development server with hot reload
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

## Architecture

- **React + TypeScript** - Component-based UI
- **Vite** - Fast development and build
- **Tailwind CSS + shadcn/ui** - Styling and components
- **Custom Vite Plugin** - Serves `../output/` directory via API

The dashboard reads files from the output directory without needing a separate backend server.

## File Format Support

- **ATIF v1.6** - Agent Trajectory Interchange Format
- **Legacy format** - Original terraform-agent format
- **benchmark_results.json** - Aggregate results file

ATIF trajectories are automatically converted to the dashboard's internal format.
