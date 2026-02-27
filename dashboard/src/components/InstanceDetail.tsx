import type { InstanceResult } from '../types'
import { StageTimeline } from './StageTimeline'
import { CodeViewer } from './CodeViewer'

interface Props {
  instance: InstanceResult
}

export function InstanceDetail({ instance }: Props) {
  const totalTime = instance.total_time_seconds
    ?? instance.stages.reduce((sum, s) => sum + s.duration_seconds, 0)

  const scoreColor = instance.total_score >= 0.8 ? 'text-green-400' : instance.total_score >= 0.5 ? 'text-yellow-400' : 'text-red-400'

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold">{instance.instance_id}</h2>
        <div className="flex items-center gap-4 mt-2 text-sm text-gray-400">
          <span>Score: <span className={`font-bold text-lg ${scoreColor}`}>{(instance.total_score * 100).toFixed(1)}%</span></span>
          <span>Time: {totalTime.toFixed(1)}s</span>
          <span>Model: {instance.model}</span>
        </div>
      </div>

      {/* Problem Statement */}
      {instance.problem_statement && (
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Problem Statement</h3>
          <p className="text-gray-200 text-sm leading-relaxed">{instance.problem_statement}</p>
        </div>
      )}

      {/* Expected Resources */}
      {instance.expected_resources && Object.keys(instance.expected_resources).length > 0 && (
        <div className="bg-gray-900 rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-2">Expected Resources</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(instance.expected_resources).map(([resource, count]) => (
              <span key={resource} className="bg-gray-800 text-gray-300 text-xs px-2.5 py-1 rounded font-mono">
                {resource} x{count as number}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Stage Timeline */}
      <div>
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Pipeline Stages</h3>
        <StageTimeline stages={instance.stages} />
      </div>

      {/* Error */}
      {instance.error && (
        <div className="bg-red-950 border border-red-800 rounded-lg p-4">
          <h3 className="text-sm font-semibold text-red-400 mb-2">Error</h3>
          <pre className="text-red-300 text-xs whitespace-pre-wrap">{instance.error}</pre>
        </div>
      )}

      {/* Generated Code */}
      {Object.keys(instance.generated_files).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide mb-3">Generated Terraform Code</h3>
          {Object.entries(instance.generated_files).map(([filename, content]) => (
            <CodeViewer key={filename} filename={filename} code={content} />
          ))}
        </div>
      )}
    </div>
  )
}
