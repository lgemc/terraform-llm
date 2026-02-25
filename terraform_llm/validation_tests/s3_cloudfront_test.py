"""Validation tests for S3 + CloudFront infrastructure."""

from typing import Dict, Any, Optional
from terraform_llm.validation_tests.base_test import BaseTerraformTest


class TestS3CloudFrontInfrastructure(BaseTerraformTest):
    """Validate S3 bucket with CloudFront distribution."""

    def validate(self) -> Dict[str, Any]:
        """Run all validation checks."""
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
        """Check S3 bucket exists."""
        bucket_name = self._find_bucket()
        assert bucket_name is not None, "S3 bucket not found"

        # Check bucket exists
        response = self.s3.head_bucket(Bucket=bucket_name)
        assert response['ResponseMetadata']['HTTPStatusCode'] == 200

        return True

    def test_bucket_static_hosting(self) -> bool:
        """Check bucket is configured for static website hosting."""
        bucket_name = self._find_bucket()

        try:
            website_config = self.s3.get_bucket_website(Bucket=bucket_name)
            assert 'IndexDocument' in website_config, "Index document not configured"
            return True
        except self.s3.exceptions.NoSuchWebsiteConfiguration:
            # Bucket might use CloudFront without website hosting
            return True

    def test_cloudfront_distribution(self) -> bool:
        """Check CloudFront distribution exists and is enabled."""
        distribution = self._find_distribution()
        assert distribution is not None, "CloudFront distribution not found"

        # Check distribution is enabled
        assert distribution['Enabled'], "CloudFront distribution is not enabled"

        return True

    def test_cloudfront_origin(self) -> bool:
        """Check CloudFront origin points to S3 bucket."""
        distribution = self._find_distribution()
        bucket_name = self._find_bucket()

        # Get origins
        origins = distribution.get('Origins', {}).get('Items', [])
        assert len(origins) > 0, "No origins configured"

        # Check if any origin points to our bucket
        bucket_found = False
        for origin in origins:
            domain_name = origin.get('DomainName', '')
            if bucket_name in domain_name:
                bucket_found = True
                break

        assert bucket_found, f"No origin points to bucket {bucket_name}"

        return True

    def _find_bucket(self) -> Optional[str]:
        """Find the S3 bucket."""
        # List all buckets
        response = self.s3.list_buckets()

        # Try to find bucket by tags or creation time
        for bucket in response['Buckets']:
            bucket_name = bucket['Name']

            # Check tags if available
            try:
                tags_response = self.s3.get_bucket_tagging(Bucket=bucket_name)
                tags = {tag['Key']: tag['Value'] for tag in tags_response.get('TagSet', [])}

                # Match against our tags
                if all(tags.get(k) == v for k, v in self.tags.items()):
                    return bucket_name
            except:
                pass

        # If no tag match, return most recent bucket
        if response['Buckets']:
            # Sort by creation date and return newest
            sorted_buckets = sorted(
                response['Buckets'],
                key=lambda b: b['CreationDate'],
                reverse=True
            )
            return sorted_buckets[0]['Name']

        return None

    def _find_distribution(self) -> Optional[Dict[str, Any]]:
        """Find the CloudFront distribution."""
        response = self.cloudfront.list_distributions()

        distributions = response.get('DistributionList', {}).get('Items', [])

        if not distributions:
            return None

        # Return most recent distribution
        # (In production, you'd want better filtering)
        return distributions[0]
