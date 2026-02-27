import { useState } from 'react'
import type { Stage } from '../types'

interface Props {
  stages: Stage[]
}

const statusConfig = {
  passed: { bg: 'bg-green-900/50', border: 'border-green-700', text: 'text-green-400', icon: '✓' },
  failed: { bg: 'bg-red-900/50', border: 'border-red-700', text: 'text-red-400', icon: '✗' },
  skipped: { bg: 'bg-gray-800/50', border: 'border-gray-700', text: 'text-gray-500', icon: '–' },
}

function stripAnsi(str: string): string {
  return str.replace(/\x1b\[[0-9;]*m/g, '')
}

function StageCard({ stage }: { stage: Stage }) {
  const [expanded, setExpanded] = useState(false)
  const config = statusConfig[stage.status]
  const hasOutput = stage.output && stage.output.trim().length > 0

  return (
    <div className={`${config.bg} border ${config.border} rounded-lg p-4`}>
      <button
        className="w-full text-left"
        onClick={() => hasOutput && setExpanded(!expanded)}
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={`${config.text} font-bold text-lg`}>{config.icon}</span>
            <div>
              <div className="font-medium text-sm">{stage.stage}</div>
              <div className="text-xs text-gray-400 mt-0.5">{stage.message}</div>
            </div>
          </div>
          <div className="flex items-center gap-3 text-right">
            {stage.duration_seconds > 0 && (
              <span className="text-xs text-gray-400">{stage.duration_seconds.toFixed(1)}s</span>
            )}
            <span className={`text-sm font-bold ${config.text}`}>
              {(stage.score * 100).toFixed(0)}%
            </span>
            {hasOutput && (
              <span className="text-gray-500 text-xs">{expanded ? '▲' : '▼'}</span>
            )}
          </div>
        </div>
      </button>
      {expanded && hasOutput && (
        <pre className="mt-3 text-xs text-gray-300 bg-gray-950 rounded p-3 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap break-words">
          {stripAnsi(stage.output!)}
        </pre>
      )}
    </div>
  )
}

export function StageTimeline({ stages }: Props) {
  return (
    <div className="space-y-2">
      {stages.map((stage, i) => (
        <div key={i} className="flex items-stretch gap-2">
          {/* Connector line */}
          <div className="flex flex-col items-center w-4 shrink-0">
            <div className={`w-0.5 flex-1 ${i === 0 ? 'bg-transparent' : 'bg-gray-700'}`} />
            <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${
              stage.status === 'passed' ? 'bg-green-500' :
              stage.status === 'failed' ? 'bg-red-500' : 'bg-gray-600'
            }`} />
            <div className={`w-0.5 flex-1 ${i === stages.length - 1 ? 'bg-transparent' : 'bg-gray-700'}`} />
          </div>
          <div className="flex-1 py-1">
            <StageCard stage={stage} />
          </div>
        </div>
      ))}
    </div>
  )
}
