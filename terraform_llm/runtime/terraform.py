"""Terraform execution and management."""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
import json


class TerraformRuntime:
    """Manages Terraform lifecycle operations."""

    def __init__(self, working_dir: str):
        """
        Initialize Terraform runtime.

        Args:
            working_dir: Directory containing Terraform configuration
        """
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)

    def init(self, backend_config: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Run terraform init.

        Args:
            backend_config: Optional backend configuration

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        cmd = ['terraform', 'init']

        if backend_config:
            for key, value in backend_config.items():
                cmd.extend(['-backend-config', f'{key}={value}'])

        return self._run_command(cmd)

    def plan(self, out_file: str = 'tfplan', var_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Run terraform plan.

        Args:
            out_file: Output plan file name
            var_file: Optional variables file

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        cmd = ['terraform', 'plan', f'-out={out_file}']

        if var_file:
            cmd.extend(['-var-file', var_file])

        return self._run_command(cmd)

    def apply(self, plan_file: str = 'tfplan', auto_approve: bool = True) -> Dict[str, Any]:
        """
        Run terraform apply.

        Args:
            plan_file: Plan file to apply
            auto_approve: Whether to auto-approve changes

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        if auto_approve and plan_file:
            cmd = ['terraform', 'apply', '-auto-approve', plan_file]
        elif auto_approve:
            cmd = ['terraform', 'apply', '-auto-approve']
        else:
            cmd = ['terraform', 'apply', plan_file] if plan_file else ['terraform', 'apply']

        return self._run_command(cmd)

    def destroy(self, auto_approve: bool = True) -> Dict[str, Any]:
        """
        Run terraform destroy.

        Args:
            auto_approve: Whether to auto-approve destruction

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        cmd = ['terraform', 'destroy']
        if auto_approve:
            cmd.append('-auto-approve')

        return self._run_command(cmd)

    def output(self, output_name: Optional[str] = None, json_format: bool = True) -> Dict[str, Any]:
        """
        Get terraform outputs.

        Args:
            output_name: Specific output to retrieve (None for all)
            json_format: Return as JSON

        Returns:
            Result dictionary with returncode, stdout, stderr, and parsed outputs
        """
        cmd = ['terraform', 'output']

        if json_format:
            cmd.append('-json')

        if output_name:
            cmd.append(output_name)

        result = self._run_command(cmd)

        # Parse JSON output if successful
        if result['returncode'] == 0 and json_format:
            try:
                result['outputs'] = json.loads(result['stdout'])
            except json.JSONDecodeError:
                result['outputs'] = {}

        return result

    def validate(self) -> Dict[str, Any]:
        """
        Run terraform validate.

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        return self._run_command(['terraform', 'validate', '-json'])

    def show(self, plan_file: Optional[str] = None) -> Dict[str, Any]:
        """
        Run terraform show.

        Args:
            plan_file: Optional plan file to show

        Returns:
            Result dictionary with returncode, stdout, stderr
        """
        cmd = ['terraform', 'show', '-json']
        if plan_file:
            cmd.append(plan_file)

        return self._run_command(cmd)

    def get_state(self) -> Dict[str, Any]:
        """
        Get current Terraform state.

        Returns:
            Parsed state as dictionary
        """
        result = self._run_command(['terraform', 'show', '-json'])

        if result['returncode'] == 0:
            try:
                return json.loads(result['stdout'])
            except json.JSONDecodeError:
                return {}
        return {}

    def get_resources(self) -> List[Dict[str, Any]]:
        """
        Get list of resources from state.

        Returns:
            List of resource dictionaries
        """
        state = self.get_state()
        return state.get('values', {}).get('root_module', {}).get('resources', [])

    def count_resources_by_type(self) -> Dict[str, int]:
        """
        Count resources by type from state.

        Returns:
            Dictionary mapping resource types to counts
        """
        resources = self.get_resources()
        counts: Dict[str, int] = {}

        for resource in resources:
            resource_type = resource.get('type', 'unknown')
            counts[resource_type] = counts.get(resource_type, 0) + 1

        return counts

    def _run_command(self, cmd: List[str], timeout: int = 600) -> Dict[str, Any]:
        """
        Run a terraform command.

        Args:
            cmd: Command and arguments
            timeout: Command timeout in seconds

        Returns:
            Dictionary with returncode, stdout, stderr
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'success': result.returncode == 0
            }

        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': f'Command timed out after {timeout} seconds',
                'success': False
            }
        except Exception as e:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': str(e),
                'success': False
            }


def create_terraform_files(
    working_dir: str,
    terraform_code: Dict[str, str]
) -> None:
    """
    Create Terraform configuration files.

    Args:
        working_dir: Directory to create files in
        terraform_code: Dictionary mapping filenames to content
    """
    work_dir = Path(working_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in terraform_code.items():
        if content:
            (work_dir / filename).write_text(content)
