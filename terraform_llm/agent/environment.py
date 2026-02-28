"""Terraform execution environment using subprocess or Docker containers."""

import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass

from terraform_llm.agent.results import StageResult, StageStatus

if TYPE_CHECKING:
    from terraform_llm.agent.docker_environment import LocalstackDockerEnvironment

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a subprocess command."""
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float


def create_terraform_files(working_dir: str, terraform_code: dict[str, str]) -> None:
    """Create Terraform configuration files in the given directory."""
    work_dir = Path(working_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in terraform_code.items():
        if content:
            filepath = work_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)


class TerraformEnvironment:
    """Manages a temporary directory with Terraform files and runs terraform commands."""

    def __init__(
        self,
        work_dir: Optional[str] = None,
        docker_env: Optional["LocalstackDockerEnvironment"] = None,
    ):
        """
        Initialize environment.

        Args:
            work_dir: Optional explicit working directory. If None, creates a temp dir.
            docker_env: Optional LocalstackDockerEnvironment. When provided, runs terraform
                        via Docker containers instead of local subprocess.
        """
        self._temp_dir: Optional[tempfile.TemporaryDirectory] = None
        self._docker_env = docker_env

        if work_dir:
            self.work_dir = Path(work_dir)
        else:
            self._temp_dir = tempfile.TemporaryDirectory(prefix="terraform-bench-")
            self.work_dir = Path(self._temp_dir.name)

    @property
    def use_docker(self) -> bool:
        return self._docker_env is not None

    def setup(self, files: dict[str, str]) -> None:
        """Write HCL files to the working directory."""
        for filename, content in files.items():
            filepath = self.work_dir / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)
            logger.debug(f"Wrote {filepath}")

    def run_command(self, args: list[str], timeout: int = 300) -> CommandResult:
        """Run a command in the working directory (local subprocess)."""
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

    def _run_docker_command(self, command: str, timeout: int = 300) -> CommandResult:
        """Run a terraform command via Docker container."""
        start = time.monotonic()
        original_timeout = self._docker_env.timeout
        self._docker_env.timeout = timeout
        try:
            result = self._docker_env.execute_terraform_command(command, work_dir=self.work_dir)
            duration = time.monotonic() - start
            return CommandResult(
                returncode=result["returncode"],
                stdout=result.get("output", ""),
                stderr=result.get("stderr", ""),
                duration_seconds=duration,
            )
        finally:
            self._docker_env.timeout = original_timeout

    def _exec(self, args: list[str], command_str: str, timeout: int = 300) -> CommandResult:
        """Execute a command, routing through Docker or local subprocess."""
        if self.use_docker:
            return self._run_docker_command(command_str, timeout=timeout)
        return self.run_command(args, timeout=timeout)

    def terraform_init(self, timeout: int = 120) -> StageResult:
        """Run terraform init and return a StageResult."""
        result = self._exec(
            ["terraform", "init", "-input=false"],
            "terraform init -input=false",
            timeout=timeout,
        )
        if result.returncode == 0:
            return StageResult(
                stage="init",
                status=StageStatus.PASSED,
                score=1.0,
                message="terraform init succeeded",
                duration_seconds=result.duration_seconds,
                raw_output=result.stdout,
            )
        # Capture both stdout and stderr for failures
        error_output = result.stdout if result.stdout else result.stderr
        if result.stdout and result.stderr:
            error_output = result.stdout + "\n" + result.stderr
        return StageResult(
            stage="init",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform init failed",
            duration_seconds=result.duration_seconds,
            raw_output=error_output,
        )

    def terraform_validate(self, timeout: int = 60) -> StageResult:
        """Run terraform validate -json and return a StageResult."""
        result = self._exec(
            ["terraform", "validate", "-json"],
            "terraform validate -json",
            timeout=timeout,
        )

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
        """Run terraform plan and return a StageResult with resource counts."""
        start = time.monotonic()

        plan_result = self._exec(
            ["terraform", "plan", "-out=tfplan", "-input=false"],
            "terraform plan -out=tfplan -input=false",
            timeout=timeout,
        )
        if plan_result.returncode != 0:
            # Capture both stdout and stderr for failures
            error_output = plan_result.stdout if plan_result.stdout else plan_result.stderr
            if plan_result.stdout and plan_result.stderr:
                error_output = plan_result.stdout + "\n" + plan_result.stderr
            return StageResult(
                stage="plan",
                status=StageStatus.FAILED,
                score=0.0,
                message="terraform plan failed",
                duration_seconds=time.monotonic() - start,
                raw_output=error_output,
            )

        show_result = self._exec(
            ["terraform", "show", "-json", "tfplan"],
            "terraform show -json tfplan",
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
        result = self._exec(
            ["terraform", "apply", "-auto-approve", "-input=false"],
            "terraform apply -auto-approve -input=false",
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
        # Capture both stdout and stderr for failures (terraform writes errors to both)
        error_output = result.stdout if result.stdout else result.stderr
        if result.stdout and result.stderr:
            error_output = result.stdout + "\n" + result.stderr
        return StageResult(
            stage="apply",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform apply failed",
            duration_seconds=result.duration_seconds,
            raw_output=error_output,
        )

    def terraform_destroy(self, timeout: int = 600) -> StageResult:
        """Run terraform destroy -auto-approve and return a StageResult."""
        result = self._exec(
            ["terraform", "destroy", "-auto-approve", "-input=false"],
            "terraform destroy -auto-approve -input=false",
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
        # Capture both stdout and stderr for failures
        error_output = result.stdout if result.stdout else result.stderr
        if result.stdout and result.stderr:
            error_output = result.stdout + "\n" + result.stderr
        return StageResult(
            stage="destroy",
            status=StageStatus.FAILED,
            score=0.0,
            message="terraform destroy failed",
            duration_seconds=result.duration_seconds,
            raw_output=error_output,
        )

    def run_validation_script(self, script_path: str, timeout: int = 120) -> StageResult:
        """Run an external validation script and return a StageResult."""
        if self.use_docker:
            return self._run_docker_validation_script(script_path, timeout)
        return self._run_local_validation_script(script_path, timeout)

    def _run_local_validation_script(self, script_path: str, timeout: int = 120) -> StageResult:
        """Run validation script locally."""
        import os
        original_cwd = Path.cwd()
        resolved_script = original_cwd / script_path

        if not resolved_script.exists():
            return StageResult(
                stage="validation_script",
                status=StageStatus.ERROR,
                score=0.0,
                message=f"Validation script not found: {script_path}",
                duration_seconds=0.0,
                raw_output=f"Script path: {resolved_script}",
            )

        result = self.run_command(["bash", str(resolved_script)], timeout=timeout)
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

    def _run_docker_validation_script(self, script_path: str, timeout: int = 120) -> StageResult:
        """Run validation script via Docker."""
        start = time.monotonic()
        original_timeout = self._docker_env.timeout
        self._docker_env.timeout = timeout
        try:
            result = self._docker_env.execute_validation_script(script_path, work_dir=self.work_dir)
            duration = time.monotonic() - start

            if result.get("passed", False):
                return StageResult(
                    stage="validation_script",
                    status=StageStatus.PASSED,
                    score=1.0,
                    message="Validation script passed",
                    duration_seconds=duration,
                    raw_output=result.get("output", ""),
                )

            error_msg = result.get("error", "")
            output = result.get("output", "") + result.get("stderr", "")
            return StageResult(
                stage="validation_script",
                status=StageStatus.FAILED if not error_msg else StageStatus.ERROR,
                score=0.0,
                message=f"Validation script failed{': ' + error_msg if error_msg else ''}",
                duration_seconds=duration,
                raw_output=output,
            )
        finally:
            self._docker_env.timeout = original_timeout

    def run_setup_script(self, script_path: str, region: str = "us-east-1") -> StageResult:
        """Run a setup script for pre-existing infrastructure."""
        if not self.use_docker:
            return self._run_local_setup_script(script_path, region)

        start = time.monotonic()
        result = self._docker_env.execute_setup_script(script_path, region, work_dir=self.work_dir)
        duration = time.monotonic() - start

        if result.get("success", False):
            return StageResult(
                stage="setup_script",
                status=StageStatus.PASSED,
                score=1.0,
                message="Setup script succeeded",
                duration_seconds=duration,
                raw_output=result.get("stdout", ""),
            )
        return StageResult(
            stage="setup_script",
            status=StageStatus.FAILED,
            score=0.0,
            message=f"Setup script failed: {result.get('error', '')}",
            duration_seconds=duration,
            raw_output=result.get("stderr", result.get("error", "")),
        )

    def _run_local_setup_script(self, script_path: str, region: str) -> StageResult:
        """Run setup script locally."""
        import os
        resolved_script = Path(script_path)
        if not resolved_script.is_absolute():
            resolved_script = Path.cwd() / script_path

        if not resolved_script.exists():
            return StageResult(
                stage="setup_script",
                status=StageStatus.ERROR,
                score=0.0,
                message=f"Setup script not found: {script_path}",
                duration_seconds=0.0,
            )

        env = os.environ.copy()
        env["AWS_DEFAULT_REGION"] = region
        env["AWS_REGION"] = region

        start = time.monotonic()
        try:
            proc = subprocess.run(
                ["/bin/bash", str(resolved_script)],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )
            duration = time.monotonic() - start
            if proc.returncode == 0:
                return StageResult(
                    stage="setup_script",
                    status=StageStatus.PASSED,
                    score=1.0,
                    message="Setup script succeeded",
                    duration_seconds=duration,
                    raw_output=proc.stdout,
                )
            return StageResult(
                stage="setup_script",
                status=StageStatus.FAILED,
                score=0.0,
                message="Setup script failed",
                duration_seconds=duration,
                raw_output=proc.stdout + proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return StageResult(
                stage="setup_script",
                status=StageStatus.ERROR,
                score=0.0,
                message="Setup script timed out",
                duration_seconds=time.monotonic() - start,
            )

    def run_cleanup_script(self, script_path: str, region: str = "us-east-1") -> StageResult:
        """Run a cleanup script."""
        if not self.use_docker:
            return self._run_local_cleanup_script(script_path, region)

        start = time.monotonic()
        result = self._docker_env.execute_cleanup_script(script_path, region, work_dir=self.work_dir)
        duration = time.monotonic() - start

        if result.get("success", False):
            return StageResult(
                stage="cleanup_script",
                status=StageStatus.PASSED,
                score=1.0,
                message="Cleanup script succeeded",
                duration_seconds=duration,
                raw_output=result.get("stdout", ""),
            )
        return StageResult(
            stage="cleanup_script",
            status=StageStatus.FAILED,
            score=0.0,
            message=f"Cleanup script failed: {result.get('error', '')}",
            duration_seconds=duration,
            raw_output=result.get("stderr", result.get("error", "")),
        )

    def _run_local_cleanup_script(self, script_path: str, region: str) -> StageResult:
        """Run cleanup script locally."""
        import os
        resolved_script = Path(script_path)
        if not resolved_script.is_absolute():
            resolved_script = Path.cwd() / script_path

        if not resolved_script.exists():
            return StageResult(
                stage="cleanup_script",
                status=StageStatus.ERROR,
                score=0.0,
                message=f"Cleanup script not found: {script_path}",
                duration_seconds=0.0,
            )

        env = os.environ.copy()
        env["AWS_DEFAULT_REGION"] = region

        start = time.monotonic()
        try:
            proc = subprocess.run(
                ["/bin/bash", str(resolved_script)],
                cwd=self.work_dir,
                capture_output=True,
                text=True,
                env=env,
                timeout=300,
            )
            duration = time.monotonic() - start
            if proc.returncode == 0:
                return StageResult(
                    stage="cleanup_script",
                    status=StageStatus.PASSED,
                    score=1.0,
                    message="Cleanup script succeeded",
                    duration_seconds=duration,
                    raw_output=proc.stdout,
                )
            return StageResult(
                stage="cleanup_script",
                status=StageStatus.FAILED,
                score=0.0,
                message="Cleanup script failed",
                duration_seconds=duration,
                raw_output=proc.stdout + proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return StageResult(
                stage="cleanup_script",
                status=StageStatus.ERROR,
                score=0.0,
                message="Cleanup script timed out",
                duration_seconds=time.monotonic() - start,
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
