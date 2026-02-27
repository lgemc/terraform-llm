import { useState } from 'react'

interface Props {
  filename: string
  code: string
}

export function CodeViewer({ filename, code }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const lineCount = code.split('\n').length

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden mb-3">
      <button
        className="w-full flex items-center justify-between px-4 py-2.5 bg-gray-800/50 hover:bg-gray-800 transition-colors text-left"
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="font-mono text-sm text-blue-400">{filename}</span>
        <span className="text-xs text-gray-500">{lineCount} lines {collapsed ? '▼' : '▲'}</span>
      </button>
      {!collapsed && (
        <div className="overflow-x-auto">
          <pre className="p-4 text-sm leading-relaxed">
            <code>{code.split('\n').map((line, i) => (
              <div key={i} className="flex">
                <span className="text-gray-600 select-none w-10 text-right pr-4 shrink-0">{i + 1}</span>
                <span className="text-gray-200">{line}</span>
              </div>
            ))}</code>
          </pre>
        </div>
      )}
    </div>
  )
}
