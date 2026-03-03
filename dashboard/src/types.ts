export interface Stage {
  stage: string;
  status: "passed" | "failed" | "skipped";
  score: number;
  message: string;
  duration_seconds: number;
  details: Record<string, unknown>;
  output?: string;
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
    }));

  const extra = atif.extra ?? {};

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
  };
}
