"""CLI command for generating leaderboard from benchmark results."""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import typer
from rich.console import Console

console = Console()


def aggregate_benchmark_results(output_dir: Path) -> List[Dict[str, Any]]:
    """
    Aggregate all benchmark_results.json files from output directory.

    Args:
        output_dir: Root output directory containing model subdirectories

    Returns:
        List of aggregated model results with computed metrics
    """
    aggregated = []

    # Find all benchmark_results.json files
    benchmark_files = list(output_dir.glob("*/benchmark_results.json"))

    if not benchmark_files:
        console.print(f"[yellow]No benchmark_results.json files found in {output_dir}[/yellow]")
        return []

    for bench_file in benchmark_files:
        try:
            with open(bench_file) as f:
                data = json.load(f)

            model = data.get("model", "unknown")
            mean_score = data.get("mean_score", 0.0)
            stage_pass_rates = data.get("stage_pass_rates", {})
            num_instances = data.get("num_instances", 0)
            results = data.get("results", [])

            # Compute average time from individual results
            total_time = sum(r.get("total_score", 0) for r in results)
            total_duration = sum(
                sum(s.get("duration_seconds", 0) for s in r.get("stages", []))
                for r in results
            )
            avg_time = total_duration / num_instances if num_instances > 0 else 0.0

            # Count passed instances
            passed_instances = sum(
                1 for r in results
                if all(
                    s.get("status") in ["passed", "skipped"]
                    for s in r.get("stages", [])
                    if s.get("stage") not in ["setup_script", "cleanup_script", "destroy"]
                ) and not any(
                    s.get("status") == "failed"
                    for s in r.get("stages", [])
                )
            )

            aggregated.append({
                "model": model,
                "mean_score": mean_score,
                "init_pass_rate": stage_pass_rates.get("init", 0.0),
                "validate_pass_rate": stage_pass_rates.get("validate", 0.0),
                "plan_pass_rate": stage_pass_rates.get("plan", 0.0),
                "apply_pass_rate": stage_pass_rates.get("apply", 0.0),
                "validation_pass_rate": stage_pass_rates.get("validation_script", 0.0),
                "avg_time": avg_time,
                "num_instances": num_instances,
                "passed_instances": passed_instances,
            })

            console.print(f"[green]✓[/green] Loaded {model}: {num_instances} instances")

        except Exception as e:
            console.print(f"[red]✗[/red] Error loading {bench_file}: {e}")
            continue

    # Sort by mean_score descending
    aggregated.sort(key=lambda x: x["mean_score"], reverse=True)

    return aggregated


def generate_html(data: List[Dict[str, Any]]) -> str:
    """
    Generate self-contained HTML leaderboard with embedded data.

    Args:
        data: List of aggregated model results

    Returns:
        Complete HTML string
    """
    # Convert data to JSON for embedding
    data_json = json.dumps(data, indent=2)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Terraform Agent Leaderboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .sortable:hover {{
            background-color: rgba(59, 130, 246, 0.1);
            cursor: pointer;
        }}
        .sort-indicator {{
            opacity: 0.3;
            margin-left: 0.25rem;
        }}
        .sort-indicator.active {{
            opacity: 1;
        }}
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <!-- Header -->
        <div class="mb-8">
            <h1 class="text-4xl font-bold text-gray-900 mb-2">Terraform Agent Leaderboard</h1>
            <p class="text-gray-600">Benchmark results for LLM-generated Terraform infrastructure</p>
            <p class="text-sm text-gray-500 mt-2">Generated: <span id="timestamp"></span></p>
        </div>

        <!-- Search/Filter -->
        <div class="mb-6">
            <input
                type="text"
                id="searchInput"
                placeholder="Search models..."
                class="w-full md:w-96 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
        </div>

        <!-- Leaderboard Table -->
        <div class="bg-white rounded-lg shadow overflow-hidden">
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-100">
                        <tr>
                            <th class="sortable px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="rank">
                                Rank
                            </th>
                            <th class="sortable px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="model">
                                Model
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="mean_score">
                                Mean Score
                                <span class="sort-indicator active">↓</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="init_pass_rate">
                                Init %
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="validate_pass_rate">
                                Validate %
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="plan_pass_rate">
                                Plan %
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="apply_pass_rate">
                                Apply %
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="validation_pass_rate">
                                Validation %
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="avg_time">
                                Avg Time (s)
                                <span class="sort-indicator">↕</span>
                            </th>
                            <th class="sortable px-6 py-3 text-right text-xs font-medium text-gray-700 uppercase tracking-wider" data-sort="num_instances">
                                Instances
                                <span class="sort-indicator">↕</span>
                            </th>
                        </tr>
                    </thead>
                    <tbody id="tableBody" class="bg-white divide-y divide-gray-200">
                        <!-- Populated by JavaScript -->
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Footer -->
        <div class="mt-8 text-center text-sm text-gray-500">
            <p>Powered by <a href="https://github.com/anthropics/terraform-agent" class="text-blue-600 hover:text-blue-800">Terraform Agent Benchmark</a></p>
        </div>
    </div>

    <script type="application/json" id="leaderboardData">
{data_json}
    </script>

    <script>
        // Load data
        const data = JSON.parse(document.getElementById('leaderboardData').textContent);

        // State
        let currentSort = {{ key: 'mean_score', ascending: false }};
        let filteredData = [...data];

        // Set timestamp
        document.getElementById('timestamp').textContent = new Date().toLocaleString();

        // Render table
        function renderTable() {{
            const tbody = document.getElementById('tableBody');
            tbody.innerHTML = '';

            filteredData.forEach((row, index) => {{
                const tr = document.createElement('tr');
                tr.className = 'hover:bg-gray-50';

                const scoreColor = row.mean_score >= 0.8 ? 'text-green-600' :
                                 row.mean_score >= 0.5 ? 'text-yellow-600' :
                                 'text-red-600';

                const passedRatio = `${{row.passed_instances}}/${{row.num_instances}}`;

                tr.innerHTML = `
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        ${{index + 1}}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        ${{row.model}}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right font-bold ${{scoreColor}}">
                        ${{row.mean_score.toFixed(2)}}
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-700">
                        ${{(row.init_pass_rate * 100).toFixed(1)}}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-700">
                        ${{(row.validate_pass_rate * 100).toFixed(1)}}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-700">
                        ${{(row.plan_pass_rate * 100).toFixed(1)}}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-700">
                        ${{(row.apply_pass_rate * 100).toFixed(1)}}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-700">
                        ${{(row.validation_pass_rate * 100).toFixed(1)}}%
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-600">
                        ${{row.avg_time.toFixed(1)}}s
                    </td>
                    <td class="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-600">
                        ${{passedRatio}}
                    </td>
                `;

                tbody.appendChild(tr);
            }});
        }}

        // Sort functionality
        function sortData(key, ascending) {{
            filteredData.sort((a, b) => {{
                let aVal = a[key];
                let bVal = b[key];

                if (typeof aVal === 'string') {{
                    return ascending ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }}

                return ascending ? aVal - bVal : bVal - aVal;
            }});

            currentSort = {{ key, ascending }};
            updateSortIndicators();
            renderTable();
        }}

        // Update sort indicators
        function updateSortIndicators() {{
            document.querySelectorAll('.sort-indicator').forEach(indicator => {{
                indicator.classList.remove('active');
                indicator.textContent = '↕';
            }});

            const activeTh = document.querySelector(`[data-sort="${{currentSort.key}}"]`);
            if (activeTh) {{
                const indicator = activeTh.querySelector('.sort-indicator');
                indicator.classList.add('active');
                indicator.textContent = currentSort.ascending ? '↑' : '↓';
            }}
        }}

        // Search functionality
        document.getElementById('searchInput').addEventListener('input', (e) => {{
            const query = e.target.value.toLowerCase();
            filteredData = data.filter(row =>
                row.model.toLowerCase().includes(query)
            );
            renderTable();
        }});

        // Attach sort listeners
        document.querySelectorAll('.sortable').forEach(th => {{
            th.addEventListener('click', () => {{
                const key = th.dataset.sort;
                const ascending = currentSort.key === key ? !currentSort.ascending : false;
                sortData(key, ascending);
            }});
        }});

        // Initial render
        renderTable();
    </script>
</body>
</html>
"""

    return html


def leaderboard_command(
    output_dir: str = typer.Argument(
        "output",
        help="Output directory containing benchmark results"
    ),
    dest: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Destination directory for leaderboard (default: leaderboards/YYYY-MM-DD--HH-MM)"
    ),
):
    """
    Generate HTML leaderboard from benchmark results.

    Scans the output directory for benchmark_results.json files from multiple models
    and generates a sortable, filterable leaderboard table.

    Examples:

        # Generate leaderboard from default output directory
        uv run python -m terraform_llm.cli leaderboard

        # Generate from custom output directory
        uv run python -m terraform_llm.cli leaderboard my_results/

        # Specify custom output location
        uv run python -m terraform_llm.cli leaderboard output/ -o my_leaderboard/
    """
    output_path = Path(output_dir)

    if not output_path.exists():
        console.print(f"[red]Error: Output directory not found: {output_dir}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Scanning {output_path} for benchmark results...[/cyan]")

    # Aggregate data
    data = aggregate_benchmark_results(output_path)

    if not data:
        console.print("[red]No benchmark results found. Run benchmarks first.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[green]Aggregated {len(data)} model(s)[/green]")

    # Generate HTML
    html = generate_html(data)

    # Determine output directory
    if dest:
        output_leaderboard_dir = Path(dest)
    else:
        timestamp = datetime.now().strftime("%Y-%m-%d--%H-%M")
        output_leaderboard_dir = Path("leaderboards") / timestamp

    output_leaderboard_dir.mkdir(parents=True, exist_ok=True)

    # Write HTML file
    html_path = output_leaderboard_dir / "index.html"
    html_path.write_text(html)

    console.print(f"[green]✓[/green] Leaderboard generated: {html_path}")
    console.print(f"[cyan]Open in browser: file://{html_path.absolute()}[/cyan]")
