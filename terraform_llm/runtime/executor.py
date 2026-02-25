"""High-level execution orchestration for benchmark instances."""

import shutil
from pathlib import Path
from typing import Dict, Any, Optional
import importlib.util

from terraform_llm.runtime.terraform import TerraformRuntime, create_terraform_files


class BenchmarkExecutor:
    """Executes a complete benchmark instance: generation, deployment, validation."""

    def __init__(self, output_dir: str):
        """
        Initialize benchmark executor.

        Args:
            output_dir: Base directory for outputs
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def execute_instance(
        self,
        instance_id: str,
        terraform_code: Dict[str, str],
        validation_script: str,
        region: str,
        expected_resources: Dict[str, int],
        cleanup: bool = True
    ) -> Dict[str, Any]:
        """
        Execute a complete benchmark instance.

        Args:
            instance_id: Instance identifier
            terraform_code: Dictionary with terraform files (main.tf, etc.)
            validation_script: Path to validation test script
            region: AWS region for validation
            expected_resources: Expected resource counts
            cleanup: Whether to destroy infrastructure after validation

        Returns:
            Dictionary with execution results
        """
        instance_dir = self.output_dir / instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)

        results = {
            'instance_id': instance_id,
            'terraform': {},
            'validation': {},
            'passed': False
        }

        try:
            # Create Terraform files
            self._create_terraform_files(instance_dir, terraform_code)

            # Execute Terraform workflow
            tf_results = self._run_terraform_workflow(instance_dir, expected_resources)
            results['terraform'] = tf_results

            # If Terraform succeeded, run validation
            if tf_results.get('success', False):
                validation_results = self._run_validation(
                    validation_script,
                    region,
                    instance_dir
                )
                results['validation'] = validation_results
                results['passed'] = validation_results.get('passed', False)

        except Exception as e:
            results['error'] = str(e)

        finally:
            # Cleanup if requested
            if cleanup:
                cleanup_results = self._cleanup(instance_dir)
                results['cleanup'] = cleanup_results

        return results

    def _create_terraform_files(
        self,
        work_dir: Path,
        terraform_code: Dict[str, str]
    ) -> None:
        """Create Terraform files from code dictionary."""
        create_terraform_files(
            working_dir=str(work_dir),
            terraform_code=terraform_code
        )

    def _run_terraform_workflow(
        self,
        work_dir: Path,
        expected_resources: Dict[str, int]
    ) -> Dict[str, Any]:
        """Run complete Terraform workflow: init, plan, apply."""
        runtime = TerraformRuntime(str(work_dir))
        results = {}

        # Init
        init_result = runtime.init()
        results['init'] = init_result

        if not init_result['success']:
            results['success'] = False
            results['stage'] = 'init'
            return results

        # Validate
        validate_result = runtime.validate()
        results['validate'] = validate_result

        if not validate_result['success']:
            results['success'] = False
            results['stage'] = 'validate'
            return results

        # Plan
        plan_result = runtime.plan()
        results['plan'] = plan_result

        if not plan_result['success']:
            results['success'] = False
            results['stage'] = 'plan'
            return results

        # Apply
        apply_result = runtime.apply()
        results['apply'] = apply_result

        if not apply_result['success']:
            results['success'] = False
            results['stage'] = 'apply'
            return results

        # Get outputs
        output_result = runtime.output()
        results['outputs'] = output_result.get('outputs', {})

        # Count resources
        resource_counts = runtime.count_resources_by_type()
        results['resource_counts'] = resource_counts

        # Validate resource counts
        results['resource_validation'] = self._validate_resources(
            resource_counts,
            expected_resources
        )

        results['success'] = True
        results['stage'] = 'completed'

        return results

    def _validate_resources(
        self,
        actual: Dict[str, int],
        expected: Dict[str, int]
    ) -> Dict[str, Any]:
        """Validate actual resources match expected."""
        validation = {
            'passed': True,
            'mismatches': []
        }

        for resource_type, expected_count in expected.items():
            actual_count = actual.get(resource_type, 0)

            if actual_count != expected_count:
                validation['passed'] = False
                validation['mismatches'].append({
                    'resource_type': resource_type,
                    'expected': expected_count,
                    'actual': actual_count
                })

        # Check for unexpected resources
        for resource_type, actual_count in actual.items():
            if resource_type not in expected and actual_count > 0:
                validation['mismatches'].append({
                    'resource_type': resource_type,
                    'expected': 0,
                    'actual': actual_count,
                    'note': 'unexpected resource type'
                })

        return validation

    def _run_validation(
        self,
        validation_script: str,
        region: str,
        work_dir: Path
    ) -> Dict[str, Any]:
        """Run boto3 validation tests."""
        try:
            # Dynamically import validation module
            spec = importlib.util.spec_from_file_location(
                "validation_module",
                validation_script
            )

            if spec is None or spec.loader is None:
                return {
                    'passed': False,
                    'error': f'Could not load validation script: {validation_script}'
                }

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find test class
            test_class = None
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and name.startswith('Test'):
                    test_class = obj
                    break

            if test_class is None:
                return {
                    'passed': False,
                    'error': 'No test class found in validation script'
                }

            # Run validation
            tester = test_class(region=region)
            results = tester.validate()

            return results

        except Exception as e:
            return {
                'passed': False,
                'error': str(e)
            }

    def _cleanup(self, work_dir: Path) -> Dict[str, Any]:
        """Destroy Terraform infrastructure and optionally remove directory."""
        runtime = TerraformRuntime(str(work_dir))

        # Try to destroy infrastructure
        destroy_result = runtime.destroy()

        return {
            'destroyed': destroy_result['success'],
            'destroy_output': destroy_result
        }

    def cleanup_directory(self, instance_id: str) -> None:
        """Remove instance directory completely."""
        instance_dir = self.output_dir / instance_id
        if instance_dir.exists():
            shutil.rmtree(instance_dir)
