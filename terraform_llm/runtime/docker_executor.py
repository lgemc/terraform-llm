"""Docker-based benchmark executor with Localstack and trace storage."""

import json
import subprocess
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from terraform_llm.runtime.docker_environment import LocalstackDockerEnvironment
from terraform_llm.runtime.terraform import create_terraform_files


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
        setup_script: Optional[str] = None,
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
            setup_script: Optional path to setup script for pre-existing infrastructure

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

            # Run setup script if provided
            if setup_script:
                print(f"  Running setup script: {setup_script}")
                setup_start = time.time()
                setup_results = self._run_setup_script(docker_env, setup_script, region, trace)
                results["setup"] = setup_results

                if not setup_results.get("success", False):
                    print(f"  Setup script failed!")
                    if "error" in setup_results:
                        print(f"  Error: {setup_results['error']}")
                    if "stderr" in setup_results:
                        print(f"  Stderr: {setup_results['stderr'][:500]}")
                    results["error"] = "Setup script failed"
                    trace["info"]["exit_status"] = "SetupFailed"
                    return results
                else:
                    print(f"  Setup script completed in {time.time() - setup_start:.1f}s")

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

                        # Also cleanup setup script resources if applicable
                        if setup_script:
                            cleanup_script_path = Path(setup_script).parent / "cleanup.sh"
                            if cleanup_script_path.exists():
                                print("  Running cleanup script for setup resources...")
                                cleanup_script_result = self._run_cleanup_script(
                                    docker_env, str(cleanup_script_path), region, trace
                                )
                                results["cleanup"]["setup_cleanup"] = cleanup_script_result

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
            results["exit_status"] = trace["info"]["exit_status"]

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
            terraform_code=terraform_code
        )

    def _run_setup_script(
        self,
        docker_env: LocalstackDockerEnvironment,
        setup_script: str,
        region: str,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute setup script for pre-existing infrastructure.

        Args:
            docker_env: Docker environment
            setup_script: Path to setup script
            region: AWS region
            trace: Execution trace

        Returns:
            Dictionary with setup results
        """
        step_start = time.time()
        setup_script_path = Path(setup_script)

        if not setup_script_path.exists():
            error_msg = f"Setup script not found: {setup_script}"
            trace["steps"].append({
                "step": "setup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "error",
                "error": error_msg,
            })
            return {
                "success": False,
                "error": error_msg,
            }

        # Copy setup script to working directory
        import shutil
        work_dir = Path(docker_env.work_dir)
        setup_script_copy = work_dir / "setup.sh"
        shutil.copy(setup_script_path, setup_script_copy)
        print(f"    Copied setup script to {setup_script_copy}")

        # Also copy lambda_code directory if it exists
        lambda_code_dir = setup_script_path.parent / "lambda_code"
        if lambda_code_dir.exists():
            dest_lambda_code_dir = work_dir / "lambda_code"
            if dest_lambda_code_dir.exists():
                shutil.rmtree(dest_lambda_code_dir)
            shutil.copytree(lambda_code_dir, dest_lambda_code_dir)
            print(f"    Copied lambda_code directory")

        # Execute setup script in a container with Go and AWS CLI
        # Using a custom image that has both Go and AWS CLI
        env_vars = {
            "AWS_DEFAULT_REGION": region,
            "AWS_REGION": region,
        }

        # Run the setup script
        command = "apk add --no-cache aws-cli bash zip && chmod +x /workspace/setup.sh && /bin/bash /workspace/setup.sh"

        # Build docker command similar to execute_terraform_command
        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{docker_env.localstack_container_name}:4566",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", docker_env.network_name,
            "-v", f"{work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Use alpine with sh
        cmd.extend([
            "golang:alpine",
            "sh", "-c",
            command,
        ])

        print(f"    Executing setup in Docker (timeout: 300s)...")
        print(f"    Installing: aws-cli, bash, zip, go")
        print(f"    This may take a few minutes on first run...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            print(f"    Setup script returned code: {result.returncode}")

            # Show some output for debugging
            if result.stdout:
                print(f"    Stdout preview: {result.stdout[-200:]}")
            if result.stderr and result.returncode != 0:
                print(f"    Stderr preview: {result.stderr[-200:]}")

            success = result.returncode == 0

            trace["steps"].append({
                "step": "setup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "success" if success else "failed",
                "output": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            })

            return {
                "success": success,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            error_msg = "Setup script timed out after 5 minutes"
            trace["steps"].append({
                "step": "setup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "error",
                "error": error_msg,
            })
            return {
                "success": False,
                "error": error_msg,
            }
        except Exception as e:
            error_msg = str(e)
            trace["steps"].append({
                "step": "setup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "error",
                "error": error_msg,
            })
            return {
                "success": False,
                "error": error_msg,
            }

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

    def _run_cleanup_script(
        self,
        docker_env: LocalstackDockerEnvironment,
        cleanup_script: str,
        region: str,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute cleanup script for pre-existing infrastructure."""
        step_start = time.time()
        cleanup_script_path = Path(cleanup_script)

        if not cleanup_script_path.exists():
            return {"success": False, "error": "Cleanup script not found"}

        # Copy cleanup script to working directory
        import shutil
        work_dir = Path(docker_env.work_dir)
        cleanup_script_copy = work_dir / "cleanup.sh"
        shutil.copy(cleanup_script_path, cleanup_script_copy)

        # Build environment
        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{docker_env.localstack_container_name}:4566",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", docker_env.network_name,
            "-v", f"{work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Use alpine with bash and aws-cli
        command = "apk add --no-cache aws-cli bash && chmod +x /workspace/cleanup.sh && /bin/bash /workspace/cleanup.sh"
        cmd.extend(["alpine:latest", "sh", "-c", command])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            trace["steps"].append({
                "step": "cleanup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "success" if result.returncode == 0 else "failed",
                "output": result.stdout,
                "stderr": result.stderr,
            })

            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            trace["steps"].append({
                "step": "cleanup_script",
                "timestamp": time.time(),
                "duration": time.time() - step_start,
                "status": "error",
                "error": str(e),
            })
            return {"success": False, "error": str(e)}

    def _cleanup_terraform(
        self,
        docker_env: LocalstackDockerEnvironment,
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Destroy Terraform infrastructure."""
        step_start = time.time()

        print("  Running terraform destroy...")

        # Set a shorter timeout for destroy to avoid hanging on LocalStack bugs
        # Save original timeout and restore after
        original_timeout = docker_env.timeout
        docker_env.timeout = 60  # 60 second timeout for destroy

        try:
            destroy_result = docker_env.execute_terraform_command("terraform destroy -auto-approve")
        except Exception as e:
            print(f"  Destroy encountered error (continuing anyway): {e}")
            destroy_result = {
                "success": False,
                "error": str(e),
                "output": "",
                "stderr": str(e)
            }
        finally:
            docker_env.timeout = original_timeout

        duration = time.time() - step_start

        if destroy_result.get("success"):
            print(f"  Terraform destroy completed in {duration:.1f}s")
        else:
            print(f"  Terraform destroy failed after {duration:.1f}s (LocalStack cleanup issue)")
            # Show some error info but don't fail the whole test
            if "stderr" in destroy_result and destroy_result["stderr"]:
                print(f"  Destroy stderr (first 300 chars): {destroy_result['stderr'][:300]}")

        trace["steps"].append({
            "step": "terraform_destroy",
            "timestamp": time.time(),
            "duration": duration,
            "command": "terraform destroy",
            "status": "success" if destroy_result.get("success") else "failed",
            "output": destroy_result.get("output", ""),
            "stderr": destroy_result.get("stderr", ""),
        })

        return {
            "destroyed": destroy_result.get("success", False),
            "output": destroy_result,
        }

    def _save_trace(self, trace: Dict[str, Any], path: Path) -> None:
        """Save execution trace to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(trace, f, indent=2)
