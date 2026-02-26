"""Docker environment for isolated Terraform execution with Localstack."""

import logging
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class LocalstackDockerEnvironment:
    """Executes terraform commands in a Docker container with Localstack for AWS mocking."""

    def __init__(
        self,
        *,
        work_dir: str,
        image: str = "hashicorp/terraform:latest",
        localstack_image: str = "localstack/localstack:latest",
        timeout: int = 300,
        logger: Optional[logging.Logger] = None,
    ):
        self.work_dir = Path(work_dir)
        self.image = image
        self.localstack_image = localstack_image
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

        self.network_name = f"terraform-test-{uuid.uuid4().hex[:8]}"
        self.localstack_container_id: Optional[str] = None
        self.localstack_container_name: Optional[str] = None
        self.terraform_container_id: Optional[str] = None

        self._setup_network()
        self._start_localstack()

    def _setup_network(self) -> None:
        """Create a docker network for container communication."""
        cmd = ["docker", "network", "create", self.network_name]
        self.logger.debug(f"Creating network: {shlex.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Failed to create docker network: {result.stderr}")

        self.logger.info(f"Created network: {self.network_name}")

    def _start_localstack(self) -> None:
        """Start or reuse localstack container."""
        existing = self._find_running_localstack()

        if existing:
            self.localstack_container_id, self.localstack_container_name = existing
            self.logger.info(f"Reusing existing localstack container: {self.localstack_container_id} ({self.localstack_container_name})")
            self._connect_to_network(self.localstack_container_id, self.network_name)
            self._wait_for_localstack()
            return

        container_name = f"localstack-{uuid.uuid4().hex[:8]}"

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", self.network_name,
            "-v", "/var/run/docker.sock:/var/run/docker.sock",
            "-e", "SERVICES=s3,ec2,lambda,iam,dynamodb,rds,ecs,cloudfront,route53",
            "-e", "DEBUG=1",
            "-e", "LS_LOG=trace",
            "-e", "LAMBDA_EXECUTOR=docker",
            "-e", "DOCKER_HOST=unix:///var/run/docker.sock",
            "-p", "4566:4566",
            self.localstack_image,
        ]

        self.logger.debug(f"Starting localstack: {shlex.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            check=True,
        )

        self.localstack_container_id = result.stdout.strip()
        self.localstack_container_name = container_name
        self.logger.info(f"Started localstack container: {self.localstack_container_id}")

        self._wait_for_localstack()

    def _find_running_localstack(self) -> Optional[tuple[str, str]]:
        """Find a running localstack container. Returns (container_id, container_name) or None."""
        result = subprocess.run(
            ["docker", "ps", "--filter", f"ancestor={self.localstack_image}",
             "--filter", "status=running", "--format", "{{.ID}}\t{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().split('\n')[0]
            parts = line.split('\t')
            if len(parts) == 2:
                return parts[0], parts[1]
        return None

    def _connect_to_network(self, container_id: str, network: str) -> None:
        """Connect container to network if not already connected."""
        result = subprocess.run(
            ["docker", "inspect", container_id,
             "--format", "{{range .NetworkSettings.Networks}}{{.NetworkID}}{{end}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if network in result.stdout:
            self.logger.debug(f"Container already connected to {network}")
            return

        result = subprocess.run(
            ["docker", "network", "connect", network, container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            self.logger.debug(f"Connected container to {network}")
        else:
            if "already exists" not in result.stderr:
                self.logger.warning(f"Failed to connect to network: {result.stderr}")

    def _wait_for_localstack(self) -> None:
        """Wait for localstack to be ready."""
        max_retries = 60

        self.logger.info("Waiting for Localstack to be ready...")

        for i in range(max_retries):
            try:
                result = subprocess.run(
                    [
                        "docker", "exec",
                        self.localstack_container_id,
                        "curl", "-s", "http://localhost:4566/_localstack/health"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    if "running" in result.stdout or "available" in result.stdout:
                        self.logger.info("Localstack is ready")
                        return
                    else:
                        self.logger.debug(f"Health check response: {result.stdout[:200]}")

            except subprocess.TimeoutExpired:
                self.logger.debug("Health check timed out")

            if i % 5 == 0:
                self.logger.info(f"Waiting for localstack... ({i+1}/{max_retries})")
            time.sleep(2)

        raise RuntimeError("Localstack failed to start within timeout")

    def execute_terraform_command(
        self,
        command: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Execute a terraform command in a Docker container."""
        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
            "TF_VAR_localstack": "true",
        }

        if env_vars:
            default_env.update(env_vars)

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "-v", f"{self.work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            "--entrypoint", "sh",
            self.image,
            "-c",
            command,
        ])

        self.logger.debug(f"Executing: {shlex.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )

            return {
                "output": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
                "command": command,
            }

        except subprocess.TimeoutExpired:
            return {
                "output": "",
                "stderr": f"Command timed out after {self.timeout}s",
                "returncode": -1,
                "success": False,
                "command": command,
                "error": "timeout",
            }
        except Exception as e:
            return {
                "output": "",
                "stderr": str(e),
                "returncode": -1,
                "success": False,
                "command": command,
                "error": str(e),
            }

    def execute_validation_script(
        self,
        script_path: str,
        region: str = "us-east-1",
    ) -> Dict[str, Any]:
        """Execute a validation script in a Python container."""
        script_path = Path(script_path)

        if not script_path.exists():
            return {
                "passed": False,
                "error": f"Validation script not found: {script_path}",
            }

        env_vars = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "-v", f"{script_path.parent.absolute()}:/validation",
            "-v", f"{self.work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])

        cmd.extend([
            "python:3.11-slim",
            "sh", "-c",
            f"pip install -q boto3 && python /validation/{script_path.name}",
        ])

        self.logger.debug(f"Running validation: {shlex.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            return {
                "passed": result.returncode == 0,
                "output": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }

        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
                "output": "",
            }

    def execute_setup_script(
        self,
        setup_script: str,
        region: str = "us-east-1",
    ) -> Dict[str, Any]:
        """Execute a setup script for pre-existing infrastructure in a Docker container."""
        setup_script_path = Path(setup_script)

        if not setup_script_path.exists():
            return {
                "success": False,
                "error": f"Setup script not found: {setup_script}",
            }

        # Copy setup script to working directory
        work_dir = self.work_dir
        setup_script_copy = work_dir / "setup.sh"
        shutil.copy(setup_script_path, setup_script_copy)

        # Copy lambda_code directory if it exists
        lambda_code_dir = setup_script_path.parent / "lambda_code"
        if lambda_code_dir.exists():
            dest_lambda_code_dir = work_dir / "lambda_code"
            if dest_lambda_code_dir.exists():
                shutil.rmtree(dest_lambda_code_dir)
            shutil.copytree(lambda_code_dir, dest_lambda_code_dir)

        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "-v", f"{work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        command = "apk add --no-cache aws-cli bash zip && chmod +x /workspace/setup.sh && /bin/bash /workspace/setup.sh"
        cmd.extend(["golang:alpine", "sh", "-c", command])

        self.logger.debug(f"Running setup script: {shlex.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )

            return {
                "success": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Setup script timed out after 5 minutes",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def execute_cleanup_script(
        self,
        cleanup_script: str,
        region: str = "us-east-1",
    ) -> Dict[str, Any]:
        """Execute a cleanup script in a Docker container."""
        cleanup_script_path = Path(cleanup_script)

        if not cleanup_script_path.exists():
            return {"success": False, "error": "Cleanup script not found"}

        work_dir = self.work_dir
        cleanup_script_copy = work_dir / "cleanup.sh"
        shutil.copy(cleanup_script_path, cleanup_script_copy)

        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "-v", f"{work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        command = "apk add --no-cache aws-cli bash && chmod +x /workspace/cleanup.sh && /bin/bash /workspace/cleanup.sh"
        cmd.extend(["alpine:latest", "sh", "-c", command])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cleanup(self) -> None:
        """Stop and remove all containers and network."""
        self.logger.info("Cleaning up docker resources...")

        if self.localstack_container_id:
            cmd = ["docker", "stop", self.localstack_container_id]
            subprocess.run(cmd, capture_output=True, timeout=60)

            cmd = ["docker", "rm", "-f", self.localstack_container_id]
            subprocess.run(cmd, capture_output=True, timeout=30)

        if self.network_name:
            cmd = ["docker", "network", "rm", self.network_name]
            subprocess.run(cmd, capture_output=True, timeout=30)

        self.logger.info("Cleanup complete")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass
