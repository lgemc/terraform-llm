import { useEffect, useState } from 'react'
import type { InstanceResult, BenchmarkResults, TrajectoryFile } from './types'
import { isATIFTrajectory, atifToTrajectory } from './types'
import { DataLoader } from './components/DataLoader'
import { AppSidebar } from './components/Sidebar'
import { InstanceDetail } from './components/InstanceDetail'
import { SummaryBar } from './components/SummaryBar'
import { ModelOverview } from './components/ModelOverview'
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar'

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
    iterations: traj.iterations,
    best_score: traj.best_score,
    num_iterations: traj.num_iterations,
  }
}

function trajectoriesToBenchmark(data: TrajectoryFile[]): BenchmarkResults {
  const instances = data.map(trajectoryToInstance)
  const scores = instances.map(i => i.total_score)
  const meanScore = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

  const stageNames = new Set<string>()
  instances.forEach(i => i.stages.forEach(s => stageNames.add(s.stage)))
  const stagePassRates: Record<string, number> = {}
  for (const name of stageNames) {
    const stages = instances.map(i => i.stages.find(s => s.stage === name)).filter(Boolean)
    const passed = stages.filter(s => s!.status === 'passed').length
    stagePassRates[name] = stages.length > 0 ? passed / stages.length : 0
  }

  return {
    model: instances[0]?.model || 'unknown',
    mean_score: meanScore,
    stage_pass_rates: stagePassRates,
    num_instances: instances.length,
    results: instances,
  }
}

function enrichBenchmarkWithTrajectories(benchData: BenchmarkResults, trajFiles: TrajectoryFile[]): BenchmarkResults {
  const trajMap = new Map<string, TrajectoryFile>()
  for (const traj of trajFiles) {
    trajMap.set(traj.instance_id, traj)
  }

  for (const result of benchData.results) {
    const traj = trajMap.get(result.instance_id)
    if (traj) {
      result.problem_statement = traj.info.problem_statement
      result.total_time_seconds = traj.info.total_time_seconds
      result.expected_resources = traj.info.expected_resources
      result.iterations = traj.iterations
      result.best_score = traj.best_score
      result.num_iterations = traj.num_iterations
      trajMap.delete(result.instance_id)
    }
  }

  for (const traj of trajMap.values()) {
    benchData.results.push({
      instance_id: traj.instance_id,
      model: traj.info.model,
      total_score: traj.info.total_score,
      stages: traj.stages,
      generated_files: traj.generated_files,
      error: null,
      problem_statement: traj.info.problem_statement,
      total_time_seconds: traj.info.total_time_seconds,
      expected_resources: traj.info.expected_resources,
      iterations: traj.iterations,
      best_score: traj.best_score,
      num_iterations: traj.num_iterations,
    })
  }

  benchData.num_instances = benchData.results.length
  const scores = benchData.results.map(r => r.total_score)
  benchData.mean_score = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0

  const stageNames = new Set<string>()
  benchData.results.forEach(r => r.stages.forEach(s => stageNames.add(s.stage)))
  benchData.stage_pass_rates = {}
  for (const name of stageNames) {
    const stages = benchData.results.map(r => r.stages.find(s => s.stage === name)).filter(Boolean)
    const passed = stages.filter(s => s!.status === 'passed').length
    benchData.stage_pass_rates[name] = stages.length > 0 ? passed / stages.length : 0
  }

  return benchData
}

async function loadFromOutputApi(): Promise<BenchmarkResults[] | null> {
  try {
    const res = await fetch('/api/output')
    if (!res.ok) return null
    const files: string[] = await res.json()
    if (files.length === 0) return null

    // Find model subfolders that have benchmark_results.json or .traj.json
    const benchmarkFiles = files.filter(f => f.endsWith('benchmark_results.json'))
    const trajFiles = files.filter(f => f.endsWith('.traj.json'))

    // Group by top-level folder
    const folderSet = new Set<string>()
    for (const f of [...benchmarkFiles, ...trajFiles]) {
      const parts = f.split('/')
      if (parts.length >= 2) {
        folderSet.add(parts[0])
      }
    }

    // If no subfolders, check root-level benchmark_results.json
    if (folderSet.size === 0) {
      const rootBench = benchmarkFiles.find(f => f === 'benchmark_results.json')
      if (rootBench) {
        const data = await (await fetch(`/api/output/${rootBench}`)).json() as BenchmarkResults
        if (data.results && Array.isArray(data.results)) {
          return [data]
        }
      }
      return null
    }

    const models: BenchmarkResults[] = []
    for (const folder of folderSet) {
      const folderBench = benchmarkFiles.find(f => f === `${folder}/benchmark_results.json`)
      const folderTrajs = trajFiles.filter(f => f.startsWith(`${folder}/`))

      if (folderBench) {
        const data = await (await fetch(`/api/output/${encodeURIComponent(folderBench)}`)).json() as BenchmarkResults
        if (data.results && Array.isArray(data.results)) {
          if (folderTrajs.length > 0) {
            const trajs: TrajectoryFile[] = []
            for (const tf of folderTrajs) {
              const parsed = await (await fetch(`/api/output/${encodeURIComponent(tf)}`)).json()
              trajs.push(isATIFTrajectory(parsed) ? atifToTrajectory(parsed) : parsed as TrajectoryFile)
            }
            enrichBenchmarkWithTrajectories(data, trajs)
          }
          models.push(data)
        }
      } else if (folderTrajs.length > 0) {
        const trajs: TrajectoryFile[] = []
        for (const tf of folderTrajs) {
          const parsed = await (await fetch(`/api/output/${encodeURIComponent(tf)}`)).json()
          trajs.push(isATIFTrajectory(parsed) ? atifToTrajectory(parsed) : parsed as TrajectoryFile)
        }
        models.push(trajectoriesToBenchmark(trajs))
      }
    }

    return models.length > 0 ? models : null
  } catch {
    return null
  }
}

type LoadState = 'loading' | 'loaded' | 'no-output'

export default function App() {
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [allModels, setAllModels] = useState<BenchmarkResults[] | null>(null)
  const [selectedModel, setSelectedModel] = useState<BenchmarkResults | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Try to auto-load from ../output on startup
  useEffect(() => {
    loadFromOutputApi().then(models => {
      if (models && models.length > 0) {
        setAllModels(models)
        if (models.length === 1) {
          setSelectedModel(models[0])
          if (models[0].results.length > 0) {
            setSelectedId(models[0].results[0].instance_id)
          }
        }
        setLoadState('loaded')
      } else {
        setLoadState('no-output')
      }
    })
  }, [])

  const handleDataLoaded = (data: BenchmarkResults[] | BenchmarkResults | TrajectoryFile[]) => {
    if (Array.isArray(data) && data.length > 0 && 'results' in data[0]) {
      const models = data as BenchmarkResults[]
      setAllModels(models)
      if (models.length === 1) {
        setSelectedModel(models[0])
        if (models[0].results.length > 0) {
          setSelectedId(models[0].results[0].instance_id)
        }
      }
    } else if (Array.isArray(data)) {
      const benchmark = trajectoriesToBenchmark(data as TrajectoryFile[])
      setAllModels([benchmark])
      setSelectedModel(benchmark)
      if (benchmark.results.length > 0) {
        setSelectedId(benchmark.results[0].instance_id)
      }
    } else {
      setAllModels([data])
      setSelectedModel(data)
      if (data.results.length > 0) {
        setSelectedId(data.results[0].instance_id)
      }
    }
    setLoadState('loaded')
  }

  const handleSelectModel = (model: BenchmarkResults) => {
    setSelectedModel(model)
    if (model.results.length > 0) {
      const sorted = [...model.results].sort((a, b) => b.total_score - a.total_score)
      setSelectedId(sorted[0].instance_id)
    } else {
      setSelectedId(null)
    }
  }

  const handleBackToOverview = () => {
    setSelectedModel(null)
    setSelectedId(null)
  }

  // Loading from API
  if (loadState === 'loading') {
    return (
      <div className="h-screen flex items-center justify-center">
        <p className="text-muted-foreground">Loading results from output folder...</p>
      </div>
    )
  }

  // No output folder found — show file picker
  if (loadState === 'no-output' && !allModels) {
    return <DataLoader onDataLoaded={handleDataLoaded} />
  }

  // Multi-model overview
  if (allModels && allModels.length > 1 && !selectedModel) {
    return <ModelOverview models={allModels} onSelectModel={handleSelectModel} />
  }

  // Single model detail view
  const results = selectedModel || allModels![0]
  const selectedInstance = results.results.find(r => r.instance_id === selectedId) || null

  return (
    <SidebarProvider defaultOpen={true}>
      <div className="flex flex-col h-screen w-full">
        <SummaryBar
          results={results}
          showBack={allModels!.length > 1}
          onBack={handleBackToOverview}
        />
        <div className="flex flex-1 overflow-hidden">
          <AppSidebar
            instances={results.results}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <SidebarInset className="overflow-hidden">
            {selectedInstance ? (
              <InstanceDetail instance={selectedInstance} />
            ) : (
              <div className="text-muted-foreground text-center mt-20">Select an instance from the sidebar</div>
            )}
          </SidebarInset>
        </div>
      </div>
    </SidebarProvider>
  )
}
