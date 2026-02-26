"""Fetch iac-eval dataset and find top 10 hardest LocalStack-compatible entries."""

import json
from datasets import load_dataset

# LocalStack well-supported services (free + pro common ones)
LOCALSTACK_SUPPORTED_RESOURCES = {
    "aws_s3_bucket", "aws_s3_bucket_policy", "aws_s3_bucket_versioning",
    "aws_s3_bucket_lifecycle_configuration", "aws_s3_bucket_notification",
    "aws_s3_bucket_cors_configuration", "aws_s3_bucket_website_configuration",
    "aws_s3_bucket_server_side_encryption_configuration",
    "aws_s3_bucket_public_access_block", "aws_s3_bucket_acl",
    "aws_s3_bucket_logging", "aws_s3_bucket_object_lock_configuration",
    "aws_s3_object",
    "aws_sqs_queue", "aws_sqs_queue_policy",
    "aws_sns_topic", "aws_sns_topic_subscription", "aws_sns_topic_policy",
    "aws_lambda_function", "aws_lambda_permission", "aws_lambda_event_source_mapping",
    "aws_lambda_layer_version", "aws_lambda_alias",
    "aws_dynamodb_table", "aws_dynamodb_table_item",
    "aws_iam_role", "aws_iam_policy", "aws_iam_role_policy",
    "aws_iam_role_policy_attachment", "aws_iam_policy_document",
    "aws_iam_instance_profile", "aws_iam_user", "aws_iam_group",
    "aws_iam_user_policy_attachment", "aws_iam_group_policy_attachment",
    "aws_cloudwatch_log_group", "aws_cloudwatch_log_stream",
    "aws_cloudwatch_metric_alarm", "aws_cloudwatch_log_resource_policy",
    "aws_kinesis_stream", "aws_kinesis_firehose_delivery_stream",
    "aws_api_gateway_rest_api", "aws_api_gateway_resource",
    "aws_api_gateway_method", "aws_api_gateway_integration",
    "aws_api_gateway_deployment", "aws_api_gateway_stage",
    "aws_api_gateway_method_response", "aws_api_gateway_integration_response",
    "aws_apigatewayv2_api", "aws_apigatewayv2_stage",
    "aws_apigatewayv2_integration", "aws_apigatewayv2_route",
    "aws_secretsmanager_secret", "aws_secretsmanager_secret_version",
    "aws_ssm_parameter",
    "aws_kms_key", "aws_kms_alias",
    "aws_stepfunctions_state_machine", "aws_sfn_state_machine",
    "aws_ses_email_identity", "aws_ses_domain_identity",
    "aws_cloudformation_stack",
    "aws_route53_zone", "aws_route53_record",
    "aws_acm_certificate",
    "aws_cloudwatch_event_rule", "aws_cloudwatch_event_target",
    "aws_vpc", "aws_subnet", "aws_security_group", "aws_security_group_rule",
    "aws_internet_gateway", "aws_route_table", "aws_route_table_association",
    "aws_nat_gateway", "aws_eip", "aws_network_acl",
    "aws_ec2_fleet", "aws_instance",
    "aws_lb", "aws_lb_target_group", "aws_lb_listener", "aws_lb_listener_rule",
    "aws_ecr_repository", "aws_ecr_lifecycle_policy",
    "aws_ecs_cluster", "aws_ecs_task_definition", "aws_ecs_service",
    "aws_cloudfront_distribution", "aws_cloudfront_origin_access_identity",
    "aws_elasticache_cluster", "aws_elasticache_replication_group",
    "aws_elasticache_subnet_group",
    "aws_db_instance", "aws_db_subnet_group", "aws_db_parameter_group",
    "aws_cognito_user_pool", "aws_cognito_user_pool_client",
}


def is_localstack_compatible(resource_types: list[str]) -> bool:
    """Check if ALL resource types in the entry are supported by LocalStack."""
    for r in resource_types:
        if r not in LOCALSTACK_SUPPORTED_RESOURCES:
            return False
    return True


def extract_resource_types(terraform_code: str) -> list[str]:
    """Extract resource type names from terraform code."""
    import re
    resources = re.findall(r'resource\s+"([^"]+)"', terraform_code)
    return list(set(resources))


def main():
    print("Loading dataset...")
    ds = load_dataset("autoiac-project/iac-eval", split="test")
    print(f"Total entries: {len(ds)}")

    # Analyze each entry
    entries = []
    for i, row in enumerate(ds):
        resource_types = extract_resource_types(row.get("terraform_code", "") or row.get("code", "") or "")

        # Try to get resources from different possible fields
        if not resource_types:
            # Check all fields for terraform code
            for key in row.keys():
                val = row[key]
                if isinstance(val, str) and "resource" in val:
                    resource_types = extract_resource_types(val)
                    if resource_types:
                        break

        entries.append({
            "index": i,
            "row": row,
            "resource_types": resource_types,
            "localstack_compatible": is_localstack_compatible(resource_types) if resource_types else False,
            "num_resources": len(resource_types),
        })

    # Print column names for debugging
    print(f"\nColumn names: {ds.column_names}")
    print(f"\nSample row keys: {list(ds[0].keys())}")

    # Show a sample entry
    sample = ds[0]
    for k, v in sample.items():
        val_str = str(v)[:200]
        print(f"  {k}: {val_str}")

    # Filter for LocalStack compatible
    compatible = [e for e in entries if e["localstack_compatible"]]
    print(f"\nLocalStack compatible entries: {len(compatible)}")

    # Sort by difficulty (highest first), then by number of resources
    for e in compatible:
        row = e["row"]
        diff = row.get("Difficulty", row.get("difficulty", 0))
        if isinstance(diff, str):
            try:
                diff = int(diff)
            except ValueError:
                diff = 0
        e["difficulty"] = diff

    compatible.sort(key=lambda x: (x["difficulty"], x["num_resources"]), reverse=True)

    # Deduplicate: skip entries with the same set of resource types AND same difficulty
    seen_signatures = set()
    deduplicated = []
    for e in compatible:
        sig = (frozenset(e["resource_types"]), e["difficulty"])
        if sig not in seen_signatures:
            seen_signatures.add(sig)
            deduplicated.append(e)

    print(f"After dedup: {len(deduplicated)} unique entries")

    # Pick top 10 with diversity in resource types
    top10 = deduplicated[:10]

    print(f"\n{'='*80}")
    print(f"TOP 10 HARDEST LOCALSTACK-COMPATIBLE ENTRIES")
    print(f"{'='*80}")

    for rank, entry in enumerate(top10, 1):
        row = entry["row"]
        print(f"\n--- #{rank} (index={entry['index']}, difficulty={entry['difficulty']}, resources={entry['num_resources']}) ---")
        print(f"Resources: {entry['resource_types']}")
        # Print all text fields
        for k, v in row.items():
            if isinstance(v, str) and len(v) < 500:
                print(f"  {k}: {v[:300]}")
            elif isinstance(v, (int, float)):
                print(f"  {k}: {v}")

    # Save top 10 as JSON for later use
    output = []
    for entry in top10:
        row = entry["row"]
        output.append({
            "index": entry["index"],
            "difficulty": entry["difficulty"],
            "resource_types": entry["resource_types"],
            "num_resources": entry["num_resources"],
            **{k: v for k, v in row.items()},
        })

    with open("scripts/top10_localstack.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nSaved top 10 to scripts/top10_localstack.json")


if __name__ == "__main__":
    main()
