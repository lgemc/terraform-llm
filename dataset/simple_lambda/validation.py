"""Validation test for simple Lambda infrastructure."""

import os
import boto3
import json
import sys
from typing import Dict, Any


class TestLambdaInfrastructure:
    """Validate simple Lambda function with IAM role."""

    def __init__(self, region: str = 'us-east-1', endpoint_url: str = None):
        client_kwargs = {'region_name': region}
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

        self.lambda_client = boto3.client('lambda', **client_kwargs)
        self.iam = boto3.client('iam', **client_kwargs)
        self._function = None
        self._role_name = None

    def validate(self) -> Dict[str, Any]:
        results = {
            'passed': True,
            'tests': {},
            'errors': []
        }

        test_methods = [
            ('lambda_exists', self.test_lambda_exists),
            ('lambda_name_correct', self.test_lambda_name_correct),
            ('lambda_runtime', self.test_lambda_runtime),
            ('lambda_handler', self.test_lambda_handler),
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
        """Check Lambda function uses Python 3.12 runtime."""
        if not self._function:
            self.test_lambda_name_correct()

        runtime = self._function.get('Runtime', '')
        assert runtime == 'python3.12', \
            f"Lambda runtime is '{runtime}', expected 'python3.12'"

    def test_lambda_handler(self):
        """Check Lambda function handler is handler.handler."""
        if not self._function:
            self.test_lambda_name_correct()

        handler = self._function.get('Handler', '')
        assert handler == 'handler.handler', \
            f"Lambda handler is '{handler}', expected 'handler.handler'"

    def test_iam_role_exists(self):
        """Check IAM role exists for Lambda function."""
        if not self._function:
            self.test_lambda_name_correct()

        role_arn = self._function.get('Role')
        assert role_arn, "Lambda function does not have an IAM role"

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
    endpoint_url = os.environ.get('AWS_ENDPOINT_URL')
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

    validator = TestLambdaInfrastructure(region=region, endpoint_url=endpoint_url)
    results = validator.validate()

    print(json.dumps(results, indent=2))
    sys.exit(0 if results['passed'] else 1)
