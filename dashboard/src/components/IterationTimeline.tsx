import type { Iteration } from '../types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ChevronDown, ChevronRight, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { useState } from 'react'

interface Props {
  iterations: Iteration[]
}

function scoreColor(score: number) {
  if (score >= 0.8) return 'text-green-600'
  if (score >= 0.5) return 'text-yellow-600'
  return 'text-red-600'
}

function scoreBadgeColor(score: number) {
  if (score >= 0.8) return 'bg-green-600 text-white hover:bg-green-600'
  if (score >= 0.5) return 'bg-yellow-600 text-white hover:bg-yellow-600'
  return 'bg-red-600 text-white hover:bg-red-600'
}

export function IterationTimeline({ iterations }: Props) {
  const [openIterations, setOpenIterations] = useState<Set<number>>(new Set([iterations.length]))

  const toggleIteration = (iterNum: number) => {
    const newOpen = new Set(openIterations)
    if (newOpen.has(iterNum)) {
      newOpen.delete(iterNum)
    } else {
      newOpen.add(iterNum)
    }
    setOpenIterations(newOpen)
  }

  return (
    <div className="space-y-3">
      {iterations.map((iter, idx) => {
        const isOpen = openIterations.has(iter.iteration_number)
        const prevScore = idx > 0 ? iterations[idx - 1].score : null
        const scoreDiff = prevScore !== null ? iter.score - prevScore : null

        return (
          <Collapsible key={iter.iteration_number} open={isOpen} onOpenChange={() => toggleIteration(iter.iteration_number)}>
            <Card>
              <CollapsibleTrigger className="w-full">
                <CardHeader className="pb-3 pt-4 px-4 cursor-pointer hover:bg-muted/50 transition-colors">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      {isOpen ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                      <CardTitle className="text-sm font-semibold">
                        Iteration {iter.iteration_number}
                      </CardTitle>
                      <Badge className={scoreBadgeColor(iter.score)}>
                        {(iter.score * 100).toFixed(0)}%
                      </Badge>
                      {scoreDiff !== null && (
                        <div className={`flex items-center gap-1 text-xs ${scoreDiff > 0 ? 'text-green-600' : scoreDiff < 0 ? 'text-red-600' : 'text-gray-500'}`}>
                          {scoreDiff > 0 ? <TrendingUp className="h-3 w-3" /> : scoreDiff < 0 ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                          {scoreDiff > 0 ? '+' : ''}{(scoreDiff * 100).toFixed(0)}%
                        </div>
                      )}
                    </div>
                  </div>
                </CardHeader>
              </CollapsibleTrigger>

              <CollapsibleContent>
                <CardContent className="px-4 pb-4">
                  {/* Feedback from previous iteration */}
                  {iter.feedback && (
                    <div className="mb-3 p-3 bg-yellow-50 dark:bg-yellow-950/20 border border-yellow-200 dark:border-yellow-800 rounded-md">
                      <p className="text-xs font-semibold text-yellow-800 dark:text-yellow-400 mb-1">Refinement Feedback:</p>
                      <p className="text-xs text-yellow-700 dark:text-yellow-300 whitespace-pre-wrap">{iter.feedback}</p>
                    </div>
                  )}

                  {/* Stages */}
                  <div className="space-y-2">
                    {iter.stages.map((stage, stageIdx) => {
                      const statusColor = stage.status === 'passed' ? 'bg-green-100 dark:bg-green-950 text-green-800 dark:text-green-300' :
                                         stage.status === 'failed' ? 'bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300' :
                                         'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400'

                      return (
                        <div key={stageIdx} className="flex items-center gap-2 text-xs">
                          <Badge variant="outline" className={statusColor}>
                            {stage.stage}
                          </Badge>
                          <span className="text-muted-foreground">{stage.message}</span>
                          <span className={`ml-auto font-mono ${scoreColor(stage.score)}`}>
                            {(stage.score * 100).toFixed(0)}%
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </CardContent>
              </CollapsibleContent>
            </Card>
          </Collapsible>
        )
      })}
    </div>
  )
}
