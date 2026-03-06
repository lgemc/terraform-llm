export interface Stage {
  stage: string;
  status: "passed" | "failed" | "skipped";
  score: number;
  message: string;
  duration_seconds: number;
  details: Record<string, unknown>;
  output?: string;
  iteration?: number;  // Multi-turn iteration number
}

export interface Iteration {
  iteration_number: number;
  generated_files: Record<string, string>;
  stages: Stage[];
  score: number;
  feedback?: string;
}

export interface InstanceResult {
  instance_id: string;
  model: string;
  total_score: number;
  stages: Stage[];
  generated_files: Record<string, string>;
  error: string | null;
  problem_statement?: string;
  total_time_seconds?: number;
  expected_resources?: Record<string, number>;
  iterations?: Iteration[];  // Multi-turn iterations
  best_score?: number;
  num_iterations?: number;
}

export interface BenchmarkResults {
  model: string;
  mean_score: number;
  stage_pass_rates: Record<string, number>;
  num_instances: number;
  results: InstanceResult[];
}

export interface TrajectoryFile {
  trajectory_format: string;
  instance_id: string;
  info: {
    problem_statement: string;
    region: string;
    expected_resources: Record<string, number>;
    model: string;
    total_score: number;
    total_time_seconds: number;
  };
  generated_files: Record<string, string>;
  stages: Stage[];
  iterations?: Iteration[];
  best_score?: number;
  num_iterations?: number;
}

// ATIF (Agent Trajectory Interchange Format) types

export interface ATIFStep {
  step_id: number;
  timestamp?: string;
  source: "user" | "agent" | "system";
  message: string;
  reasoning_content?: string;
  model_name?: string;
  observation?: {
    results: Array<{ content?: string; source_call_id?: string }>;
  };
  extra?: Record<string, unknown>;
}

export interface ATIFTrajectory {
  schema_version: string;
  session_id: string;
  agent: {
    name: string;
    version: string;
    model_name: string;
    extra?: Record<string, unknown>;
  };
  steps: ATIFStep[];
  final_metrics?: {
    total_prompt_tokens?: number;
    total_completion_tokens?: number;
    total_cached_tokens?: number;
    total_cost_usd?: number;
    total_steps?: number;
    extra?: Record<string, unknown>;
  };
  extra?: Record<string, unknown>;
}

export function isATIFTrajectory(data: unknown): data is ATIFTrajectory {
  return (
    typeof data === 'object' &&
    data !== null &&
    'schema_version' in data &&
    typeof (data as ATIFTrajectory).schema_version === 'string' &&
    (data as ATIFTrajectory).schema_version.startsWith('ATIF')
  );
}

export function atifToTrajectory(atif: ATIFTrajectory): TrajectoryFile {
  // Extract stages from system steps that have extra.stage
  const stages: Stage[] = atif.steps
    .filter(s => s.source === 'system' && s.extra?.stage)
    .map(s => ({
      stage: s.extra!.stage as string,
      status: s.extra!.status as Stage['status'],
      score: (s.extra!.score as number) ?? 0,
      message: (s.extra!.message as string) ?? s.message,
      duration_seconds: (s.extra!.duration_seconds as number) ?? 0,
      details: (s.extra!.details as Record<string, unknown>) ?? {},
      output: s.observation?.results?.[0]?.content,
      iteration: (s.extra!.iteration as number) ?? undefined,
    }));

  const extra = atif.extra ?? {};

  // Extract iterations from ATIF steps (multi-turn support)
  const iterations: Iteration[] = [];
  const iterationMap = new Map<number, { stages: Stage[], generatedFiles?: Record<string, string>, feedback?: string }>();

  for (const step of atif.steps) {
    if (step.source === 'system' && step.extra?.iteration) {
      const iterNum = step.extra.iteration as number;
      if (!iterationMap.has(iterNum)) {
        iterationMap.set(iterNum, { stages: [], generatedFiles: undefined, feedback: undefined });
      }
      const iterData = iterationMap.get(iterNum)!;
      iterData.stages.push({
        stage: step.extra.stage as string,
        status: step.extra.status as Stage['status'],
        score: (step.extra.score as number) ?? 0,
        message: (step.extra.message as string) ?? step.message,
        duration_seconds: (step.extra.duration_seconds as number) ?? 0,
        details: (step.extra.details as Record<string, unknown>) ?? {},
        output: step.observation?.results?.[0]?.content,
        iteration: iterNum,
      });
    } else if (step.source === 'agent' && step.message.includes('Generated') && step.message.includes('Terraform file')) {
      // Try to extract iteration number from message
      const match = step.message.match(/iteration (\d+)/);
      if (match) {
        const iterNum = parseInt(match[1]);
        if (!iterationMap.has(iterNum)) {
          iterationMap.set(iterNum, { stages: [], generatedFiles: undefined, feedback: undefined });
        }
        // Note: generated_files are stored in extra.generated_files for the whole trajectory
      }
    } else if (step.source === 'user' && step.message.includes('fix')) {
      // This is refinement feedback
      const sortedIters = Array.from(iterationMap.keys()).sort((a, b) => b - a);
      if (sortedIters.length > 0) {
        const latestIter = iterationMap.get(sortedIters[0])!;
        latestIter.feedback = step.message;
      }
    }
  }

  // Convert iteration map to array
  for (const [iterNum, data] of Array.from(iterationMap.entries()).sort((a, b) => a[0] - b[0])) {
    const iterScore = data.stages.length > 0
      ? data.stages.reduce((sum, s) => sum + s.score, 0) / data.stages.length
      : 0;

    iterations.push({
      iteration_number: iterNum,
      generated_files: data.generatedFiles ?? {},
      stages: data.stages,
      score: iterScore,
      feedback: data.feedback,
    });
  }

  return {
    trajectory_format: atif.schema_version,
    instance_id: atif.session_id,
    info: {
      problem_statement: (extra.problem_statement as string) ?? '',
      region: (extra.region as string) ?? '',
      expected_resources: (extra.expected_resources as Record<string, number>) ?? {},
      model: atif.agent.model_name,
      total_score: (extra.total_score as number) ?? 0,
      total_time_seconds: (extra.total_time_seconds as number) ?? 0,
    },
    generated_files: (extra.generated_files as Record<string, string>) ?? {},
    stages,
    iterations: iterations.length > 0 ? iterations : undefined,
    best_score: (extra.best_score as number) ?? undefined,
    num_iterations: (extra.iterations as number) ?? (iterations.length > 0 ? iterations.length : undefined),
  };
}
