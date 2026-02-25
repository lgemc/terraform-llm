"""Docker-based benchmark executor with Localstack and trace storage."""

import json
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from .docker_environment import LocalstackDockerEnvironment
from .terraform import create_terraform_files


class DockerBenchmarkExecutor:
    """
    Executes benchmark instances in isolated Docker containers with Localstack.

    This executor follows the mini-swe-agent pattern:
    - Runs Terraform in Docker with Localstack for AWS mocking
    - Mounts validation scripts and executes them in containers
    - Stores detailed execution traces similar to mini-swe-agent trajectories
    """

    def __init__(
        self,
        output_dir: str,
        terraform_image: str = "hashicorp/terraform:latest",
        localstack_image: str = "localstack/localstack:latest",
    ):
        """
        Initialize docker-based executor.

        Args:
            output_dir: Base directory for outputs and traces
            terraform_image: Docker image for Terraform
            localstack_image: Docker image for Localstack
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.terraform_image = terraform_image
        self.localstack_image = localstack_image

    def execute_instance(
        self,
        instance_id: str,
        terraform_code: Dict[str, str],
        validation_script: str,
        region: str,
        expected_resources: Dict[str, int],
        problem_statement: str = "",
        cleanup: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute a complete benchmark instance in Docker with trace storage.

        Args:
            instance_id: Instance identifier
            terraform_code: Dictionary with terraform files
            validation_script: Path to validation script
            region: AWS region
            expected_resources: Expected resource counts
            problem_statement: Original problem statement
            cleanup: Whether to destroy infrastructure after tests

        Returns:
            Dictionary with execution results and trace path
        """
        instance_dir = self.output_dir / instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)

        # Initialize trace
        trace = self._init_trace(
            instance_id=instance_id,
            problem_statement=problem_statement,
            terraform_code=terraform_code,
            validation_script=validation_script,
            region=region,
            expected_resources=expected_resources,
        )

        results = {
            "instance_id": instance_id,
            "terraform": {},
            "validation": {},
            "passed": False,
            "trace_path": str(instance_dir / f"{instance_id}.traj.json"),
        }

        docker_env = None
        start_time = time.time()

        try:
            # Create Terraform files
            self._create_terraform_files(instance_dir, terraform_code)
            trace["steps"].append({
                "step": "create_files",
                "timestamp": time.time(),
                "status": "success",
                "message": "Created Terraform files",
            })

            # Start Docker environment with Localstack
            docker_env = LocalstackDockerEnvironment(
                work_dir=str(instance_dir),
                image=self.terraform_image,
                localstack_image=self.localstack_image,
            )

            trace["steps"].append({
                "step": "docker_setup",
                "timestamp": time.time(),
                "status": "success",
                "message": f"Started Docker environment with Localstack",
                "network": docker_env.network_name,
                "localstack_container": docker_env.localstack_container_id,
            })

            # Execute Terraform workflow
            tf_results = self._run_terraform_workflow(
                docker_env,
                expected_resources,
                trace,
            )
            results["terraform"] = tf_results

            # If Terraform succeeded, run validation
            if tf_results.get("success", False):
                validation_results = self._run_validation(
                    docker_env,
                    validation_script,
                    region,
                    trace,
                )
                results["validation"] = validation_results
                results["passed"] = validation_results.get("passed", False)

                trace["info"]["exit_status"] = "Passed" if results["passed"] else "Failed"
            else:
                trace["info"]["exit_status"] = "TerraformFailed"

        except Exception as e:
            results["error"] = str(e)
            trace["info"]["exit_status"] = "Error"
            trace["steps"].append({
                "step": "error",
                "timestamp": time.time(),
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

        finally:
            # Cleanup Docker resources
            if docker_env:
                try:
                    if cleanup:
                        cleanup_result = self._cleanup_terraform(docker_env, trace)
                        results["cleanup"] = cleanup_result

                    docker_env.cleanup()
                    trace["steps"].append({
                        "step": "docker_cleanup",
                        "timestamp": time.time(),
                        "status": "success",
                        "message": "Cleaned up Docker resources",
                    })
                except Exception as e:
                    trace["steps"].append({
                        "step": "docker_cleanup",
                        "timestamp": time.time(),
                        "status": "error",
                        "error": str(e),
                    })

            # Finalize trace
            trace["info"]["total_time_seconds"] = time.time() - start_time
            trace["info"]["passed"] = results["passed"]

            # Save trace
            trace_path = instance_dir / f"{instance_id}.traj.json"
            self._save_trace(trace, trace_path)
            trace["steps"].append({
                "step": "save_trace",
                "timestamp": time.time(),
                "status": "success",
                "path": str(trace_path),
            })

        return results

    def _init_trace(
        self,
        instance_id: str,
        problem_statement: str,
        terraform_code: Dict[str, str],
        validation_script: str,
        region: str,
        expected_resources: Dict[str, int],
    ) -> Dict[str, Any]:
        """Initialize execution trace."""
        return {
            "trajectory_format": "terraform-agent-1.0",
            "instance_id": instance_id,
            "info": {
                "problem_statement": problem_statement,
                "region": region,
                "expected_resources": expected_resources,
                "validation_script": validation_script,
                "exit_status": "InProgress",
                "passed": False,
                "total_time_seconds": 0,
            },
            "terraform_code": terraform_code,
            "steps": [],
        }

    def _create_terraform_files(
        self,
        work_dir: Path,
        terraform_code: Dict[str, str],
    ) -> None:
        """Create Terraform files from code dictionary."""
        create_terraform_files(
            working_dir=str(work_dir),
            main_tf=terraform_code.get("main.tf", ""),
            variables_tf=terraform_code.get("variables.tf"),
            outputs_tf=terraform_code.get("outputs.tf"),
            terraform_tfvars=terraform_code.get("terraform.tfvars"),
        )

    def _run_terraform_workflow(
        self,
        docker_env: LocalstackDockerEnvironment,
        expected_resources: Dict[str, int],
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run complete Terraform workflow in Docker."""
        results = {}

        # Terraform init
        step_start = time.time()
        init_result = docker_env.execute_terraform_command("terraform init")
        results["init"] = init_result

        trace["steps"].append({
            "step": "terraform_init",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform init",
            "status": "success" if init_result["success"] else "failed",
            "output": init_result["output"],
            "stderr": init_result.get("stderr", ""),
            "returncode": init_result["returncode"],
        })

        if not init_result["success"]:
            results["success"] = False
            results["stage"] = "init"
            return results

        # Terraform validate
        step_start = time.time()
        validate_result = docker_env.execute_terraform_command("terraform validate -json")
        results["validate"] = validate_result

        trace["steps"].append({
            "step": "terraform_validate",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform validate",
            "status": "success" if validate_result["success"] else "failed",
            "output": validate_result["output"],
            "stderr": validate_result.get("stderr", ""),
            "returncode": validate_result["returncode"],
        })

        if not validate_result["success"]:
            results["success"] = False
            results["stage"] = "validate"
            return results

        # Terraform plan
        step_start = time.time()
        plan_result = docker_env.execute_terraform_command("terraform plan -out=tfplan")
        results["plan"] = plan_result

        trace["steps"].append({
            "step": "terraform_plan",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform plan",
            "status": "success" if plan_result["success"] else "failed",
            "output": plan_result["output"],
            "stderr": plan_result.get("stderr", ""),
            "returncode": plan_result["returncode"],
        })

        if not plan_result["success"]:
            results["success"] = False
            results["stage"] = "plan"
            return results

        # Terraform apply
        step_start = time.time()
        apply_result = docker_env.execute_terraform_command("terraform apply -auto-approve tfplan")
        results["apply"] = apply_result

        trace["steps"].append({
            "step": "terraform_apply",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform apply",
            "status": "success" if apply_result["success"] else "failed",
            "output": apply_result["output"],
            "stderr": apply_result.get("stderr", ""),
            "returncode": apply_result["returncode"],
        })

        if not apply_result["success"]:
            results["success"] = False
            results["stage"] = "apply"
            return results

        # Get outputs
        step_start = time.time()
        output_result = docker_env.execute_terraform_command("terraform output -json")

        if output_result["success"]:
            try:
                outputs = json.loads(output_result["output"])
                results["outputs"] = outputs
            except json.JSONDecodeError:
                results["outputs"] = {}

        trace["steps"].append({
            "step": "terraform_output",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform output",
            "status": "success" if output_result["success"] else "failed",
            "outputs": results.get("outputs", {}),
        })

        # Count resources from state
        step_start = time.time()
        state_result = docker_env.execute_terraform_command("terraform state list")

        if state_result["success"]:
            resource_counts = self._count_resources_from_state(state_result["output"])
            results["resource_counts"] = resource_counts

            # Validate resource counts
            resource_validation = self._validate_resources(
                resource_counts,
                expected_resources,
            )
            results["resource_validation"] = resource_validation

            trace["steps"].append({
                "step": "resource_validation",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "resource_counts": resource_counts,
                "expected_resources": expected_resources,
                "validation": resource_validation,
            })

        results["success"] = True
        results["stage"] = "completed"

        return results

    def _count_resources_from_state(self, state_list_output: str) -> Dict[str, int]:
        """Count resources by type from terraform state list output."""
        resource_counts: Dict[str, int] = {}

        for line in state_list_output.strip().split("\n"):
            if not line:
                continue

            # Extract resource type (e.g., "aws_vpc.main" -> "aws_vpc")
            if "." in line:
                resource_type = line.split(".")[0]
                resource_counts[resource_type] = resource_counts.get(resource_type, 0) + 1

        return resource_counts

    def _validate_resources(
        self,
        actual: Dict[str, int],
        expected: Dict[str, int],
    ) -> Dict[str, Any]:
        """Validate actual resources match expected."""
        validation = {
            "passed": True,
            "mismatches": [],
        }

        for resource_type, expected_count in expected.items():
            actual_count = actual.get(resource_type, 0)

            if actual_count != expected_count:
                validation["passed"] = False
                validation["mismatches"].append({
                    "resource_type": resource_type,
                    "expected": expected_count,
                    "actual": actual_count,
                })

        return validation

    def _run_validation(
        self,
        docker_env: LocalstackDockerEnvironment,
        validation_script: str,
        region: str,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Run validation script in Docker."""
        step_start = time.time()

        validation_result = docker_env.execute_validation_script(
            validation_script,
            region,
        )

        trace["steps"].append({
            "step": "validation",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "validation_script": validation_script,
            "status": "passed" if validation_result.get("passed", False) else "failed",
            "output": validation_result.get("output", ""),
            "stderr": validation_result.get("stderr", ""),
            "error": validation_result.get("error"),
        })

        return validation_result

    def _cleanup_terraform(
        self,
        docker_env: LocalstackDockerEnvironment,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Destroy Terraform infrastructure."""
        step_start = time.time()

        destroy_result = docker_env.execute_terraform_command("terraform destroy -auto-approve")

        trace["steps"].append({
            "step": "terraform_destroy",
            "timestamp": time.time(),
            "duration": time.time() - step_start,
            "command": "terraform destroy",
            "status": "success" if destroy_result["success"] else "failed",
            "output": destroy_result.get("output", ""),
            "stderr": destroy_result.get("stderr", ""),
        })

        return {
            "destroyed": destroy_result["success"],
            "output": destroy_result,
        }

    def _save_trace(self, trace: Dict[str, Any], path: Path) -> None:
        """Save execution trace to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(trace, f, indent=2)
