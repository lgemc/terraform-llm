import type { BenchmarkResults } from '../types'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

interface Props {
  results: BenchmarkResults
}

function scoreColor(score: number) {
  if (score >= 0.8) return 'bg-green-600 text-white hover:bg-green-600'
  if (score >= 0.5) return 'bg-yellow-600 text-white hover:bg-yellow-600'
  return 'bg-red-600 text-white hover:bg-red-600'
}

function rateColor(rate: number) {
  if (rate >= 0.8) return 'border-green-700 text-green-400'
  if (rate >= 0.5) return 'border-yellow-700 text-yellow-400'
  return 'border-red-700 text-red-400'
}

export function SummaryBar({ results }: Props) {
  return (
    <header className="border-b bg-card px-6 py-3 flex items-center gap-6 shrink-0">
      <h1 className="font-bold text-lg">Terraform LLM Benchmark</h1>
      <Separator orientation="vertical" className="h-6" />
      <div className="flex items-center gap-4 text-sm flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Model:</span>
          <span className="font-medium">{results.model}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Mean Score:</span>
          <Badge className={scoreColor(results.mean_score)}>
            {(results.mean_score * 100).toFixed(1)}%
          </Badge>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-muted-foreground">Instances:</span>
          <span className="font-medium">{results.num_instances}</span>
        </div>
        <Separator orientation="vertical" className="h-4" />
        {Object.entries(results.stage_pass_rates).map(([stage, rate]) => (
          <div key={stage} className="flex items-center gap-1.5">
            <span className="text-muted-foreground">{stage}:</span>
            <Badge variant="outline" className={rateColor(rate)}>
              {(rate * 100).toFixed(0)}%
            </Badge>
          </div>
        ))}
      </div>
    </header>
  )
}
