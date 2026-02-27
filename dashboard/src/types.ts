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
