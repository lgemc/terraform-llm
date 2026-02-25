"""Docker environment for isolated Terraform execution with Localstack."""

import logging
import os
import shlex
import subprocess
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
        """
        Initialize docker environment with localstack.

        Args:
            work_dir: Host directory to mount as working directory
            image: Terraform docker image
            localstack_image: Localstack docker image
            timeout: Command execution timeout in seconds
            logger: Optional logger instance
        """
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
        # Check if there's already a running localstack container
        existing = self._find_running_localstack()

        if existing:
            self.localstack_container_id, self.localstack_container_name = existing
            self.logger.info(f"Reusing existing localstack container: {self.localstack_container_id} ({self.localstack_container_name})")

            # Connect it to our network if not already connected
            self._connect_to_network(self.localstack_container_id, self.network_name)

            # Verify it's healthy
            self._wait_for_localstack()
            return

        # Start new container
        container_name = f"localstack-{uuid.uuid4().hex[:8]}"

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", self.network_name,
            "-e", "SERVICES=s3,ec2,lambda,iam,dynamodb,rds,ecs,cloudfront,route53",
            "-e", "DEBUG=1",
            "-e", "LS_LOG=trace",
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

        # Wait for localstack to be ready
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
            line = result.stdout.strip().split('\n')[0]  # Get first running container
            parts = line.split('\t')
            if len(parts) == 2:
                return parts[0], parts[1]
        return None

    def _connect_to_network(self, container_id: str, network: str) -> None:
        """Connect container to network if not already connected."""
        # Check if already connected
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

        # Connect to network
        result = subprocess.run(
            ["docker", "network", "connect", network, container_id],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            self.logger.debug(f"Connected container to {network}")
        else:
            # Ignore error if already connected (race condition)
            if "already exists" not in result.stderr:
                self.logger.warning(f"Failed to connect to network: {result.stderr}")

    def _wait_for_localstack(self) -> None:
        """Wait for localstack to be ready."""
        import time
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
                    # Check for "running" or "available" in response
                    if "running" in result.stdout or "available" in result.stdout:
                        self.logger.info("Localstack is ready")
                        return
                    else:
                        self.logger.debug(f"Health check response: {result.stdout[:200]}")

            except subprocess.TimeoutExpired:
                self.logger.debug(f"Health check timed out")

            if i % 5 == 0:  # Log every 10 seconds
                self.logger.info(f"Waiting for localstack... ({i+1}/{max_retries})")
            time.sleep(2)

        raise RuntimeError("Localstack failed to start within timeout")

    def execute_terraform_command(
        self,
        command: str,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a terraform command in the docker container.

        Args:
            command: Terraform command to execute (e.g., "init", "plan", "apply")
            env_vars: Additional environment variables

        Returns:
            Dictionary with output, returncode, and success status
        """
        # Configure AWS to use localstack
        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
            # Terraform-specific localstack endpoints
            "TF_VAR_localstack": "true",
        }

        if env_vars:
            default_env.update(env_vars)

        # Build docker exec command
        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "-v", f"{self.work_dir.absolute()}:/workspace",
            "-w", "/workspace",
        ]

        # Add environment variables
        for key, value in default_env.items():
            cmd.extend(["-e", f"{key}={value}"])

        # Override entrypoint to use sh for executing commands
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

        except subprocess.TimeoutExpired as e:
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
        """
        Execute a validation script in a Python container.

        Args:
            script_path: Path to validation script on host
            region: AWS region

        Returns:
            Dictionary with validation results
        """
        script_path = Path(script_path)

        if not script_path.exists():
            return {
                "passed": False,
                "error": f"Validation script not found: {script_path}",
            }

        # Environment for boto3 to use localstack
        env_vars = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.localstack_container_name}:4566",
        }

        # Build command to run validation script
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

    def cleanup(self) -> None:
        """Stop and remove all containers and network."""
        self.logger.info("Cleaning up docker resources...")

        # Stop localstack
        if self.localstack_container_id:
            cmd = ["docker", "stop", self.localstack_container_id]
            subprocess.run(cmd, capture_output=True, timeout=60)

            cmd = ["docker", "rm", "-f", self.localstack_container_id]
            subprocess.run(cmd, capture_output=True, timeout=30)

        # Remove network
        if self.network_name:
            cmd = ["docker", "network", "rm", self.network_name]
            subprocess.run(cmd, capture_output=True, timeout=30)

        self.logger.info("Cleanup complete")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.cleanup()
        return False

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.cleanup()
        except Exception:
            pass
