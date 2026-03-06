import type { InstanceResult } from '../types'
import { StageTimeline } from './StageTimeline'
import { CodeViewer } from './CodeViewer'
import { IterationTimeline } from './IterationTimeline'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Clock, Cpu, AlertTriangle, RotateCw } from 'lucide-react'

interface Props {
  instance: InstanceResult
}

function scoreColor(score: number) {
  if (score >= 0.8) return 'bg-green-600 text-white hover:bg-green-600'
  if (score >= 0.5) return 'bg-yellow-600 text-white hover:bg-yellow-600'
  return 'bg-red-600 text-white hover:bg-red-600'
}

export function InstanceDetail({ instance }: Props) {
  const totalTime = instance.total_time_seconds
    ?? instance.stages.reduce((sum, s) => sum + s.duration_seconds, 0)

  return (
    <ScrollArea className="h-full">
      <div className="max-w-4xl space-y-6 p-6">
        {/* Header */}
        <div>
          <h2 className="text-2xl font-bold">{instance.instance_id}</h2>
          <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
            <div className="flex items-center gap-1.5">
              Score: <Badge className={scoreColor(instance.total_score)}>
                {(instance.total_score * 100).toFixed(1)}%
              </Badge>
              {instance.best_score !== undefined && instance.best_score !== instance.total_score && (
                <span className="text-xs text-muted-foreground">
                  (best: {(instance.best_score * 100).toFixed(1)}%)
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {totalTime.toFixed(1)}s
            </div>
            <div className="flex items-center gap-1">
              <Cpu className="h-3.5 w-3.5" />
              {instance.model}
            </div>
            {instance.num_iterations && instance.num_iterations > 1 && (
              <div className="flex items-center gap-1">
                <RotateCw className="h-3.5 w-3.5" />
                {instance.num_iterations} iterations
              </div>
            )}
          </div>
        </div>

        {/* Problem Statement */}
        {instance.problem_statement && (
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Problem Statement
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <p className="text-sm leading-relaxed">{instance.problem_statement}</p>
            </CardContent>
          </Card>
        )}

        {/* Expected Resources */}
        {instance.expected_resources && Object.keys(instance.expected_resources).length > 0 && (
          <Card>
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
                Expected Resources
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <div className="flex flex-wrap gap-2">
                {Object.entries(instance.expected_resources).map(([resource, count]) => (
                  <Badge key={resource} variant="secondary" className="font-mono">
                    {resource} x{count as number}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Iteration Timeline (Multi-turn) */}
        {instance.iterations && instance.iterations.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Multi-turn Refinement ({instance.iterations.length} iteration{instance.iterations.length > 1 ? 's' : ''})
            </h3>
            <IterationTimeline iterations={instance.iterations} />
          </div>
        )}

        {/* Stage Timeline */}
        <div>
          <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
            Pipeline Stages {instance.iterations && instance.iterations.length > 0 ? '(All Iterations)' : ''}
          </h3>
          <StageTimeline stages={instance.stages} />
        </div>

        {/* Error */}
        {instance.error && (
          <Card className="border-red-800 bg-red-950/30">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-semibold text-red-400 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                Error
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4">
              <pre className="text-red-300 text-xs whitespace-pre-wrap">{instance.error}</pre>
            </CardContent>
          </Card>
        )}

        {/* Generated Code */}
        {Object.keys(instance.generated_files).length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
              Generated Terraform Code
            </h3>
            {Object.entries(instance.generated_files).map(([filename, content]) => (
              <CodeViewer key={filename} filename={filename} code={content} />
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  )
}
