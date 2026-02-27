import { useState } from 'react'
import type { InstanceResult, BenchmarkResults, TrajectoryFile } from './types'
import { DataLoader } from './components/DataLoader'
import { Sidebar } from './components/Sidebar'
import { InstanceDetail } from './components/InstanceDetail'
import { SummaryBar } from './components/SummaryBar'

function trajectoryToInstance(traj: TrajectoryFile): InstanceResult {
  return {
    instance_id: traj.instance_id,
    model: traj.info.model,
    total_score: traj.info.total_score,
    stages: traj.stages,
    generated_files: traj.generated_files,
    error: null,
    problem_statement: traj.info.problem_statement,
    total_time_seconds: traj.info.total_time_seconds,
    expected_resources: traj.info.expected_resources,
  }
}

export default function App() {
  const [results, setResults] = useState<BenchmarkResults | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const handleDataLoaded = (data: BenchmarkResults | TrajectoryFile[]) => {
    let benchmark: BenchmarkResults

    if (Array.isArray(data)) {
      // Array of trajectory files
      const instances = data.map(trajectoryToInstance)
      const scores = instances.map(i => i.total_score)
      const meanScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

      // Calculate stage pass rates
      const stageNames = new Set<string>()
      instances.forEach(i => i.stages.forEach(s => stageNames.add(s.stage)))
      const stagePassRates: Record<string, number> = {}
      for (const name of stageNames) {
        const stages = instances.map(i => i.stages.find(s => s.stage === name)).filter(Boolean)
        const passed = stages.filter(s => s!.status === 'passed').length
        stagePassRates[name] = stages.length > 0 ? passed / stages.length : 0
      }

      benchmark = {
        model: instances[0]?.model || 'unknown',
        mean_score: meanScore,
        stage_pass_rates: stagePassRates,
        num_instances: instances.length,
        results: instances,
      }
    } else {
      benchmark = data
    }

    setResults(benchmark)
    if (benchmark.results.length > 0) {
      setSelectedId(benchmark.results[0].instance_id)
    }
  }

  if (!results) {
    return <DataLoader onDataLoaded={handleDataLoaded} />
  }

  const selectedInstance = results.results.find(r => r.instance_id === selectedId) || null

  return (
    <div className="h-screen flex flex-col">
      <SummaryBar results={results} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          instances={results.results}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <main className="flex-1 overflow-y-auto p-6">
          {selectedInstance ? (
            <InstanceDetail instance={selectedInstance} />
          ) : (
            <div className="text-gray-500 text-center mt-20">Select an instance from the sidebar</div>
          )}
        </main>
      </div>
    </div>
  )
}
