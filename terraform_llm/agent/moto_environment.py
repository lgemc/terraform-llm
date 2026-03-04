"""Docker environment for isolated Terraform execution with Moto."""

import logging
import shlex
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class MotoDockerEnvironment:
    """Executes terraform commands in a Docker container with Moto for AWS mocking."""

    def __init__(
        self,
        *,
        work_dir: str,
        image: str = "hashicorp/terraform:latest",
        moto_image: str = "motoserver/moto:latest",
        port: int = 5555,
        timeout: int = 600,
        logger: Optional[logging.Logger] = None,
    ):
        self.work_dir = Path(work_dir)
        self.image = image
        self.moto_image = moto_image
        self.port = port
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

        self.network_name = f"terraform-test-{uuid.uuid4().hex[:8]}"
        self.moto_container_id: Optional[str] = None
        self.moto_container_name: Optional[str] = None
        self.terraform_container_id: Optional[str] = None

        self._setup_network()
        self._start_moto()

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

    def _start_moto(self) -> None:
        """Start moto server container."""
        # Clean up ALL moto containers (including running ones) to ensure fresh start with correct env vars
        self._cleanup_all_moto_containers()

        container_name = f"moto-{uuid.uuid4().hex[:8]}"

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", self.network_name,
            "-p", f"{self.port}:5000",
            "-e", "MOTO_IAM_LOAD_MANAGED_POLICIES=true",
            self.moto_image,
        ]

        self.logger.debug(f"Starting moto: {shlex.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to start moto container: {result.stderr}\n"
                f"Command: {shlex.join(cmd)}\n"
                f"Stdout: {result.stdout}"
            )

        self.moto_container_id = result.stdout.strip()
        self.moto_container_name = container_name
        self.logger.info(f"Started moto container: {self.moto_container_id}")

        self._wait_for_moto()

    def _cleanup_all_moto_containers(self) -> None:
        """Remove all moto containers to ensure fresh start with correct environment variables."""
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"ancestor={self.moto_image}",
             "--format", "{{.ID}}"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0 and result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            for container_id in container_ids:
                self.logger.debug(f"Removing moto container: {container_id}")
                subprocess.run(
                    ["docker", "rm", "-f", container_id],
                    capture_output=True,
                    timeout=10,
                )

    def _connect_to_network(self, container_id: str, network: str) -> None:
        """Connect container to network if not already connected."""
        result = subprocess.run(
            ["docker", "inspect", container_id,
             "--format", "{{range .NetworkSettings.Networks}}{{.Name}}{{end}}"],
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

    def _verify_dns_resolution(self) -> None:
        """Verify that Moto container is resolvable via DNS on the network."""
        self.logger.info(f"Verifying DNS resolution for {self.moto_container_name}...")
        max_retries = 10

        for i in range(max_retries):
            try:
                # Use a lightweight alpine image to test DNS resolution
                result = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", self.network_name,
                        "alpine:latest",
                        "sh", "-c", f"nslookup {self.moto_container_name} || getent hosts {self.moto_container_name}"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    self.logger.info(f"DNS resolution successful for {self.moto_container_name}")
                    return
            except Exception as e:
                self.logger.debug(f"DNS check attempt {i+1} failed: {e}")

            time.sleep(1)

        raise RuntimeError(f"DNS verification failed after {max_retries} attempts - Moto container not resolvable on network {self.network_name}")

    def _wait_for_moto(self) -> None:
        """Wait for moto to be ready by checking if its port is accepting connections."""
        max_retries = 30

        self.logger.info("Waiting for Moto to be ready...")

        for i in range(max_retries):
            try:
                # Try to connect to moto server using a simple HTTP request
                result = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", self.network_name,
                        "alpine:latest",
                        "sh", "-c",
                        f"wget -q -O- --timeout=2 http://{self.moto_container_name}:5000/ || exit 0"
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                # Moto server is ready if we can connect (any response is fine)
                if result.returncode == 0:
                    self.logger.info("Moto is ready")
                    return

            except subprocess.TimeoutExpired:
                self.logger.debug("Moto check timed out")

            if i % 5 == 0:
                self.logger.info(f"Waiting for moto... ({i+1}/{max_retries})")
            time.sleep(2)

        raise RuntimeError("Moto failed to start within timeout")

    def execute_terraform_command(
        self,
        command: str,
        env_vars: Optional[Dict[str, str]] = None,
        work_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute a terraform command in a Docker container."""
        # Use provided work_dir or fall back to instance work_dir
        effective_work_dir = work_dir if work_dir is not None else self.work_dir

        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": "us-east-1",
            "AWS_ENDPOINT_URL": f"http://{self.moto_container_name}:5000",
            "AWS_S3_USE_PATH_STYLE": "true",
            "TF_VAR_moto": "true",
        }

        if env_vars:
            default_env.update(env_vars)

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "--mount", f"type=bind,source={str(effective_work_dir.absolute())},target=/workspace",
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
        work_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute a validation script in a Python container."""
        script_path = Path(script_path)
        effective_work_dir = work_dir if work_dir is not None else self.work_dir

        if not script_path.exists():
            return {
                "passed": False,
                "error": f"Validation script not found: {script_path}",
            }

        env_vars = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.moto_container_name}:5000",
            "AWS_S3_USE_PATH_STYLE": "true",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "--mount", f"type=bind,source={str(script_path.parent.absolute())},target=/validation,readonly",
            "--mount", f"type=bind,source={str(effective_work_dir.absolute())},target=/workspace",
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
        work_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute a setup script for pre-existing infrastructure in a Docker container."""
        setup_script_path = Path(setup_script)
        effective_work_dir = work_dir if work_dir is not None else self.work_dir

        if not setup_script_path.exists():
            return {
                "success": False,
                "error": f"Setup script not found: {setup_script}",
            }

        # Copy setup script to working directory
        setup_script_copy = effective_work_dir / "setup.sh"
        shutil.copy(setup_script_path, setup_script_copy)

        # Copy lambda_code directory if it exists
        lambda_code_dir = setup_script_path.parent / "lambda_code"
        if lambda_code_dir.exists():
            dest_lambda_code_dir = effective_work_dir / "lambda_code"
            if dest_lambda_code_dir.exists():
                shutil.rmtree(dest_lambda_code_dir)
            shutil.copytree(lambda_code_dir, dest_lambda_code_dir)

        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.moto_container_name}:5000",
            "AWS_S3_USE_PATH_STYLE": "true",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "--mount", f"type=bind,source={str(effective_work_dir.absolute())},target=/workspace",
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
        work_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Execute a cleanup script in a Docker container."""
        cleanup_script_path = Path(cleanup_script)
        effective_work_dir = work_dir if work_dir is not None else self.work_dir

        if not cleanup_script_path.exists():
            return {"success": False, "error": "Cleanup script not found"}

        cleanup_script_copy = effective_work_dir / "cleanup.sh"
        shutil.copy(cleanup_script_path, cleanup_script_copy)

        default_env = {
            "AWS_ACCESS_KEY_ID": "test",
            "AWS_SECRET_ACCESS_KEY": "test",
            "AWS_DEFAULT_REGION": region,
            "AWS_ENDPOINT_URL": f"http://{self.moto_container_name}:5000",
            "AWS_S3_USE_PATH_STYLE": "true",
        }

        cmd = [
            "docker", "run", "--rm",
            "--network", self.network_name,
            "--mount", f"type=bind,source={str(effective_work_dir.absolute())},target=/workspace",
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

        if self.moto_container_id:
            cmd = ["docker", "stop", self.moto_container_id]
            subprocess.run(cmd, capture_output=True, timeout=60)

            cmd = ["docker", "rm", "-f", self.moto_container_id]
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
