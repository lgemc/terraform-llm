import { useCallback, useState } from 'react'
import type { BenchmarkResults, TrajectoryFile } from '../types'
import { isATIFTrajectory, atifToTrajectory } from '../types'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { FolderOpen, FileJson, Files } from 'lucide-react'

interface Props {
  onDataLoaded: (data: BenchmarkResults | TrajectoryFile[]) => void
}

export function DataLoader({ onDataLoaded }: Props) {
  const [error, setError] = useState<string | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const processFiles = useCallback(async (files: FileList | File[]) => {
    setError(null)
    const fileArray = Array.from(files)

    // Collect .traj.json files
    const trajFiles = fileArray.filter(f => f.name.endsWith('.traj.json'))

    // Check for benchmark_results.json
    const benchmarkFile = fileArray.find(f => f.name === 'benchmark_results.json')

    if (benchmarkFile && trajFiles.length > 0) {
      // Both benchmark_results.json and .traj.json files — merge them
      try {
        const benchText = await benchmarkFile.text()
        const benchData = JSON.parse(benchText) as BenchmarkResults

        const trajMap = new Map<string, TrajectoryFile>()
        for (const file of trajFiles) {
          const text = await file.text()
          const parsed = JSON.parse(text)
          const traj = isATIFTrajectory(parsed) ? atifToTrajectory(parsed) : parsed as TrajectoryFile
          trajMap.set(traj.instance_id, traj)
        }

        // Enrich benchmark results with trajectory data
        for (const result of benchData.results) {
          const traj = trajMap.get(result.instance_id)
          if (traj) {
            result.problem_statement = traj.info.problem_statement
            result.total_time_seconds = traj.info.total_time_seconds
            result.expected_resources = traj.info.expected_resources
            trajMap.delete(result.instance_id)
          }
        }

        // Add any trajectory instances not in benchmark_results
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
          })
        }

        // Recalculate summary stats
        benchData.num_instances = benchData.results.length
        const scores = benchData.results.map(r => r.total_score)
        benchData.mean_score = scores.reduce((a, b) => a + b, 0) / scores.length

        const stageNames = new Set<string>()
        benchData.results.forEach(r => r.stages.forEach(s => stageNames.add(s.stage)))
        benchData.stage_pass_rates = {}
        for (const name of stageNames) {
          const stages = benchData.results.map(r => r.stages.find(s => s.stage === name)).filter(Boolean)
          const passed = stages.filter(s => s!.status === 'passed').length
          benchData.stage_pass_rates[name] = stages.length > 0 ? passed / stages.length : 0
        }

        onDataLoaded(benchData)
        return
      } catch {
        setError('Failed to parse files')
        return
      }
    }

    if (benchmarkFile) {
      try {
        const text = await benchmarkFile.text()
        const data = JSON.parse(text) as BenchmarkResults
        if (data.results && Array.isArray(data.results)) {
          onDataLoaded(data)
          return
        }
      } catch {
        setError('Failed to parse benchmark_results.json')
        return
      }
    }

    if (trajFiles.length > 0) {
      try {
        const trajectories: TrajectoryFile[] = []
        for (const file of trajFiles) {
          const text = await file.text()
          const parsed = JSON.parse(text)
          trajectories.push(isATIFTrajectory(parsed) ? atifToTrajectory(parsed) : parsed as TrajectoryFile)
        }
        onDataLoaded(trajectories)
        return
      } catch {
        setError('Failed to parse .traj.json files')
        return
      }
    }

    setError('No benchmark_results.json or .traj.json files found. Please select the output folder or individual result files.')
  }, [onDataLoaded])

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFiles(e.target.files)
    }
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files)
    }
  }

  return (
    <div className="h-screen flex items-center justify-center p-8">
      <Card
        className={`max-w-lg w-full border-2 border-dashed p-8 text-center transition-colors ${
          isDragging ? 'border-primary bg-primary/5' : ''
        }`}
        onDragOver={(e) => { e.preventDefault(); setIsDragging(true) }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <CardHeader className="pb-4">
          <div className="text-4xl mb-2">📂</div>
          <CardTitle className="text-xl">Load Benchmark Results</CardTitle>
          <CardDescription>
            Select the <code className="text-primary">output/</code> folder to load all results,
            or pick individual files.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col gap-3 items-center">
            <Button asChild className="w-64">
              <label className="cursor-pointer">
                <FolderOpen className="h-4 w-4" />
                Select Output Folder
                {/* @ts-expect-error webkitdirectory is non-standard */}
                <input type="file" webkitdirectory="" className="hidden" onChange={handleFileInput} />
              </label>
            </Button>
            <Button asChild variant="secondary" className="w-64">
              <label className="cursor-pointer">
                <FileJson className="h-4 w-4" />
                Select benchmark_results.json
                <input type="file" accept=".json" className="hidden" onChange={handleFileInput} />
              </label>
            </Button>
            <Button asChild variant="secondary" className="w-64">
              <label className="cursor-pointer">
                <Files className="h-4 w-4" />
                Select .traj.json files
                <input type="file" accept=".json" multiple className="hidden" onChange={handleFileInput} />
              </label>
            </Button>
          </div>
          {error && (
            <p className="mt-4 text-destructive text-sm">{error}</p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
