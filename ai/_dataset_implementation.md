# Terraform Agent Benchmark Dataset Implementation

## Overview

This document defines the dataset structure for benchmarking a Terraform agent, inspired by SWE-bench. The dataset validates that an AI agent can correctly generate Terraform infrastructure code based on natural language requirements, with validation performed using AWS boto3 to check actual deployed resources.

## Dataset Schema

### Core Structure

Each instance in the dataset follows this schema:

```json
{
  "instance_id": "terraform-aws-lambda-vpc-001",
  "problem_statement": "Create AWS Terraform infrastructure to deploy a Lambda function written in Golang into a VPC with proper networking configuration",
  "difficulty": "easy|medium|hard",
  "tags": ["aws", "lambda", "vpc", "golang"],

  "provider": "aws",
  "region": "us-east-1",

  "expected_resources": {
    "aws_vpc": 1,
    "aws_subnet": 2,
    "aws_lambda_function": 1,
    "aws_iam_role": 1,
    "aws_iam_role_policy_attachment": 1,
    "aws_security_group": 1
  },

  "required_outputs": [
    "lambda_function_arn",
    "vpc_id",
    "lambda_function_name"
  ],

  "validation_script": "validation_tests/lambda_vpc_test.py",

  "gold_solution": {
    "main.tf": "# Optional reference solution",
    "variables.tf": "# Optional",
    "outputs.tf": "# Optional"
  },

  "hints": [
    "Lambda functions in VPC require VPCAccessExecutionRole",
    "Subnets should be in different availability zones for HA"
  ],

  "metadata": {
    "estimated_cost": "< $1/month",
    "deployment_time_seconds": 300,
    "cleanup_required": true,
    "created_at": "2026-02-24",
    "author": "terraform-bench"
  }
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `instance_id` | string | Yes | Unique identifier (format: `terraform-{provider}-{service}-{number}`) |
| `problem_statement` | string | Yes | Natural language description of infrastructure requirements |
| `difficulty` | string | Yes | One of: `easy`, `medium`, `hard` |
| `tags` | array[string] | Yes | Searchable tags for categorization |
| `provider` | string | Yes | Cloud provider (e.g., `aws`, `azure`, `gcp`) |
| `region` | string | Yes | Default region for deployment |
| `expected_resources` | object | Yes | Map of Terraform resource types to expected counts |
| `required_outputs` | array[string] | No | Terraform outputs that must be defined |
| `validation_script` | string | Yes | Path to boto3 validation test script |
| `gold_solution` | object | No | Reference solution files (for analysis, not shown to agent) |
| `hints` | array[string] | No | Optional hints about best practices |
| `metadata` | object | Yes | Additional metadata for tracking |

## Dataset File Format

Store dataset as **JSONL** (JSON Lines) format for easy streaming and incremental loading:

```jsonl
{"instance_id": "terraform-aws-lambda-vpc-001", "problem_statement": "Create AWS Terraform infrastructure to deploy a Lambda function written in Golang into a VPC", "difficulty": "medium", ...}
{"instance_id": "terraform-aws-s3-cloudfront-002", "problem_statement": "Set up an S3 bucket with CloudFront distribution for static website hosting", "difficulty": "easy", ...}
{"instance_id": "terraform-aws-eks-cluster-003", "problem_statement": "Deploy a production-ready EKS cluster with managed node groups", "difficulty": "hard", ...}
```

## Validation Test Structure

### Base Test Class

```python
# validation_tests/base_test.py
import boto3
import pytest
from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseTerraformTest(ABC):
    """Base class for all Terraform infrastructure validation tests"""

    def __init__(self, region: str = 'us-east-1', tags: Dict[str, str] = None):
        self.region = region
        self.tags = tags or {}
        self.setup_clients()

    def setup_clients(self):
        """Initialize boto3 clients"""
        self.ec2 = boto3.client('ec2', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.iam = boto3.client('iam', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        self.cloudfront = boto3.client('cloudfront', region_name=self.region)
        self.eks = boto3.client('eks', region_name=self.region)

    def find_resource_by_tags(self, resource_type: str, filters: List[Dict] = None) -> List[Dict]:
        """Generic method to find resources by tags"""
        base_filters = [
            {'Name': f'tag:{k}', 'Values': [v]}
            for k, v in self.tags.items()
        ]
        if filters:
            base_filters.extend(filters)

        # Route to appropriate describe method based on resource type
        if resource_type == 'vpc':
            return self.ec2.describe_vpcs(Filters=base_filters)['Vpcs']
        elif resource_type == 'subnet':
            return self.ec2.describe_subnets(Filters=base_filters)['Subnets']
        elif resource_type == 'security_group':
            return self.ec2.describe_security_groups(Filters=base_filters)['SecurityGroups']
        # Add more resource types as needed

    @abstractmethod
    def validate(self) -> Dict[str, Any]:
        """Run all validation checks and return results"""
        pass
```

### Example: Lambda + VPC Validation Test

```python
# validation_tests/lambda_vpc_test.py
import boto3
import pytest
from typing import Dict, Any
from .base_test import BaseTerraformTest

class TestLambdaVPCInfrastructure(BaseTerraformTest):
    """Validate Lambda function deployed in VPC"""

    def validate(self) -> Dict[str, Any]:
        """Run all validation checks"""
        results = {
            'passed': True,
            'tests': {},
            'errors': []
        }

        try:
            results['tests']['vpc_exists'] = self.test_vpc_exists()
            results['tests']['subnets_exist'] = self.test_subnets_exist()
            results['tests']['lambda_exists'] = self.test_lambda_exists()
            results['tests']['lambda_in_vpc'] = self.test_lambda_in_vpc()
            results['tests']['lambda_iam_role'] = self.test_lambda_has_proper_iam_role()
            results['tests']['security_group'] = self.test_security_group_exists()

            # Overall pass/fail
            results['passed'] = all(results['tests'].values())

        except Exception as e:
            results['passed'] = False
            results['errors'].append(str(e))

        return results

    def test_vpc_exists(self) -> bool:
        """Check that VPC was created"""
        vpcs = self.find_resource_by_tags('vpc')
        assert len(vpcs) >= 1, "VPC not found"

        # Validate VPC has DNS support enabled (required for Lambda)
        vpc = vpcs[0]
        vpc_id = vpc['VpcId']

        dns_support = self.ec2.describe_vpc_attribute(
            VpcId=vpc_id,
            Attribute='enableDnsSupport'
        )
        dns_hostnames = self.ec2.describe_vpc_attribute(
            VpcId=vpc_id,
            Attribute='enableDnsHostnames'
        )

        assert dns_support['EnableDnsSupport']['Value'], "DNS support must be enabled"
        assert dns_hostnames['EnableDnsHostnames']['Value'], "DNS hostnames must be enabled"

        return True

    def test_subnets_exist(self) -> bool:
        """Check that subnets exist in VPC"""
        subnets = self.find_resource_by_tags('subnet')
        assert len(subnets) >= 2, "At least 2 subnets required for HA"

        # Check subnets are in different AZs
        azs = set(subnet['AvailabilityZone'] for subnet in subnets)
        assert len(azs) >= 2, "Subnets should be in different availability zones"

        return True

    def test_lambda_exists(self) -> bool:
        """Check Lambda function exists"""
        target_function = self._find_lambda_function()
        assert target_function is not None, "Lambda function not found"

        # Check runtime is Go
        assert target_function['Runtime'].startswith('go'), \
            f"Expected Go runtime, got {target_function['Runtime']}"

        return True

    def test_lambda_in_vpc(self) -> bool:
        """Check Lambda is deployed in VPC"""
        target_function = self._find_lambda_function()
        assert 'VpcConfig' in target_function, "Lambda not configured with VPC"

        vpc_config = target_function['VpcConfig']
        assert vpc_config['VpcId'], "Lambda VPC ID is empty"
        assert len(vpc_config['SubnetIds']) >= 1, "No subnets configured"
        assert len(vpc_config['SecurityGroupIds']) >= 1, "No security groups configured"

        return True

    def test_lambda_has_proper_iam_role(self) -> bool:
        """Check Lambda has IAM role with VPC execution permissions"""
        target_function = self._find_lambda_function()
        role_arn = target_function['Role']
        role_name = role_arn.split('/')[-1]

        # Get attached policies
        attached_policies = self.iam.list_attached_role_policies(RoleName=role_name)
        policy_arns = [p['PolicyArn'] for p in attached_policies['AttachedPolicies']]

        # Check for VPC execution policy (managed policy)
        vpc_execution_policy = 'arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole'
        assert vpc_execution_policy in policy_arns, \
            "Missing AWSLambdaVPCAccessExecutionRole policy"

        return True

    def test_security_group_exists(self) -> bool:
        """Check security group is created and attached"""
        target_function = self._find_lambda_function()
        sg_ids = target_function['VpcConfig']['SecurityGroupIds']

        sgs = self.ec2.describe_security_groups(GroupIds=sg_ids)
        assert len(sgs['SecurityGroups']) >= 1, "Security group not found"

        return True

    def _find_lambda_function(self) -> Dict[str, Any]:
        """Helper to find the Lambda function"""
        functions = self.lambda_client.list_functions()

        # Try to find by tags (if supported) or name patterns
        for func in functions['Functions']:
            func_name = func['FunctionName']
            # Match common patterns
            if any(keyword in func_name.lower() for keyword in ['golang', 'go-lambda', 'vpc']):
                return func

        return None
```

### Example: S3 + CloudFront Test

```python
# validation_tests/s3_cloudfront_test.py
from typing import Dict, Any
from .base_test import BaseTerraformTest

class TestS3CloudFrontInfrastructure(BaseTerraformTest):
    """Validate S3 bucket with CloudFront distribution"""

    def validate(self) -> Dict[str, Any]:
        results = {
            'passed': True,
            'tests': {},
            'errors': []
        }

        try:
            results['tests']['s3_bucket_exists'] = self.test_s3_bucket_exists()
            results['tests']['bucket_configured_for_static'] = self.test_bucket_static_hosting()
            results['tests']['cloudfront_distribution'] = self.test_cloudfront_distribution()
            results['tests']['cloudfront_points_to_s3'] = self.test_cloudfront_origin()

            results['passed'] = all(results['tests'].values())

        except Exception as e:
            results['passed'] = False
            results['errors'].append(str(e))

        return results

    def test_s3_bucket_exists(self) -> bool:
        """Check S3 bucket exists"""
        # Implementation
        return True

    def test_bucket_static_hosting(self) -> bool:
        """Check bucket is configured for static website hosting"""
        # Implementation
        return True

    def test_cloudfront_distribution(self) -> bool:
        """Check CloudFront distribution exists and is enabled"""
        # Implementation
        return True

    def test_cloudfront_origin(self) -> bool:
        """Check CloudFront origin points to S3 bucket"""
        # Implementation
        return True
```

## Dataset Loader Implementation

```python
# dataset_loader.py
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List
import importlib.util

class TerraformBenchmarkRunner:
    """Runs Terraform agent on benchmark dataset and validates results"""

    def __init__(self, dataset_path: str, agent_command: str, output_dir: str):
        self.dataset_path = Path(dataset_path)
        self.agent_command = agent_command
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_dataset(self) -> List[Dict[str, Any]]:
        """Load JSONL dataset"""
        instances = []
        with open(self.dataset_path, 'r') as f:
            for line in f:
                if line.strip():
                    instances.append(json.loads(line))
        return instances

    def run_instance(self, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Run agent on single instance and validate"""
        instance_id = instance['instance_id']
        print(f"Processing {instance_id}...")

        # Create temp directory for this instance
        instance_dir = self.output_dir / instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)

        # Run the agent to generate Terraform code
        agent_result = self._run_agent(instance, instance_dir)

        # Apply Terraform
        terraform_result = self._apply_terraform(instance_dir, instance)

        # Run validation tests
        validation_result = self._run_validation(instance, instance_dir)

        # Cleanup (destroy infrastructure)
        if instance['metadata'].get('cleanup_required', True):
            self._cleanup_terraform(instance_dir)

        return {
            'instance_id': instance_id,
            'agent_result': agent_result,
            'terraform_result': terraform_result,
            'validation_result': validation_result,
            'passed': validation_result.get('passed', False)
        }

    def _run_agent(self, instance: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        """Execute AI agent to generate Terraform code"""
        # This would call your mini-swe-agent or similar
        # For now, placeholder
        problem_statement = instance['problem_statement']

        # Example: call mini agent
        cmd = f"{self.agent_command} --task '{problem_statement}' --output {work_dir}"

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True
        )

        return {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }

    def _apply_terraform(self, work_dir: Path, instance: Dict[str, Any]) -> Dict[str, Any]:
        """Run terraform init, plan, and apply"""
        results = {}

        # Init
        init_result = subprocess.run(
            ['terraform', 'init'],
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        results['init'] = {'returncode': init_result.returncode}

        if init_result.returncode != 0:
            results['init']['error'] = init_result.stderr
            return results

        # Plan
        plan_result = subprocess.run(
            ['terraform', 'plan', '-out=tfplan'],
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        results['plan'] = {'returncode': plan_result.returncode}

        if plan_result.returncode != 0:
            results['plan']['error'] = plan_result.stderr
            return results

        # Apply
        apply_result = subprocess.run(
            ['terraform', 'apply', '-auto-approve', 'tfplan'],
            cwd=work_dir,
            capture_output=True,
            text=True
        )
        results['apply'] = {
            'returncode': apply_result.returncode,
            'stdout': apply_result.stdout
        }

        if apply_result.returncode != 0:
            results['apply']['error'] = apply_result.stderr

        return results

    def _run_validation(self, instance: Dict[str, Any], work_dir: Path) -> Dict[str, Any]:
        """Run boto3 validation tests"""
        validation_script = instance['validation_script']

        # Dynamically import the test class
        spec = importlib.util.spec_from_file_location("validation_module", validation_script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Assume test class follows naming convention
        test_class_name = ''.join(
            word.capitalize()
            for word in instance['instance_id'].replace('-', '_').split('_')
        )
        test_class = getattr(module, f"Test{test_class_name}", None)

        if test_class is None:
            # Try to find any class that inherits from BaseTerraformTest
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and name.startswith('Test'):
                    test_class = obj
                    break

        # Instantiate and run validation
        tester = test_class(region=instance['region'])
        results = tester.validate()

        return results

    def _cleanup_terraform(self, work_dir: Path) -> Dict[str, Any]:
        """Destroy Terraform infrastructure"""
        destroy_result = subprocess.run(
            ['terraform', 'destroy', '-auto-approve'],
            cwd=work_dir,
            capture_output=True,
            text=True
        )

        return {
            'returncode': destroy_result.returncode,
            'stdout': destroy_result.stdout,
            'stderr': destroy_result.stderr
        }

    def run_benchmark(self) -> Dict[str, Any]:
        """Run complete benchmark on all instances"""
        instances = self.load_dataset()
        results = []

        for instance in instances:
            result = self.run_instance(instance)
            results.append(result)

        # Calculate metrics
        total = len(results)
        passed = sum(1 for r in results if r['passed'])

        summary = {
            'total_instances': total,
            'passed': passed,
            'failed': total - passed,
            'pass_rate': passed / total if total > 0 else 0,
            'results': results
        }

        # Save results
        with open(self.output_dir / 'benchmark_results.json', 'w') as f:
            json.dump(summary, f, indent=2)

        return summary
```

## Example Dataset Instances

### 1. Lambda + VPC (Medium Difficulty)

```json
{
  "instance_id": "terraform-aws-lambda-vpc-001",
  "problem_statement": "Create AWS Terraform infrastructure to deploy a Lambda function written in Golang into a VPC. The Lambda should be accessible from private subnets and have proper IAM permissions for VPC networking.",
  "difficulty": "medium",
  "tags": ["aws", "lambda", "vpc", "golang", "networking"],
  "provider": "aws",
  "region": "us-east-1",
  "expected_resources": {
    "aws_vpc": 1,
    "aws_subnet": 2,
    "aws_lambda_function": 1,
    "aws_iam_role": 1,
    "aws_iam_role_policy_attachment": 1,
    "aws_security_group": 1
  },
  "required_outputs": ["lambda_function_arn", "vpc_id"],
  "validation_script": "validation_tests/lambda_vpc_test.py",
  "hints": [
    "Lambda in VPC requires AWSLambdaVPCAccessExecutionRole",
    "Enable DNS support and DNS hostnames in VPC"
  ],
  "metadata": {
    "estimated_cost": "< $1/month",
    "deployment_time_seconds": 180,
    "cleanup_required": true
  }
}
```

### 2. S3 + CloudFront (Easy Difficulty)

```json
{
  "instance_id": "terraform-aws-s3-cloudfront-002",
  "problem_statement": "Set up an S3 bucket configured for static website hosting with a CloudFront distribution in front of it for global content delivery.",
  "difficulty": "easy",
  "tags": ["aws", "s3", "cloudfront", "cdn", "static-website"],
  "provider": "aws",
  "region": "us-east-1",
  "expected_resources": {
    "aws_s3_bucket": 1,
    "aws_s3_bucket_website_configuration": 1,
    "aws_cloudfront_distribution": 1,
    "aws_s3_bucket_policy": 1
  },
  "required_outputs": ["cloudfront_domain_name", "s3_bucket_name"],
  "validation_script": "validation_tests/s3_cloudfront_test.py",
  "metadata": {
    "estimated_cost": "< $0.50/month",
    "deployment_time_seconds": 120,
    "cleanup_required": true
  }
}
```

### 3. EKS Cluster (Hard Difficulty)

```json
{
  "instance_id": "terraform-aws-eks-cluster-003",
  "problem_statement": "Deploy a production-ready EKS cluster with managed node groups, proper IAM roles, VPC with public and private subnets across multiple availability zones, and cluster autoscaling enabled.",
  "difficulty": "hard",
  "tags": ["aws", "eks", "kubernetes", "vpc", "autoscaling"],
  "provider": "aws",
  "region": "us-west-2",
  "expected_resources": {
    "aws_vpc": 1,
    "aws_subnet": 4,
    "aws_eks_cluster": 1,
    "aws_eks_node_group": 1,
    "aws_iam_role": 2,
    "aws_security_group": 2,
    "aws_internet_gateway": 1,
    "aws_nat_gateway": 2
  },
  "required_outputs": ["cluster_endpoint", "cluster_name", "cluster_certificate_authority"],
  "validation_script": "validation_tests/eks_cluster_test.py",
  "metadata": {
    "estimated_cost": "$70-100/month",
    "deployment_time_seconds": 900,
    "cleanup_required": true
  }
}
```

## Usage

```bash
# Run benchmark
python dataset_loader.py \
  --dataset examples/terraform_bench.jsonl \
  --agent-command "mini --model claude-sonnet-4" \
  --output-dir results/run_001

# View results
cat results/run_001/benchmark_results.json
```

## Directory Structure

```
terraform-agent/
├── datasets/
│   ├── terraform_bench_full.jsonl       # Complete dataset
│   ├── terraform_bench_lite.jsonl       # Small subset for testing
│   └── terraform_bench_schema.json      # JSON schema definition
├── validation_tests/
│   ├── __init__.py
│   ├── base_test.py                     # Base test class
│   ├── lambda_vpc_test.py
│   ├── s3_cloudfront_test.py
│   ├── eks_cluster_test.py
│   └── ...
├── dataset_loader.py                     # Main benchmark runner
├── evaluate.py                           # Evaluation metrics
└── README.md                             # Documentation
```

## Next Steps

1. Create initial dataset with 10-20 instances covering common patterns
2. Implement base validation test framework
3. Build dataset loader with Terraform execution
4. Add metrics and reporting
5. Expand dataset to 100+ instances
6. Add support for Azure and GCP providers
