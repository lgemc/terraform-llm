"""Validation tests for Lambda + VPC infrastructure."""

from typing import Dict, Any, Optional
from terraform_llm.validation_tests.base_test import BaseTerraformTest


class TestLambdaVPCInfrastructure(BaseTerraformTest):
    """Validate Lambda function deployed in VPC."""

    def validate(self) -> Dict[str, Any]:
        """Run all validation checks."""
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
        """Check that VPC was created."""
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
        """Check that subnets exist in VPC."""
        subnets = self.find_resource_by_tags('subnet')
        assert len(subnets) >= 2, "At least 2 subnets required for HA"

        # Check subnets are in different AZs
        azs = set(subnet['AvailabilityZone'] for subnet in subnets)
        assert len(azs) >= 2, "Subnets should be in different availability zones"

        return True

    def test_lambda_exists(self) -> bool:
        """Check Lambda function exists."""
        target_function = self._find_lambda_function()
        assert target_function is not None, "Lambda function not found"

        # Check runtime is Go
        runtime = target_function.get('Runtime', '')
        assert runtime.startswith('go') or 'provided' in runtime, \
            f"Expected Go runtime, got {runtime}"

        return True

    def test_lambda_in_vpc(self) -> bool:
        """Check Lambda is deployed in VPC."""
        target_function = self._find_lambda_function()
        assert 'VpcConfig' in target_function, "Lambda not configured with VPC"

        vpc_config = target_function['VpcConfig']
        assert vpc_config.get('VpcId'), "Lambda VPC ID is empty"
        assert len(vpc_config.get('SubnetIds', [])) >= 1, "No subnets configured"
        assert len(vpc_config.get('SecurityGroupIds', [])) >= 1, "No security groups configured"

        return True

    def test_lambda_has_proper_iam_role(self) -> bool:
        """Check Lambda has IAM role with VPC execution permissions."""
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
        """Check security group is created and attached."""
        target_function = self._find_lambda_function()
        sg_ids = target_function['VpcConfig']['SecurityGroupIds']

        sgs = self.ec2.describe_security_groups(GroupIds=sg_ids)
        assert len(sgs['SecurityGroups']) >= 1, "Security group not found"

        return True

    def _find_lambda_function(self) -> Optional[Dict[str, Any]]:
        """Helper to find the Lambda function."""
        functions = self.lambda_client.list_functions()

        # Try to find by tags or name patterns
        for func in functions['Functions']:
            func_name = func['FunctionName']
            # Match common patterns
            if any(keyword in func_name.lower() for keyword in ['golang', 'go-lambda', 'vpc', 'lambda']):
                return func

        # If no pattern match, return first function (if any)
        if functions['Functions']:
            return functions['Functions'][0]

        return None
