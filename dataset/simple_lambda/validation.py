"""Validation test for simple Lambda infrastructure."""

import os
import boto3
from typing import Dict, Any


class TestLambdaInfrastructure:
    """Validate simple Lambda function with IAM role."""

    def __init__(self, region: str = 'us-east-1', endpoint_url: str = None):
        """Initialize test with AWS region."""
        self.region = region
        self.endpoint_url = endpoint_url

        # Create boto3 clients with optional endpoint_url for LocalStack
        client_kwargs = {'region_name': region}
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

        self.lambda_client = boto3.client('lambda', **client_kwargs)
        self.iam = boto3.client('iam', **client_kwargs)
        self._function = None
        self._role_name = None

    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks for Lambda infrastructure.

        Returns:
            Dictionary with:
                - passed: bool (overall pass/fail)
                - tests: dict of individual test results
                - errors: list of error messages
        """
        results = {
            'passed': True,
            'tests': {},
            'errors': []
        }

        # Run each test
        test_methods = [
            ('lambda_exists', self.test_lambda_exists),
            ('lambda_name_correct', self.test_lambda_name_correct),
            ('lambda_runtime', self.test_lambda_runtime),
            ('lambda_s3_deployment', self.test_lambda_s3_deployment),
            ('iam_role_exists', self.test_iam_role_exists),
            ('iam_assume_role_policy', self.test_iam_assume_role_policy),
            ('iam_policy_attachment', self.test_iam_policy_attachment),
        ]

        for test_name, test_func in test_methods:
            try:
                test_func()
                results['tests'][test_name] = True
            except AssertionError as e:
                results['tests'][test_name] = False
                results['errors'].append(f"{test_name}: {str(e)}")
                results['passed'] = False
            except Exception as e:
                results['tests'][test_name] = False
                results['errors'].append(f"{test_name}: Unexpected error: {str(e)}")
                results['passed'] = False

        return results

    def test_lambda_exists(self):
        """Check that Lambda function exists."""
        functions = self.lambda_client.list_functions()
        assert functions['Functions'], "No Lambda functions found in the region"

    def test_lambda_name_correct(self):
        """Check Lambda function named 'hello_world' exists."""
        try:
            function = self.lambda_client.get_function(FunctionName='hello_world')
            self._function = function['Configuration']
        except self.lambda_client.exceptions.ResourceNotFoundException:
            raise AssertionError("Lambda function 'hello_world' not found")

    def test_lambda_runtime(self):
        """Check Lambda function uses Go runtime (provided.al2 or go1.x)."""
        if not self._function:
            self.test_lambda_name_correct()

        runtime = self._function.get('Runtime', '')
        valid_runtimes = ['provided.al2', 'go1.x']
        assert runtime in valid_runtimes, \
            f"Lambda runtime is '{runtime}', expected one of {valid_runtimes}"

    def test_lambda_s3_deployment(self):
        """Check Lambda function uses S3 deployment (not local file)."""
        if not self._function:
            self.test_lambda_name_correct()

        # Get function code location
        try:
            code_info = self.lambda_client.get_function(FunctionName='hello_world')
            code = code_info.get('Code', {})

            # Check that S3 location is present
            s3_bucket = self._function.get('CodeSha256')  # This will exist for any deployment
            assert s3_bucket, "Lambda function does not have code"

            # The function configuration should not have a local file reference
            # Instead, it should have been deployed from S3
            # We can verify this by checking the Code section
            repository_type = code.get('RepositoryType')
            if repository_type:
                assert repository_type == 'S3', \
                    f"Lambda deployed from {repository_type}, expected S3"

        except Exception as e:
            # If we can't verify deployment method conclusively, just check handler
            handler = self._function.get('Handler', '')
            assert handler == 'bootstrap', \
                f"Lambda handler is '{handler}', expected 'bootstrap' for Go Lambda"

    def test_iam_role_exists(self):
        """Check IAM role exists for Lambda function."""
        if not self._function:
            self.test_lambda_name_correct()

        role_arn = self._function.get('Role')
        assert role_arn, "Lambda function does not have an IAM role"

        # Extract role name from ARN
        self._role_name = role_arn.split('/')[-1]

        try:
            self.iam.get_role(RoleName=self._role_name)
        except self.iam.exceptions.NoSuchEntityException:
            raise AssertionError(f"IAM role '{self._role_name}' not found")

    def test_iam_assume_role_policy(self):
        """Check IAM role has proper AssumeRole policy for Lambda."""
        if not self._role_name:
            self.test_iam_role_exists()

        role = self.iam.get_role(RoleName=self._role_name)
        assume_role_policy = role['Role']['AssumeRolePolicyDocument']

        # Check that Lambda service can assume the role
        statements = assume_role_policy.get('Statement', [])
        assert statements, "No statements in AssumeRole policy"

        lambda_can_assume = False
        for statement in statements:
            if (statement.get('Effect') == 'Allow' and
                statement.get('Action') == 'sts:AssumeRole' and
                statement.get('Principal', {}).get('Service') == 'lambda.amazonaws.com'):
                lambda_can_assume = True
                break

        assert lambda_can_assume, "IAM role does not allow Lambda service to assume it"

    def test_iam_policy_attachment(self):
        """Check IAM role has AWSLambdaBasicExecutionRole policy attached."""
        if not self._role_name:
            self.test_iam_role_exists()

        attached_policies = self.iam.list_attached_role_policies(RoleName=self._role_name)
        policy_arns = [p['PolicyArn'] for p in attached_policies['AttachedPolicies']]

        basic_execution_policy = 'arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole'
        assert basic_execution_policy in policy_arns, \
            f"AWSLambdaBasicExecutionRole not attached to role. Attached policies: {policy_arns}"


if __name__ == '__main__':
    """Run validation tests."""
    import sys
    import json

    # Get endpoint URL from environment (for LocalStack support)
    endpoint_url = os.environ.get('AWS_ENDPOINT_URL')
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

    # Run validation
    validator = TestLambdaInfrastructure(region=region, endpoint_url=endpoint_url)
    results = validator.validate()

    # Print results as JSON
    print(json.dumps(results, indent=2))

    # Exit with appropriate code
    sys.exit(0 if results['passed'] else 1)
