"""Base class for infrastructure validation tests."""

import boto3
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseTerraformTest(ABC):
    """Base class for all Terraform infrastructure validation tests."""

    def __init__(self, region: str = 'us-east-1', tags: Optional[Dict[str, str]] = None):
        """
        Initialize test base.

        Args:
            region: AWS region
            tags: Optional tags to filter resources
        """
        self.region = region
        self.tags = tags or {}
        self.setup_clients()

    def setup_clients(self):
        """Initialize boto3 clients."""
        self.ec2 = boto3.client('ec2', region_name=self.region)
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.iam = boto3.client('iam', region_name=self.region)
        self.s3 = boto3.client('s3', region_name=self.region)
        self.cloudfront = boto3.client('cloudfront', region_name=self.region)
        self.eks = boto3.client('eks', region_name=self.region)
        self.rds = boto3.client('rds', region_name=self.region)
        self.dynamodb = boto3.client('dynamodb', region_name=self.region)

    def find_resource_by_tags(
        self,
        resource_type: str,
        filters: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Find resources by tags.

        Args:
            resource_type: Type of resource to find
            filters: Additional filters

        Returns:
            List of matching resources
        """
        base_filters = [
            {'Name': f'tag:{k}', 'Values': [v]}
            for k, v in self.tags.items()
        ]

        if filters:
            base_filters.extend(filters)

        # Route to appropriate describe method
        if resource_type == 'vpc':
            return self.ec2.describe_vpcs(Filters=base_filters)['Vpcs']
        elif resource_type == 'subnet':
            return self.ec2.describe_subnets(Filters=base_filters)['Subnets']
        elif resource_type == 'security_group':
            return self.ec2.describe_security_groups(Filters=base_filters)['SecurityGroups']
        elif resource_type == 'instance':
            return self.ec2.describe_instances(Filters=base_filters)['Reservations']
        elif resource_type == 'internet_gateway':
            return self.ec2.describe_internet_gateways(Filters=base_filters)['InternetGateways']
        elif resource_type == 'nat_gateway':
            return self.ec2.describe_nat_gateways(Filters=base_filters)['NatGateways']
        elif resource_type == 'route_table':
            return self.ec2.describe_route_tables(Filters=base_filters)['RouteTables']

        return []

    @abstractmethod
    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks.

        Returns:
            Dictionary with validation results
        """
        pass

    def run_test(self, test_name: str, test_func) -> Dict[str, Any]:
        """
        Run a single test and capture result.

        Args:
            test_name: Name of the test
            test_func: Test function to run

        Returns:
            Test result dictionary
        """
        try:
            result = test_func()
            return {
                'name': test_name,
                'passed': result,
                'error': None
            }
        except AssertionError as e:
            return {
                'name': test_name,
                'passed': False,
                'error': str(e)
            }
        except Exception as e:
            return {
                'name': test_name,
                'passed': False,
                'error': f'Unexpected error: {str(e)}'
            }
