"""Terraform execution environment using subprocess in temporary directories."""

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from .results import StageResult, StageStatus

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a subprocess command."""
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


class TerraformEnvironment:
    """Manages a temporary directory with Terraform files and runs terraform commands."""

    def __init__(self, work_dir: Optional[str] = None):
        """
        Initialize environment.

        Args:
            work_dir: Optional explicit working directory. If None, creates a temp dir.
        """
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        if work_dir:
            self.work_dir = Path(work_dir)
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="terraform-bench-")
            self.work_dir = Path(self._temp_dir.name)

    def setup(self, files: dict[str, str]) -> None:
        """Write HCL files to the working directory."""
        for filename, content in files.items():
            filepath = self.work_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            logger.debug(f"Wrote {filepath}")

    def run_command(self, args: list[str], timeout: int = 300) -> CommandResult:
        """Run a command in the working directory."""
        start = time.monotonic()
        try:
            result = subprocess.run(
                args,
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start
            return CommandResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_seconds=duration,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_seconds=duration,
            )
        except FileNotFoundError:
            duration = time.monotonic() - start
            return CommandResult(
                returncode=-1,
                stdout="",
                stderr=f"Command not found: {args[0]}",
                duration_seconds=duration,
            )

    def terraform_init(self, timeout: int = 120) -> StageResult:
        """Run terraform init and return a StageResult."""
        result = self.run_command(["terraform", "init", "-input=false"], timeout=timeout)
        if result.returncode == 0:
            return StageResult(
                stage="init",
                status=StageStatus.PASSED,
                score=1.0,
                message="terraform init succeeded",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
            )
        return StageResult(
            stage="init",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform init failed",
            duration_seconds=result.duration_seconds,
            raw_output=result.stderr,
        )

    def terraform_validate(self, timeout: int = 60) -> StageResult:
        """Run terraform validate -json and return a StageResult."""
        result = self.run_command(["terraform", "validate", "-json"], timeout=timeout)

        try:
            output = json.loads(result.stdout)
            valid = output.get("valid", False)
            diagnostics = output.get("diagnostics", [])
        except (json.JSONDecodeError, KeyError):
            return StageResult(
                stage="validate",
                status=StageStatus.ERROR,
                score=0.0,
                message="Failed to parse validate output",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout + result.stderr,
            )

        if valid:
            return StageResult(
                stage="validate",
                status=StageStatus.PASSED,
                score=1.0,
                message="Validation passed",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
                details={"warning_count": output.get("warning_count", 0)},
            )
        return StageResult(
            stage="validate",
            status=StageStatus.FAILED,
            score=0.0,
            message=f"Validation failed with {output.get('error_count', 0)} error(s)",
            duration_seconds=result.duration_seconds,
            raw_output=result.stdout,
            details={"diagnostics": diagnostics},
        )

    def terraform_plan(self, timeout: int = 300) -> StageResult:
        """
        Run terraform plan and return a StageResult.

        Uses plan -out=tfplan then show -json tfplan to get structured output.
        Parses resource_changes to count resources by type.
        """
        start = time.monotonic()

        plan_result = self.run_command(
            ["terraform", "plan", "-out=tfplan", "-input=false"],
            timeout=timeout,
        )
        if plan_result.returncode != 0:
            return StageResult(
                stage="plan",
                status=StageStatus.FAILED,
                score=0.0,
                message="terraform plan failed",
                duration_seconds=time.monotonic() - start,
                raw_output=plan_result.stderr,
            )

        show_result = self.run_command(
            ["terraform", "show", "-json", "tfplan"],
            timeout=60,
        )
        if show_result.returncode != 0:
            return StageResult(
                stage="plan",
                status=StageStatus.ERROR,
                score=0.0,
                message="terraform show -json failed",
                duration_seconds=time.monotonic() - start,
                raw_output=show_result.stderr,
            )

        try:
            plan_json = json.loads(show_result.stdout)
        except json.JSONDecodeError:
            return StageResult(
                stage="plan",
                status=StageStatus.ERROR,
                score=0.0,
                message="Failed to parse plan JSON",
                duration_seconds=time.monotonic() - start,
                raw_output=show_result.stdout,
            )

        resource_counts: dict[str, int] = {}
        for change in plan_json.get("resource_changes", []):
            if change.get("mode") != "managed":
                continue
            actions = change.get("change", {}).get("actions", [])
            if "create" not in actions:
                continue
            resource_type = change["type"]
            resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1

        duration = time.monotonic() - start
        total_resources = sum(resource_counts.values())
        return StageResult(
            stage="plan",
            status=StageStatus.PASSED,
            score=1.0,
            message=f"Plan succeeded with {total_resources} resource(s)",
            duration_seconds=duration,
            raw_output=plan_result.stdout,
            details={"planned_resources": resource_counts},
        )

    def terraform_apply(self, timeout: int = 600) -> StageResult:
        """Run terraform apply -auto-approve and return a StageResult."""
        result = self.run_command(
            ["terraform", "apply", "-auto-approve", "-input=false"],
            timeout=timeout,
        )
        if result.returncode == 0:
            return StageResult(
                stage="apply",
                status=StageStatus.PASSED,
                score=1.0,
                message="terraform apply succeeded",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
            )
        return StageResult(
            stage="apply",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform apply failed",
            duration_seconds=result.duration_seconds,
            raw_output=result.stderr,
        )

    def terraform_destroy(self, timeout: int = 600) -> StageResult:
        """Run terraform destroy -auto-approve and return a StageResult."""
        result = self.run_command(
            ["terraform", "destroy", "-auto-approve", "-input=false"],
            timeout=timeout,
        )
        if result.returncode == 0:
            return StageResult(
                stage="destroy",
                status=StageStatus.PASSED,
                score=1.0,
                message="terraform destroy succeeded",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
            )
        return StageResult(
            stage="destroy",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform destroy failed",
            duration_seconds=result.duration_seconds,
            raw_output=result.stderr,
        )

    def run_validation_script(self, script_path: str, timeout: int = 120) -> StageResult:
        """Run an external validation script and return a StageResult."""
        result = self.run_command(["bash", script_path], timeout=timeout)
        if result.returncode == 0:
            return StageResult(
                stage="validation_script",
                status=StageStatus.PASSED,
                score=1.0,
                message="Validation script passed",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
            )
        return StageResult(
            stage="validation_script",
            status=StageStatus.FAILED,
            score=0.0,
            message="Validation script failed",
            duration_seconds=result.duration_seconds,
            raw_output=result.stdout + result.stderr,
        )

    def cleanup(self) -> None:
        """Remove temporary directory."""
        if self._temp_dir:
            self._temp_dir.cleanup()
            self._temp_dir = None

    def __enter__(self) -> "TerraformEnvironment":
        return self

    def __exit__(self, *args) -> None:
        self.cleanup()
