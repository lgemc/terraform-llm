import type { BenchmarkResults } from '../types'

interface Props {
  results: BenchmarkResults
}

export function SummaryBar({ results }: Props) {
  const scoreColor = results.mean_score >= 0.8 ? 'text-green-400' : results.mean_score >= 0.5 ? 'text-yellow-400' : 'text-red-400'

  return (
    <header className="bg-gray-900 border-b border-gray-800 px-6 py-3 flex items-center gap-8 shrink-0">
      <h1 className="font-bold text-lg">Terraform LLM Benchmark</h1>
      <div className="flex items-center gap-6 text-sm">
        <div>
          <span className="text-gray-400">Model: </span>
          <span className="font-medium">{results.model}</span>
        </div>
        <div>
          <span className="text-gray-400">Mean Score: </span>
          <span className={`font-bold ${scoreColor}`}>{(results.mean_score * 100).toFixed(1)}%</span>
        </div>
        <div>
          <span className="text-gray-400">Instances: </span>
          <span className="font-medium">{results.num_instances}</span>
        </div>
        {Object.entries(results.stage_pass_rates).map(([stage, rate]) => (
          <div key={stage}>
            <span className="text-gray-400">{stage}: </span>
            <span className={`font-medium ${rate >= 0.8 ? 'text-green-400' : rate >= 0.5 ? 'text-yellow-400' : 'text-red-400'}`}>
              {(rate * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </header>
  )
}
