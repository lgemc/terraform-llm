import { useState } from 'react'
import type { Stage } from '../types'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { CheckCircle2, XCircle, MinusCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { cn } from '@/lib/utils'

interface Props {
  stages: Stage[]
}

const statusConfig = {
  passed: {
    icon: CheckCircle2,
    dotColor: 'bg-green-500',
    badgeClass: 'bg-green-900 text-green-300 hover:bg-green-900',
    textColor: 'text-green-400',
  },
  failed: {
    icon: XCircle,
    dotColor: 'bg-red-500',
    badgeClass: 'bg-red-900 text-red-300 hover:bg-red-900',
    textColor: 'text-red-400',
  },
  skipped: {
    icon: MinusCircle,
    dotColor: 'bg-muted-foreground',
    badgeClass: 'bg-muted text-muted-foreground hover:bg-muted',
    textColor: 'text-muted-foreground',
  },
}

function stripAnsi(str: string): string {
  return str.replace(/\x1b\[[0-9;]*m/g, '')
}

function StageCard({ stage }: { stage: Stage }) {
  const [open, setOpen] = useState(false)
  const config = statusConfig[stage.status]
  const Icon = config.icon
  const hasOutput = stage.output && stage.output.trim().length > 0

  return (
    <Card className={cn(
      'border',
      stage.status === 'passed' && 'border-green-800/50 bg-green-950/20',
      stage.status === 'failed' && 'border-red-800/50 bg-red-950/20',
      stage.status === 'skipped' && 'border-border bg-muted/20',
    )}>
      <Collapsible open={open} onOpenChange={setOpen}>
        <CollapsibleTrigger asChild disabled={!hasOutput}>
          <button className="w-full text-left p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Icon className={cn('h-5 w-5', config.textColor)} />
                <div>
                  <div className="font-medium text-sm">{stage.stage}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{stage.message}</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {stage.duration_seconds > 0 && (
                  <span className="text-xs text-muted-foreground">{stage.duration_seconds.toFixed(1)}s</span>
                )}
                <Badge className={config.badgeClass}>
                  {(stage.score * 100).toFixed(0)}%
                </Badge>
                {hasOutput && (
                  open ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
            </div>
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          {hasOutput && (
            <CardContent className="pt-0 px-4 pb-4">
              <pre className="text-xs text-muted-foreground bg-background rounded-md p-3 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap break-words border">
                {stripAnsi(stage.output!)}
              </pre>
            </CardContent>
          )}
        </CollapsibleContent>
      </Collapsible>
    </Card>
  )
}

export function StageTimeline({ stages }: Props) {
  return (
    <div className="space-y-2">
      {stages.map((stage, i) => (
        <div key={i} className="flex items-stretch gap-2">
          {/* Connector line */}
          <div className="flex flex-col items-center w-4 shrink-0">
            <div className={cn('w-0.5 flex-1', i === 0 ? 'bg-transparent' : 'bg-border')} />
            <div className={cn('w-2.5 h-2.5 rounded-full shrink-0', statusConfig[stage.status].dotColor)} />
            <div className={cn('w-0.5 flex-1', i === stages.length - 1 ? 'bg-transparent' : 'bg-border')} />
          </div>
          <div className="flex-1 py-1">
            <StageCard stage={stage} />
          </div>
        </div>
      ))}
    </div>
  )
}
