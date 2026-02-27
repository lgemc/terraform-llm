"""Result dataclasses for benchmark evaluation."""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class StageStatus(str, Enum):
    """Status of an evaluation stage."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class StageResult:
    """Result of a single evaluation stage."""
    stage: str
    status: StageStatus
    score: float
    message: str = ""
    duration_seconds: float = 0.0
    raw_output: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = {
            "stage": self.stage,
            "status": self.status.value,
            "score": self.score,
            "message": self.message,
            "duration_seconds": self.duration_seconds,
            "details": self.details,
        }
        if self.raw_output:
            d["output"] = self.raw_output
        return d


STAGE_WEIGHTS = {
    "init": 0.1,
    "validate": 0.2,
    "plan": 0.4,
    "apply": 0.2,
    "validation_script": 0.1,
}


@dataclass
class InstanceResult:
    """Result of evaluating a single benchmark instance."""
    instance_id: str
    model: str = ""
    stages: List[StageResult] = field(default_factory=list)
    generated_files: Dict[str, str] = field(default_factory=dict)
    total_score: float = 0.0
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)  # Track tool calls (RAG searches, etc.)
    prompt: Optional[str] = None  # The actual prompt sent to the LLM

    # Stages that are excluded from scoring (infrastructure setup, not model quality)
    _UNSCORED_STAGES = {"setup_script", "cleanup_script", "destroy"}

    def compute_total_score(self) -> float:
        """Compute weighted total score across stages."""
        total_weight = 0.0
        weighted_sum = 0.0
        for stage in self.stages:
            if stage.status == StageStatus.SKIPPED:
                continue
            if stage.stage in self._UNSCORED_STAGES:
                continue
            w = STAGE_WEIGHTS.get(stage.stage, 0.1)
            weighted_sum += stage.score * w
            total_weight += w
        self.total_score = weighted_sum / total_weight if total_weight > 0 else 0.0
        return self.total_score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "instance_id": self.instance_id,
            "model": self.model,
            "total_score": self.total_score,
            "stages": [s.to_dict() for s in self.stages],
            "generated_files": self.generated_files,
            "error": self.error,
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.prompt:
            result["prompt"] = self.prompt
        return result


@dataclass
class BenchmarkReport:
    """Aggregated results across multiple instances."""
    model: str
    results: List[InstanceResult] = field(default_factory=list)

    @property
    def mean_score(self) -> float:
        """Mean total score across all instances."""
        if not self.results:
            return 0.0
        return sum(r.total_score for r in self.results) / len(self.results)

    def stage_pass_rates(self) -> Dict[str, float]:
        """Pass rate per stage across all instances."""
        stage_counts: Dict[str, List[bool]] = {}
        for result in self.results:
            for stage in result.stages:
                if stage.status != StageStatus.SKIPPED:
                    stage_counts.setdefault(stage.stage, []).append(
                        stage.status == StageStatus.PASSED
                    )
        return {
            stage: sum(vals) / len(vals)
            for stage, vals in stage_counts.items()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "model": self.model,
            "mean_score": self.mean_score,
            "stage_pass_rates": self.stage_pass_rates(),
            "num_instances": len(self.results),
            "results": [r.to_dict() for r in self.results],
        }
