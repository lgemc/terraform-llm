import type { InstanceResult } from '../types'

interface Props {
  instances: InstanceResult[]
  selectedId: string | null
  onSelect: (id: string) => void
}

function scoreBadge(score: number) {
  const pct = (score * 100).toFixed(0)
  if (score >= 0.8) return <span className="bg-green-900 text-green-300 text-xs px-2 py-0.5 rounded-full font-medium">{pct}%</span>
  if (score >= 0.5) return <span className="bg-yellow-900 text-yellow-300 text-xs px-2 py-0.5 rounded-full font-medium">{pct}%</span>
  return <span className="bg-red-900 text-red-300 text-xs px-2 py-0.5 rounded-full font-medium">{pct}%</span>
}

export function Sidebar({ instances, selectedId, onSelect }: Props) {
  const sorted = [...instances].sort((a, b) => b.total_score - a.total_score)

  return (
    <aside className="w-72 bg-gray-900 border-r border-gray-800 overflow-y-auto shrink-0">
      <div className="p-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">Instances ({instances.length})</h2>
      </div>
      <ul>
        {sorted.map(inst => (
          <li key={inst.instance_id}>
            <button
              onClick={() => onSelect(inst.instance_id)}
              className={`w-full text-left px-4 py-3 border-b border-gray-800/50 transition-colors hover:bg-gray-800 ${
                selectedId === inst.instance_id ? 'bg-gray-800 border-l-2 border-l-blue-500' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium truncate">{inst.instance_id}</span>
                {scoreBadge(inst.total_score)}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {inst.stages.filter(s => s.status === 'passed').length}/{inst.stages.length} stages passed
              </div>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}
