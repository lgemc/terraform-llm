"""Execution tracing in mini-swe-agent compatible format."""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional


class ExecutionTracer:
    """Records execution traces compatible with mini-swe-agent trajectory format."""

    def __init__(self, traces_dir: str = "traces"):
        """
        Initialize tracer.

        Args:
            traces_dir: Base directory for traces
        """
        self.traces_dir = Path(traces_dir)
        self.current_run_dir: Optional[Path] = None
        self.traces: Dict[str, Dict[str, Any]] = {}

    def start_run(self, run_name: Optional[str] = None) -> Path:
        """
        Start a new run with timestamped directory.

        Args:
            run_name: Optional prefix for run directory

        Returns:
            Path to the run directory
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
        run_dir_name = f"{run_name}_{timestamp}" if run_name else timestamp

        self.current_run_dir = self.traces_dir / run_dir_name
        self.current_run_dir.mkdir(parents=True, exist_ok=True)

        return self.current_run_dir

    def start_instance(self, instance_id: str, problem_statement: str) -> None:
        """
        Start tracing a benchmark instance.

        Args:
            instance_id: Unique instance identifier
            problem_statement: Problem description
        """
        self.traces[instance_id] = {
            "instance_id": instance_id,
            "problem_statement": problem_statement,
            "trajectory_format": "terraform-agent-1.0",
            "start_time": datetime.now().isoformat(),
            "messages": [],
            "steps": [],
            "info": {
                "exit_status": "",
                "passed": False,
            }
        }

    def add_message(
        self,
        instance_id: str,
        role: str,
        content: str,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a message to the trace (compatible with LLM conversation format).

        Args:
            instance_id: Instance being traced
            role: Message role (system, user, assistant, tool)
            content: Message content
            extra: Additional metadata
        """
        if instance_id not in self.traces:
            raise ValueError(f"Instance {instance_id} not started")

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

        if extra:
            message["extra"] = extra

        self.traces[instance_id]["messages"].append(message)

    def add_step(
        self,
        instance_id: str,
        step_name: str,
        step_type: str,
        result: Dict[str, Any]
    ) -> None:
        """
        Add an execution step to the trace.

        Args:
            instance_id: Instance being traced
            step_name: Step name (init, validate, plan, apply, etc.)
            step_type: Step type (terraform, validation, cleanup)
            result: Step execution result
        """
        if instance_id not in self.traces:
            raise ValueError(f"Instance {instance_id} not started")

        step = {
            "name": step_name,
            "type": step_type,
            "timestamp": datetime.now().isoformat(),
            "result": result
        }

        self.traces[instance_id]["steps"].append(step)

    def end_instance(
        self,
        instance_id: str,
        exit_status: str,
        passed: bool,
        submission: str = "",
        final_result: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Complete instance tracing.

        Args:
            instance_id: Instance being traced
            exit_status: Exit status (success, error, timeout, etc.)
            passed: Whether instance passed validation
            submission: Final output/submission
            final_result: Complete result dictionary
        """
        if instance_id not in self.traces:
            raise ValueError(f"Instance {instance_id} not started")

        self.traces[instance_id]["end_time"] = datetime.now().isoformat()
        self.traces[instance_id]["info"]["exit_status"] = exit_status
        self.traces[instance_id]["info"]["passed"] = passed
        self.traces[instance_id]["info"]["submission"] = submission

        if final_result:
            self.traces[instance_id]["final_result"] = final_result

    def save_instance(self, instance_id: str) -> Path:
        """
        Save instance trace to disk.

        Args:
            instance_id: Instance to save

        Returns:
            Path to saved trace file
        """
        if instance_id not in self.traces:
            raise ValueError(f"Instance {instance_id} not started")

        if self.current_run_dir is None:
            raise ValueError("No run started. Call start_run() first.")

        trace_file = self.current_run_dir / f"{instance_id}.json"

        with open(trace_file, 'w') as f:
            json.dump(self.traces[instance_id], f, indent=2)

        return trace_file

    def save_all(self) -> List[Path]:
        """
        Save all instance traces to disk.

        Returns:
            List of saved trace file paths
        """
        if self.current_run_dir is None:
            raise ValueError("No run started. Call start_run() first.")

        return [self.save_instance(instance_id) for instance_id in self.traces]

    def save_summary(self, summary: Dict[str, Any]) -> Path:
        """
        Save run summary with aggregated statistics.

        Args:
            summary: Summary statistics

        Returns:
            Path to summary file
        """
        if self.current_run_dir is None:
            raise ValueError("No run started. Call start_run() first.")

        summary_file = self.current_run_dir / "summary.json"

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        return summary_file

    def get_trace(self, instance_id: str) -> Dict[str, Any]:
        """Get trace for specific instance."""
        return self.traces.get(instance_id, {})
