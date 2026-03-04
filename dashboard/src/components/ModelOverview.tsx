import type { BenchmarkResults } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

interface Props {
  models: BenchmarkResults[]
  onSelectModel: (model: BenchmarkResults) => void
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

function scoreBorderTopColor(score: number) {
  if (score >= 0.8) return 'border-t-green-500'
  if (score >= 0.5) return 'border-t-yellow-500'
  return 'border-t-red-500'
}

const STAGE_ORDER = ['init', 'validate', 'plan', 'apply', 'validation_script']

export function ModelOverview({ models, onSelectModel }: Props) {
  const sorted = [...models].sort((a, b) => b.mean_score - a.mean_score)

  return (
    <div className="h-screen flex flex-col">
      <header className="border-b bg-card px-6 py-4 shrink-0">
        <h1 className="font-bold text-xl">Terraform LLM Benchmark</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {sorted.length} models evaluated — sorted by mean score
        </p>
      </header>
      <div className="flex-1 overflow-auto p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-7xl mx-auto">
          {sorted.map((model, idx) => (
            <Card
              key={model.model}
              className={`cursor-pointer transition-colors hover:bg-accent/50 border-t-4 ${scoreBorderTopColor(model.mean_score)}`}
              onClick={() => onSelectModel(model)}
            >
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground text-xs font-mono">#{idx + 1}</span>
                  <Badge className={`text-base px-3 py-1 ${scoreColor(model.mean_score)}`}>
                    {(model.mean_score * 100).toFixed(1)}%
                  </Badge>
                </div>
                <CardTitle className="text-base truncate" title={model.model}>
                  {model.model}
                </CardTitle>
                <p className="text-xs text-muted-foreground">{model.num_instances} instances</p>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm">
                  {STAGE_ORDER
                    .filter(stage => stage in model.stage_pass_rates)
                    .map(stage => (
                      <div key={stage} className="flex items-center justify-between">
                        <span className="text-muted-foreground text-xs">{stage}</span>
                        <Badge variant="outline" className={`text-xs ${rateColor(model.stage_pass_rates[stage])}`}>
                          {(model.stage_pass_rates[stage] * 100).toFixed(0)}%
                        </Badge>
                      </div>
                    ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  )
}
