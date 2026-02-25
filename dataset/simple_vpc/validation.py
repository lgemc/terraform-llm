"""Validation test for simple VPC infrastructure."""

import os
import boto3
from typing import Dict, Any


class TestVPCInfrastructure:
    """Validate simple VPC with public subnet."""

    def __init__(self, region: str = 'us-east-1', endpoint_url: str = None):
        """Initialize test with AWS region."""
        self.region = region
        self.endpoint_url = endpoint_url

        # Create boto3 client with optional endpoint_url for LocalStack
        client_kwargs = {'region_name': region}
        if endpoint_url:
            client_kwargs['endpoint_url'] = endpoint_url

        self.ec2 = boto3.client('ec2', **client_kwargs)
        self._vpc_id = None
        self._subnet_id = None

    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks for VPC infrastructure.

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
            ('vpc_exists', self.test_vpc_exists),
            ('vpc_cidr_correct', self.test_vpc_cidr_correct),
            ('vpc_name_tag', self.test_vpc_name_tag),
            ('public_subnet_exists', self.test_public_subnet_exists),
            ('subnet_cidr_correct', self.test_subnet_cidr_correct),
            ('subnet_availability_zone', self.test_subnet_availability_zone),
            ('subnet_public_ip_mapping', self.test_subnet_public_ip_mapping),
            ('subnet_name_tag', self.test_subnet_name_tag),
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

    def test_vpc_exists(self):
        """Check that at least one VPC exists."""
        vpcs = self.ec2.describe_vpcs()['Vpcs']
        assert vpcs, "No VPC found in the region"

    def test_vpc_cidr_correct(self):
        """Check VPC has correct CIDR block 10.0.0.0/16."""
        vpcs = self.ec2.describe_vpcs()['Vpcs']

        for vpc in vpcs:
            if vpc.get('CidrBlock') == '10.0.0.0/16':
                self._vpc_id = vpc['VpcId']
                return

        raise AssertionError("VPC with CIDR block 10.0.0.0/16 not found")

    def test_vpc_name_tag(self):
        """Check VPC is tagged with Name='main'."""
        if not self._vpc_id:
            self.test_vpc_cidr_correct()

        vpc = self.ec2.describe_vpcs(VpcIds=[self._vpc_id])['Vpcs'][0]
        tags = {tag['Key']: tag['Value'] for tag in vpc.get('Tags', [])}

        assert tags.get('Name') == 'main', f"VPC Name tag is '{tags.get('Name')}', expected 'main'"

    def test_public_subnet_exists(self):
        """Check that at least one subnet exists."""
        if not self._vpc_id:
            self.test_vpc_cidr_correct()

        subnets = self.ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [self._vpc_id]}]
        )['Subnets']

        assert subnets, "No subnets found in VPC"

    def test_subnet_cidr_correct(self):
        """Check subnet has correct CIDR block 10.0.1.0/24."""
        if not self._vpc_id:
            self.test_vpc_cidr_correct()

        subnets = self.ec2.describe_subnets(
            Filters=[{'Name': 'vpc-id', 'Values': [self._vpc_id]}]
        )['Subnets']

        for subnet in subnets:
            if subnet.get('CidrBlock') == '10.0.1.0/24':
                self._subnet_id = subnet['SubnetId']
                return

        raise AssertionError("Subnet with CIDR block 10.0.1.0/24 not found")

    def test_subnet_availability_zone(self):
        """Check subnet is in us-east-1a."""
        if not self._subnet_id:
            self.test_subnet_cidr_correct()

        subnet = self.ec2.describe_subnets(SubnetIds=[self._subnet_id])['Subnets'][0]
        az = subnet.get('AvailabilityZone')

        assert az == 'us-east-1a', f"Subnet is in AZ '{az}', expected 'us-east-1a'"

    def test_subnet_public_ip_mapping(self):
        """Check subnet has map_public_ip_on_launch enabled."""
        if not self._subnet_id:
            self.test_subnet_cidr_correct()

        subnet = self.ec2.describe_subnets(SubnetIds=[self._subnet_id])['Subnets'][0]

        assert subnet.get('MapPublicIpOnLaunch', False), \
            "Subnet does not have map_public_ip_on_launch enabled"

    def test_subnet_name_tag(self):
        """Check subnet is tagged with Name='public'."""
        if not self._subnet_id:
            self.test_subnet_cidr_correct()

        subnet = self.ec2.describe_subnets(SubnetIds=[self._subnet_id])['Subnets'][0]
        tags = {tag['Key']: tag['Value'] for tag in subnet.get('Tags', [])}

        assert tags.get('Name') == 'public', \
            f"Subnet Name tag is '{tags.get('Name')}', expected 'public'"


if __name__ == '__main__':
    """Run validation tests."""
    import sys
    import json

    # Get endpoint URL from environment (for LocalStack support)
    endpoint_url = os.environ.get('AWS_ENDPOINT_URL')
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

    # Run validation
    validator = TestVPCInfrastructure(region=region, endpoint_url=endpoint_url)
    results = validator.validate()

    # Print results as JSON
    print(json.dumps(results, indent=2))

    # Exit with appropriate code
    sys.exit(0 if results['passed'] else 1)
